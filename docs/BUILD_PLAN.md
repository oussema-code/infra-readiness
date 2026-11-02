# Infrastructure Readiness & Recovery Lab

## Objective

Build a small Python CLI that checks whether a lab deployment is usable, explains failures using observed evidence, and runs in CI. The portfolio evidence is reliable automation and reproducible troubleshooting, not production-scale operation.

Initial scope: this standalone tool and its Docker Compose lab. A satellite-platform database recovery exercise is a separate follow-up.

## Version 1

- YAML configuration containing named DNS, TCP, and HTTP checks and expected HTTP status codes.
- Validate the full configuration before performing network requests.
- Explicit per-check time limits, a configurable concurrency limit, and no automatic retries initially.
- DNS resolution must have an enforceable deadline; a socket timeout alone does not bound hostname resolution. Use an isolated, terminable resolver process if needed.
- HTTP checks must not download unlimited bodies or silently follow redirects. Use status checks first; keep application/database verification in the lab's readiness endpoint.
- Result fields: check name/type, target, status, duration, observed evidence, and error category where applicable.
- PASS means the expectation was observed; FAIL means a negative result was observed; UNKNOWN means evidence was insufficient, such as a timeout. Report a timeout as an observed timeout, not a diagnosis of its cause.
- Terminal output and an optional JSON report contain the same results.
- Exit codes: 0 = all pass; 1 = at least one failed check; 2 = unknown results with no failed checks; 3 = invalid configuration or tool execution error. Preserve every result when outcomes are mixed.
- No secret values in example configuration or reports.

## Lab

Use Docker Compose with a small Python API, MariaDB, and a reverse proxy. Run the checker inside the Compose network so service DNS names resolve consistently in local and CI runs.

The API exposes a liveness endpoint and a readiness endpoint that performs a real, bounded database query. This demonstrates why an open TCP port does not prove application readiness. Use disposable synthetic data.

Scenarios:

| Scenario | Expected evidence |
| --- | --- |
| Healthy baseline | All configured checks pass |
| Database stopped | API liveness passes; readiness returns 503; database TCP reports negative or incomplete evidence |
| Invalid service hostname | DNS reports a resolution failure; dependent connection checks retain their own evidence |
| Delayed API response | HTTP result is UNKNOWN with timeout evidence; other checks complete |
| Incorrect proxy upstream | Proxy returns an unexpected status while direct API readiness passes |

Scenario scripts must restore the baseline, including after a test failure. Use isolated Compose project names and wait for readiness rather than fixed sleeps.

## Milestones and acceptance criteria

### 1. Define the interface (implemented) — approximately 2–3 hours

Create package layout, example YAML, documented result schema and exit-code rules. Add configuration parsing and validation tests.

Done when valid configuration loads, malformed configuration produces an actionable error, and invalid input triggers no probes.

### 2. Implement checks and reporting (implemented) — approximately 5–7 hours

Implement DNS, TCP, HTTP, bounded execution, terminal/JSON reports, and outcome aggregation. Start with Python's standard library; YAML parsing needs a dependency. Keep implementation in a few modules without a plugin system.

Test connection refusal, name-resolution failure, unexpected HTTP status, delayed response, malformed HTTP response, mixed outcomes, and concurrency bounds. Use local fixtures and tolerant timing bounds, not public websites.

Done when a stalled target cannot hold the CLI indefinitely, resource cleanup works, and JSON output plus exit codes agree with observed results.

### 3. Build the lab and failure exercises (implemented) — approximately 4–6 hours

Create API/database/proxy services and reproducible commands for each scenario. Include seeded data and one meaningful application query in readiness verification.

Done when every scenario produces its documented evidence and returning to the baseline makes checks pass again.

### 4. Run the evidence in CI (implemented and verified) — approximately 2–4 hours

Run unit tests and Compose integration scenarios in GitHub Actions. Always clean up lab resources and upload diagnostic reports on failure.

Expected lab failures must be asserted by the integration harness: the CI job passes only when the tool reports the expected failure or uncertainty. Avoid swallowing arbitrary errors with `|| true`.

Done when a clean checkout can reproduce the tests using documented commands and a regression in diagnosis or exit codes fails CI.

### 5. Package the portfolio evidence (implemented) — approximately 2–3 hours

Write a concise README with purpose, architecture, quick start, one sample report, scenario instructions, and limitations. Add two incident notes covering symptoms, evidence, diagnosis, recovery, and verification. Record a short terminal demo if useful.

Done when another person can reproduce a healthy run and one failure exercise without private infrastructure. Add resume bullets only for completed, verified behavior; record any metrics with their actual lab conditions.

Estimated total: 15–23 focused hours, with extra time for unfamiliar networking or CI issues. Treat this as an estimate, not a deadline.

## Follow-up after version 1

Restore a satellite-platform database backup into a clean environment; verify records and application behavior, and document measured recovery under stated lab conditions. Keep this separate from basic readiness checks.

## Deliberately outside version 1

Kubernetes deployment, Terraform, Ansible, Ceph, GPUs, a dashboard, continuous monitoring, automatic remediation, service-version discovery, authentication flows, and a generic extension framework. Add a capability only when a concrete target or demonstrated need justifies it.

## Next implementation task

Use `docs/WALKTHROUGH.md` to practice explaining the implementation and tradeoffs. Future specialization and satellite-platform backup restoration remain separate follow-up projects.

## Implementation progress — 2026-11-02

- Exact upstream source and license recorded in `lab/UPSTREAM.md`; MariaDB reused from its topology.
- Configuration validation, DNS/TCP/HTTP probes, bounded asynchronous process runner, terminal/JSON reporting, and CI exit codes implemented.
- Deadlines include name resolution, worker startup, connection, TLS, and HTTP headers; timed-out workers are killed and reaped.
- Containerized checker can access both lab networks without database credentials or Docker socket access.
- Automated baseline plus database-outage, invalid-hostname, delayed-response, and broken-proxy exercises implemented, each followed by a passing recovery baseline. Unique project names, ephemeral ports, reports, logs, and cleanup retained.
- Public repository: https://github.com/oussema-code/infra-readiness. GitHub Actions passed the Python 3.11/3.13 matrix and complete Docker lab: https://github.com/oussema-code/infra-readiness/actions/runs/41499281433.
- Evidence-backed notes added in `docs/database-outage.md` and `docs/diagnostic-scenarios.md`.
- Recorded demo, raw sample evidence, MIT license, and interview walkthrough added. All version 1 milestones are complete.

### Verification

- 75 configuration, result, CLI, network, deadline, lifecycle, and concurrency tests passed locally on Python 3.14.4.
- 3 API unit tests passed, including the lab-only delayed endpoint (sleep and database calls mocked).
- Three Docker images built; full Compose baseline/outage/recovery verified with the checker on Python 3.13.
- Baseline: 5 PASS, exit 0. Database outage: 1 PASS, 2 FAIL, 2 UNKNOWN, exit 1. Recovery: 5 PASS, exit 0.
- Temporary resolver errors during the database outage were retained as UNKNOWN instead of permanent DNS failures.
- Expanded Docker run `readiness-smoke-732b0515` verified all four exercises and recovery: invalid hostname = 1 PASS / 1 FAIL (exit 1); delayed response = 1 PASS / 1 UNKNOWN (exit 2); broken proxy = 4 PASS / 1 FAIL (exit 1). Each subsequent five-check baseline passed (exit 0).
- Compose configuration validated. The smoke harness cleans up its containers, networks, and synthetic database volume.
- GitHub run 41499281433 passed both Python 3.11/3.13 jobs (78 tests each) and all four Docker failure/recovery exercises. Reports and logs were uploaded and downloaded for verification. Windows/macOS are untested.
- Repository published on GitHub with an initial commit and `origin/main` tracking. Resume artifacts remain outside the public repository.
