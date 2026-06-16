# Migas

Migas is a telemetry web service that collects, aggregates, and displays software usage.

Developers can leverage migas to:
- Monitor software usage, including (somewhat) unique users.
- Communicate with users using legacy/deprecated version.
- Generate interactive graphs with usage statistics.

## NiPreps hosted server

The NiPreps organization hosts [an official instance](https://migas.nipreps.org/) of this service.

For developers wishing to spin-up their own server:

- **[Getting started with Docker Compose](docs/getting-started.md)** — the fastest way to run a local instance for development or evaluation.
- **[Self-hosting guide](docs/self-hosting.md)** — running a persistent instance on your own host with your own Postgres and Redis.
- **[Cloud hosting (GCP)](docs/cloud-hosting.md)** — running it as a managed service on Cloud Run + Cloud SQL, the setup used in production.


## Usage Monitoring

Authenticated users can view their projects' usage at https://migas.nipreps.org/viz/.
