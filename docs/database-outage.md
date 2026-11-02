# Database outage and recovery — local Docker lab

Verified 2026-11-02 using the Python CLI running inside a Compose checker container.
This is a controlled single-machine exercise with synthetic records, not a
production incident or an availability benchmark.

## Symptoms and evidence

Healthy baseline: all five DNS/TCP/HTTP checks passed (exit 0).
After stopping the MariaDB service:

| Check | Result | Evidence |
| --- | --- | --- |
| Database DNS | UNKNOWN | Temporary resolver error, EAI_AGAIN (-3) |
| Database TCP | UNKNOWN | Name resolution failed before connectivity could be checked |
| API liveness | PASS | HTTP 200 |
| API readiness | FAIL | HTTP 503, expected 200 |
| Proxy readiness | FAIL | HTTP 503, expected 200 |

Overall exit code: 1. Both failures and incomplete evidence were retained.
The API readiness route performs a real query and checks the expected seed rows;
liveness does not depend on the database.

## Investigation and recovery

The harness intentionally ran `docker compose stop db`. The resulting temporary
Docker DNS error does not independently prove that a name is permanently absent
or a TCP port is closed. The tool therefore reported those probes as UNKNOWN.
The HTTP checks directly observed application unavailability through readiness.

The harness restarted MariaDB, waited for Compose health checks, and reran all
checks. All five passed again (exit 0), including readiness backed by the expected
database records. This verifies recovery from a stopped dependency; it does not
verify backup restoration or recovery from data loss.

## Reproduce

```bash
.venv/bin/python scripts/lab_smoke.py
```

Reports and logs are written under `reports/<random-project>/`. Resolver behavior
may differ across hosts; readiness HTTP 503 and successful recovery are explicit
harness assertions. No latency or recovery-time claim is made from this run.
