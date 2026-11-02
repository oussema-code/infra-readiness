"""Verify controlled failures and recovery, then remove only our isolated lab."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASE_NAMES = {"database-dns", "database-tcp", "api-live", "api-ready", "proxy-ready"}


def main():
    project = f"readiness-smoke-{uuid.uuid4().hex[:8]}"
    reports = ROOT / "reports" / project
    reports.mkdir(parents=True)
    env = {**os.environ, "LAB_PORT": "0"}
    base = ["docker", "compose", "--progress", "quiet", "-p", project,
            "-f", str(ROOT / "lab/compose.yaml")]

    def compose(*arguments, timeout=300):
        completed = subprocess.run(base + list(arguments), capture_output=True, text=True,
                                   env=env, timeout=timeout)
        with (reports / "compose.log").open("a") as log:
            log.write(f"{' '.join(arguments)}\n{completed.stdout}\n{completed.stderr}\n")
        return completed

    def require(*arguments, timeout=300):
        completed = compose(*arguments, timeout=timeout)
        if completed.returncode:
            raise RuntimeError(f"Compose command failed: {' '.join(arguments)}; see {reports}")
        return completed

    def check(stage, expected_codes=(0,), config="lab.yaml", names=BASE_NAMES):
        completed = compose("run", "--rm", "-T", "checker", "run", f"/config/{config}", "--json", "-")
        (reports / f"{stage}.json").write_text(completed.stdout)
        if completed.returncode not in expected_codes:
            raise RuntimeError(f"{stage}: expected exit in {expected_codes}, got {completed.returncode}")
        document = json.loads(completed.stdout)
        results = {result["name"]: result for result in document["checks"]}
        if (document["exit_code"] != completed.returncode or set(results) != names
                or len(document["checks"]) != len(names)):
            raise RuntimeError(f"{stage}: inconsistent JSON report")
        print(f"{stage}: {document['summary']}; exit {completed.returncode}", flush=True)
        return results

    def healthy(stage):
        if any(result["status"] != "PASS" for result in check(stage).values()):
            raise RuntimeError(f"{stage}: every baseline check must pass")

    def proxy_config(filename):
        require("cp", str(ROOT / "lab/proxy" / filename), "proxy:/etc/nginx/conf.d/default.conf")
        require("exec", "-T", "proxy", "nginx", "-t")
        require("exec", "-T", "proxy", "nginx", "-s", "reload")

    def wait_proxy(expected_status):
        address = require("port", "proxy", "80").stdout.strip()
        deadline = time.monotonic() + 20
        # Reload is asynchronous: poll for the new configuration to serve requests.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            try:
                with opener.open(f"http://{address}/ready", timeout=1) as response:
                    observed = response.status
            except urllib.error.HTTPError as error:
                observed = error.code
                error.close()
            except (urllib.error.URLError, TimeoutError):
                observed = None
            if observed == expected_status:
                return
            time.sleep(0.2)
        raise RuntimeError(f"proxy did not serve HTTP {expected_status} after configuration reload")

    try:
        require("build", "backend", "proxy", "checker", timeout=600)
        require("up", "-d", "--wait", "--wait-timeout", "180")
        healthy("baseline")

        require("stop", "db")
        try:
            outage = check("database-outage", (1,))
            if outage["api-live"]["status"] != "PASS":
                raise RuntimeError("API liveness must survive a database outage")
            for name in ("api-ready", "proxy-ready"):
                if (outage[name]["status"] != "FAIL" or outage[name]["error_category"] != "http_status"
                        or "HTTP 503" not in outage[name]["evidence"]):
                    raise RuntimeError(f"{name} must observe HTTP 503 during the outage")
            if outage["database-tcp"]["status"] == "PASS":
                raise RuntimeError("database TCP must not pass during the outage")
        finally:
            require("start", "db")
            require("up", "-d", "--wait", "--wait-timeout", "180")
            healthy("database-recovered")

        try:
            missing = check("invalid-hostname", (1, 2), "invalid-hostname.yaml", {"invalid-dns", "api-live"})
            dns = missing["invalid-dns"]
            if ((dns["status"], dns["error_category"]) not in {
                    ("FAIL", "dns_not_found"), ("UNKNOWN", "dns_error"), ("UNKNOWN", "timeout")}
                    or missing["api-live"]["status"] != "PASS"):
                raise RuntimeError("invalid hostname must report negative/incomplete DNS evidence and preserve liveness")
        finally:
            # Restore the original targets: no service configuration was changed.
            healthy("hostname-recovered")

        try:
            delayed = check("delayed-response", (2,), "delayed-response.yaml", {"delayed-ready", "api-live"})
            slow = delayed["delayed-ready"]
            if ((slow["status"], slow["error_category"]) != ("UNKNOWN", "timeout")
                    or delayed["api-live"]["status"] != "PASS"):
                raise RuntimeError("delayed response must time out while liveness passes")
        finally:
            healthy("delay-recovered")

        try:
            proxy_config("broken.conf")
            wait_proxy(502)
            broken = check("broken-proxy", (1,))
            for name in BASE_NAMES - {"proxy-ready"}:
                if broken[name]["status"] != "PASS":
                    raise RuntimeError(f"{name} must pass when only the proxy upstream is broken")
            proxy = broken["proxy-ready"]
            if (proxy["status"] != "FAIL" or proxy["error_category"] != "http_status"
                    or "HTTP 502" not in proxy["evidence"]):
                raise RuntimeError("broken proxy must report HTTP 502")
        finally:
            proxy_config("conf")
            wait_proxy(200)
            healthy("proxy-recovered")

        print(f"All four failure exercises and recovery verified. Reports: {reports}", flush=True)
    finally:
        try:
            logs = compose("logs", "--no-color", timeout=30)
            (reports / "services.log").write_text(logs.stdout + logs.stderr)
        finally:
            # This random project owns only disposable synthetic data.
            require("down", "--volumes", "--remove-orphans", timeout=60)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
