# Implementation walkthrough

## A two-minute explanation

This project checks whether deployment targets meet explicit expectations. A YAML
file describes DNS, TCP, and HTTP checks; the CLI validates the entire file before
network activity, executes bounded probe workers, and produces human-readable and
JSON evidence with CI-friendly exit codes.

The lab provides a real database-backed readiness route and a separate liveness
route. The failure harness tests a stopped database, an invalid hostname, a slow
HTTP fixture, and an incorrect proxy upstream. It checks the expected evidence,
restores the baseline after each case, and cleans up its isolated Compose project.

## Trace one check through the code

1. `cli.py` parses `run` or `validate` and delegates configuration loading.
2. `config.py` rejects malformed YAML, duplicate keys/names, unsupported fields,
   invalid types, and out-of-range settings. It creates immutable check definitions.
3. `runner.py` queues checks behind a semaphore and launches one subprocess per
   active check. The timeout begins after queue admission and includes startup.
4. `worker.py` performs DNS resolution, a TCP connection, or a status-only HTTP GET.
   It classifies observed failures separately from incomplete evidence.
5. `runner.py` kills and reaps timed-out workers and preserves configuration order.
6. `report.py` renders the results. `models.py` applies exit-code precedence:
   tool errors, then failures, then unknown outcomes, then all-pass.

## Design questions to be ready for

**Why a subprocess per check?** A socket timeout does not necessarily bound name
resolution, and a peer can keep sending header bytes to prolong an operation.
The parent can terminate the entire probe. Startup and memory overhead make this
a deliberate tradeoff for a small CI validator; the configuration caps concurrency
at 32 and the number of checks at 100.

**What does a timeout prove?** Only that the configured deadline expired without
sufficient evidence. It cannot distinguish slow service, network delay, a stalled
resolver, or a busy local machine. The result is UNKNOWN, not a diagnosis.

**What does PASS prove?** Exactly the configured observation. An open TCP port
does not prove application readiness; an HTTP status does not verify response
body completeness. The lab's readiness endpoint separately checks expected data.

**Why compare direct API and proxy readiness?** Direct success with proxy failure
narrows the failing path. In the exercise, the wrong upstream port is known
because the harness introduced it; HTTP 502 by itself does not prove that cause.

**What is reused?** The lab topology and application/proxy foundation came from
Docker's Awesome Compose sample. The tool, validation and execution model, reports,
tests, failure harness, and lab adaptations are project additions. Upstream
provenance and its CC0 dedication are included.

**What remains limited?** Single-host synthetic lab, development API server,
status-only HTTP checks, public test passwords, and unpinned image tags. There is
no production access, availability claim, automatic remediation, GPU work, or
backup-restoration evidence.

## Evidence to show

- The CI run for the same commit, including both Python test jobs and Compose job.
- `docs/demo/` for the recorded sample and its underlying JSON results.
- `docs/database-outage.md` and `docs/diagnostic-scenarios.md` for investigations.
- Tests for stalled resolution, slow HTTP headers, cancellation/reaping, malformed
  responses, report consistency, and concurrency bounds.
