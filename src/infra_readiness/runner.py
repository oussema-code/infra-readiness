"""Run bounded probe processes so DNS and slow headers cannot outlive a deadline."""

import asyncio
from dataclasses import asdict
import json
import sys
from time import monotonic

from .config import Check, Config
from .models import Result, Status


def target(check: Check) -> str:
    if check.type == "http":
        return check.url
    if check.type == "tcp":
        host = f"[{check.host}]" if ":" in check.host else check.host
        return f"{host}:{check.port}"
    return check.host


async def run_check(check: Check) -> Result:
    started = monotonic()
    process = None
    status, evidence, category = Status.UNKNOWN, "Probe worker failed", "tool_error"
    try:
        async with asyncio.timeout(check.timeout):
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "infra_readiness.worker",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await process.communicate(json.dumps(asdict(check)).encode())
            if process.returncode == 0:
                payload = json.loads(stdout)
                status = Status(payload["status"])
                evidence, category = payload["evidence"], payload["error_category"]
    except TimeoutError:
        status = Status.UNKNOWN
        evidence = f"Check deadline of {check.timeout:g}s exceeded; service state is undetermined"
        category = "timeout"
    except (OSError, ValueError, KeyError, TypeError):
        status, evidence, category = Status.UNKNOWN, "Probe worker could not execute or return a valid result", "tool_error"
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()
    return Result(check.name, check.type, target(check), status,
                  round((monotonic() - started) * 1000, 3), evidence, category)


async def run_checks(config: Config) -> list[Result]:
    semaphore = asyncio.Semaphore(config.concurrency)

    async def limited(check):
        async with semaphore:
            return await run_check(check)

    # gather preserves configuration order even when workers finish out of order.
    return list(await asyncio.gather(*(limited(check) for check in config.checks)))
