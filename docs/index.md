# migas-server

Migas is a telemetry web service that collects, aggregates, and displays
software usage. The NiPreps organization runs a public instance at
[migas.nipreps.org](https://migas.nipreps.org).

## Deployment

Pick how you want to run the server:

- **[Getting started with Docker Compose](getting-started.md)** — a full local
  instance for development or evaluation.
- **[Self-hosting](self-hosting.md)** — a persistent instance on your own host,
  with your own Postgres and Redis.
- **[Cloud hosting (GCP)](cloud-hosting.md)** — running it as a managed service
  on Cloud Run + Cloud SQL, the setup used in production.

## Operations

Applies to any deployment:

- **[Configuration](configuration.md)** — environment variables.
- **[Administration](administration.md)** — tokens, registering projects, the
  admin API.
- **[Usage](usage.md)** — sending breadcrumbs and viewing the dashboard.

To send telemetry from a Python application, see the
[migas-py](https://github.com/nipreps/migas-py) client.
