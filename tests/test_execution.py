import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import threading
import time
from unittest.mock import patch

import pytest

from infra_readiness.cli import main
from infra_readiness.config import Check, Config
from infra_readiness.models import Status, exit_code
from infra_readiness.runner import run_check, run_checks
from infra_readiness.worker import execute


@pytest.fixture
def server():
    state = {"active": 0, "maximum": 0, "paths": []}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            with lock:
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
                state["paths"].append(self.path)
            try:
                if self.path == "/drip":
                    self.connection.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                    for _ in range(30):
                        self.connection.sendall(b"a")
                        time.sleep(0.04)
                    return
                if self.path == "/malformed":
                    self.connection.sendall(b"this is not HTTP\r\n\r\n")
                    return
                if self.path == "/slow":
                    time.sleep(0.2)
                status = {"/bad": 503, "/redirect": 302}.get(self.path, 200)
                self.send_response(status)
                if self.path == "/redirect":
                    self.send_header("Location", "/redirect-target")
                if self.path == "/unending-body":
                    self.send_header("Content-Length", "999999999")
                self.end_headers()
                if self.path == "/unending-body":
                    time.sleep(1)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with lock:
                    state["active"] -= 1

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", state
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def check(url, timeout=2, name="http", expected_status=200):
    return Check(name, "http", timeout, url=url, expected_status=expected_status)


@pytest.mark.parametrize("path, status, category", [
    ("/", Status.PASS, None), ("/bad", Status.FAIL, "http_status"),
    ("/redirect", Status.FAIL, "http_status"),
    ("/malformed", Status.FAIL, "http_protocol"),
    ("/unending-body", Status.PASS, None),
])
def test_real_http_responses(server, path, status, category):
    base, state = server
    result = asyncio.run(run_check(check(base + path)))
    assert result.status == status
    assert result.error_category == category
    assert "/redirect-target" not in state["paths"]


def test_expected_redirect_is_reported_without_following(server):
    base, state = server
    result = asyncio.run(run_check(check(base + "/redirect", expected_status=302)))
    assert result.status == Status.PASS
    assert state["paths"] == ["/redirect"]


def test_slow_headers_cannot_extend_total_deadline(server):
    base, _ = server
    result = asyncio.run(run_check(check(base + "/drip", timeout=0.3)))
    assert result.status == Status.UNKNOWN
    assert result.error_category == "timeout"
    assert result.duration_ms < 1500


def test_dns_and_tcp_localhost(server):
    base, _ = server
    port = int(base.rsplit(":", 1)[1])
    config = Config(2, (Check("dns", "dns", 2, host="localhost"),
                        Check("tcp", "tcp", 2, host="127.0.0.1", port=port)))
    results = asyncio.run(run_checks(config))
    assert [result.name for result in results] == ["dns", "tcp"]
    assert exit_code(results) == 0


def test_connection_refusal():
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        port = unused.getsockname()[1]
        result = asyncio.run(run_check(Check("closed", "tcp", 2, host="127.0.0.1", port=port)))
    assert result.status == Status.FAIL
    assert result.error_category == "connection_refused"


@pytest.mark.parametrize("error, category, status", [
    (socket.gaierror(socket.EAI_NONAME, "missing"), "dns_not_found", "FAIL"),
    (socket.gaierror(socket.EAI_AGAIN, "temporary"), "dns_error", "UNKNOWN"),
    (ssl.SSLCertVerificationError("invalid certificate"), "tls_certificate", "FAIL"),
])
def test_error_classification(error, category, status):
    with patch("infra_readiness.worker.probe", side_effect=error):
        observed = execute(Check("dns", "dns", 1, host="example.invalid"))
    assert observed[0] == status
    assert observed[2] == category


def test_concurrency_bound_and_order(server):
    base, state = server
    config = Config(2, tuple(check(base + "/slow", name=f"check-{i}") for i in range(5)))
    results = asyncio.run(run_checks(config))
    assert exit_code(results) == 0
    assert state["maximum"] == 2
    assert [result.name for result in results] == [f"check-{i}" for i in range(5)]


@contextmanager
def substitute_worker(script):
    """Exercise actual OS process lifecycle with deliberately broken workers."""
    original = asyncio.create_subprocess_exec
    processes = []

    async def spawn(*args, **kwargs):
        process = await original(sys.executable, "-c", script, **kwargs)
        processes.append(process)
        return process

    with patch("infra_readiness.runner.asyncio.create_subprocess_exec", side_effect=spawn):
        yield processes


def test_stalled_resolver_is_killed_and_reaped():
    script = "import socket,time; socket.getaddrinfo=lambda *a,**kw: time.sleep(30); from infra_readiness.worker import main; main()"
    with substitute_worker(script) as processes:
        result = asyncio.run(run_check(Check("dns", "dns", 0.3, host="localhost")))
    assert result.error_category == "timeout"
    assert processes[0].returncode is not None
    if os.name == "posix":
        with pytest.raises(ProcessLookupError):
            os.kill(processes[0].pid, 0)


def test_cancellation_cleans_up_worker():
    async def cancel():
        task = asyncio.create_task(run_check(Check("dns", "dns", 30, host="localhost")))
        while not processes:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with substitute_worker("import time; time.sleep(30)") as processes:
        asyncio.run(cancel())
    assert processes[0].returncode is not None


@pytest.mark.parametrize("script", ["raise RuntimeError('broken')", "print('not json')"])
def test_worker_failure_is_tool_error(script):
    with substitute_worker(script):
        result = asyncio.run(run_check(Check("dns", "dns", 2, host="localhost")))
    assert result.status == Status.UNKNOWN
    assert result.error_category == "tool_error"
    assert exit_code([result]) == 3


def test_cli_reports_same_results_and_preserves_mixed_outcomes(server, tmp_path, capsys):
    base, _ = server
    config = tmp_path / "checks.yaml"
    config.write_text(f'''checks:
  - {{name: healthy, type: http, url: '{base}/'}}
  - {{name: unhealthy, type: http, url: '{base}/bad'}}
  - {{name: slow, type: http, url: '{base}/drip', timeout: 0.3}}
''')
    output = tmp_path / "report.json"
    assert main(["run", str(config), "--json", str(output)]) == 1
    report = json.loads(output.read_text())
    assert report["exit_code"] == 1
    assert report["summary"] == {"PASS": 1, "FAIL": 1, "UNKNOWN": 1}
    text = capsys.readouterr().out
    for result in report["checks"]:
        assert result["name"] in text
        assert result["evidence"] in text


def test_invalid_config_starts_no_worker(tmp_path):
    config = tmp_path / "checks.yaml"
    config.write_text("checks: []")
    with patch("infra_readiness.runner.asyncio.create_subprocess_exec") as spawn:
        assert main(["run", str(config)]) == 3
    spawn.assert_not_called()


def test_report_cannot_overwrite_input(tmp_path):
    config = tmp_path / "checks.yaml"
    original = "checks: [{name: dns, type: dns, host: localhost}]"
    config.write_text(original)
    assert main(["run", str(config), "--json", str(config)]) == 3
    assert config.read_text() == original


def test_report_io_error_is_not_success(server, tmp_path, capsys):
    base, _ = server
    config = tmp_path / "checks.yaml"
    config.write_text(f"checks: [{{name: api, type: http, url: '{base}/'}}]")
    assert main(["run", str(config), "--json", str(tmp_path / "missing/report.json")]) == 3
    assert "cannot write JSON" in capsys.readouterr().err


def test_json_stdout_is_machine_readable(server, tmp_path, capsys):
    base, _ = server
    config = tmp_path / "checks.yaml"
    config.write_text(f"checks: [{{name: api, type: http, url: '{base}/'}}]")
    assert main(["run", str(config), "--json", "-"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["PASS"] == 1
