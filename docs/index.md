# migas-server

Migas is a telemetry web service that collects, aggregates, and displays
software usage. The NiPreps organization runs a public instance at
[migas.nipreps.org](https://migas.nipreps.org).

These docs cover the various deployment options.

## Guides

- **[Getting started with Docker Compose](getting-started.md)** — a full local
  instance for development or evaluation.
- **[Self-hosting](self-hosting.md)** — a persistent instance on your own host,
  with your own Postgres and Redis.
- **[Cloud hosting (GCP)](cloud-hosting.md)** — running it as a managed service
  on Cloud Run + Cloud SQL, the setup used in production.

To send telemetry from a Python application, see the
[migas-py](https://github.com/nipreps/migas-py) client.
