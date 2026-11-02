# Distinguishing target errors, timeouts, and proxy failures

These are deliberate local Docker exercises with synthetic data. Reproduce all
cases with `.venv/bin/python scripts/lab_smoke.py`. Reports are saved under
`reports/<random-project>/`, alongside service and Compose logs.

Verified on 2026-11-02 in run `readiness-smoke-732b0515`: invalid hostname
produced 1 PASS / 1 FAIL (exit 1); delayed response produced 1 PASS / 1 UNKNOWN
(exit 2); broken proxy produced 4 PASS / 1 FAIL (exit 1). All five baseline
checks passed after each scenario.

## Invalid hostname: negative evidence versus an unavailable answer

The checker configuration substitutes `absent.invalid` for the DNS target while
retaining a direct API liveness check. The hostname is deliberately invalid; what
the checker can establish still depends on the resolver's response.

A definitive no-address response is FAIL with `dns_not_found`. A temporary resolver
error is UNKNOWN with `dns_error`; deadline exhaustion is UNKNOWN with `timeout`.
The harness checks these allowed status/category pairs and requires API liveness
to pass. It rejects tool errors, unexpected passes, and unrelated liveness failures.

Recovery consists of selecting the original five-check configuration and requiring
all checks to pass. No DNS server or application configuration is modified.

## Delayed API: incomplete evidence does not prove an outage

The lab provides `/slow-ready`, which waits three seconds before running the same
query used by `/ready`. A dedicated checker configuration gives this endpoint a
one-second deadline and checks `/live` concurrently.

Expected evidence: delayed readiness is UNKNOWN with `timeout`, liveness is PASS,
and the command exits 2. This demonstrates that the stalled check does not prevent
the healthy check from completing. The checker kills and reaps its timed-out
worker; the API can continue its own request processing after the client leaves.

Recovery selects the original `/ready` target and requires all five baseline checks
to pass. The slow route remains an explicit test fixture; this exercise does not
claim that a real degraded service was repaired or that timed-out server work was
cancelled.

## Incorrect proxy upstream: locate failure at a boundary

The harness copies `lab/proxy/broken.conf` into its own NGINX container, validates
its syntax, and reloads it. The file points to `backend:1` instead of `backend:8000`.
It polls the published proxy endpoint until HTTP 502 is observed, avoiding a race
with the asynchronous reload.

The checker must observe:

| Target | Required result |
| --- | --- |
| Database DNS and TCP | PASS |
| Direct API liveness and readiness | PASS |
| Proxied readiness | FAIL, HTTP 502, `http_status` |

The difference between direct and proxied readiness isolates the failing path.
HTTP 502 alone would not establish that a wrong port was the root cause; that
cause is known here because the harness introduced it, and proxy logs provide
supporting evidence.

In a `finally` block, the harness copies the original `lab/proxy/conf` back,
validates it, reloads NGINX, polls for HTTP 200, and requires all five checks to
pass. It then saves logs and removes its own containers, networks, and database
volume. The original development lab is untouched.
