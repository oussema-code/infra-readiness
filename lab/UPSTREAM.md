# Lab provenance

Adapted from Docker's Awesome Compose `nginx-flask-mysql` sample:
https://github.com/docker/awesome-compose/tree/30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562/nginx-flask-mysql

Retrieved 2026-11-02. Upstream commit: `30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562`.
Upstream dedication: CC0 1.0 Universal; full text is in LICENSE.upstream.
The upstream sample is named MySQL but defaults to MariaDB.

Retained: three-service API/database/proxy structure, Compose networks and storage,
Flask application foundation, and NGINX upstream routing.

Adaptations: updated image families and Python dependencies; removed development
image extras, restart policies, root application database access, and database
initialization from request handling. Added disposable SQL seed data, independent
liveness and database-backed readiness routes, bounded database I/O, startup health
checks, a delayed-readiness fixture, a deliberately broken proxy configuration,
and a loopback-only proxy port. The database and API have no host ports.
The API and Compose configuration were substantially rewritten for these exercises.

The CLI, configuration schema, result model, tests, and automated failure exercises
are project additions. This lab uses public test passwords and Flask's development
server with debugging disabled. It is not a production deployment template.
