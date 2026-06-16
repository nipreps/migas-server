# Getting Started with Docker Compose

The Docker Compose stack runs a full local instance — server, PostgreSQL, and
Redis — with the schema and an admin token already seeded. Good for development
and trying out the API.

> [!NOTE]
> Running a persistent instance you control (your own Postgres/Redis, no
> Compose)? See the [self-hosting guide](self-hosting.md) instead.

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Start the stack](#2-start-the-stack)
3. [What you get](#3-what-you-get)
4. [Register a project](#4-register-a-project)
5. [Send your first breadcrumb](#5-send-your-first-breadcrumb)
6. [Use the admin API](#6-use-the-admin-api)
7. [View the dashboard](#7-view-the-dashboard)
8. [Live reload during development](#8-live-reload-during-development)
9. [Stop the stack](#9-stop-the-stack)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites

- **Docker** with the **Compose** plugin (`docker compose …`)
- **make**
- **hatch** — the build reads the version from `hatch version`. If you don't
  have it: `uv tool install hatch` (or `pipx install hatch`).

Everything runs in containers; no local Python, Postgres, or Redis needed.

---

## 2. Start the stack

From the repository root:

```bash
make compose-up
```

This runs two steps (see the [Makefile](https://github.com/nipreps/migas-server/blob/main/Makefile)):

1. `docker build` — builds the `migas-server:latest` image.
2. `docker compose up --detach` — starts the server, Postgres, and Redis in the
   background.

The first build takes a few minutes; subsequent runs are cached.

---

## 3. What you get

The stack ([`docker-compose.yml`](https://github.com/nipreps/migas-server/blob/main/docker-compose.yml)) brings up three
services with these host ports:

| Service | Container | Host port | Notes |
|---|---|---|---|
| **migas-server** | `migas-server` | `8081` → 8080 | The API + dashboard. |
| **PostgreSQL** | `postgres` | `5433` → 5432 | User `postgres`, password `crumbs`, database `migas`. |
| **Redis** | `redis` | `6380` → 6379 | No password. |

> [!NOTE]
> The host ports are offset (8081/5433/6380) so they don't clash with a local
> Postgres/Redis. See [troubleshooting](#10-troubleshooting) to change them.

On first start, Postgres runs [`deploy/docker/init.sql`](https://github.com/nipreps/migas-server/blob/main/deploy/docker/init.sql),
which creates the `migas` schema and tables and seeds:

- Two registered projects: **`master`** and **`nipreps/nipreps`**
- A working **master (admin) token: `my_test_token`**
- A `nipreps/nipreps` project token: `m_nipreps`

> [!WARNING]
> These tokens are public and for **local development only**. Never expose
> this stack to the internet or reuse these tokens anywhere real.

Check it's up. This endpoint needs the master token and lists the registered
projects:

```bash
curl -H "Authorization: Bearer my_test_token" http://localhost:8081/api/auth/projects
# {"projects":["master","nipreps/nipreps"]}
```

Without a valid token it returns `401`, which still tells you the server is
running.

---

## 4. Register a project

A project must be registered before it can receive telemetry. The stack seeds
`nipreps/nipreps`; add your own with the master token (registration is
admin-only), using the `owner/repo` form:

```bash
export TOKEN=my_test_token

curl -X POST http://localhost:8081/api/admin/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project": "my-org/my-tool"}'
# {"success":true,"message":"Project is now registered."}
```

---

## 5. Send your first breadcrumb

A breadcrumb is a single telemetry ping. It needs no token, but the project must
already be registered — use `my-org/my-tool` from the last step, or the seeded
`nipreps/nipreps`. `?wait=true` ingests synchronously; without it the call
returns `202` and ingestion runs in the background:

```bash
curl -X POST "http://localhost:8081/api/breadcrumb?wait=true" \
  -H "Content-Type: application/json" \
  -d '{
    "project": "my-org/my-tool",
    "project_version": "1.0.0",
    "language": "python",
    "language_version": "3.11",
    "ctx": {"platform": "linux", "is_ci": false},
    "proc": {"status": "C"}
  }'
```

Response:

```json
{ "success": true, "message": "" }
```

The `proc.status` values map to: `R` (running), `C` (completed), `F` (failed),
`S` (suspended).

> [!TIP]
> The `curl` above just shows the endpoint. Python packages can use
> [migas-py](https://github.com/nipreps/migas-py), which builds and sends
> breadcrumbs for you (fire-and-forget, fingerprinting, opt-out, CI detection).
> Point it at your instance via its endpoint config.

---

## 6. Use the admin API

Admin endpoints live under `/api/admin/` and require the master token
(`my_test_token` here, exported as `$TOKEN` in [4](#4-register-a-project)).
Besides [registering projects](#4-register-a-project), you can issue and manage
scoped tokens.

A scoped token is tied to one project and grants read access to that project
only:

- Its usage statistics via `GET /api/usage/{owner}/{repo}`.
- That project (and nothing else) in the [dashboard](#7-view-the-dashboard)
  selector and `GET /api/auth/projects`.

It can't reach other projects or the admin endpoints; those need the master
token. Sending breadcrumbs needs no token at all, so scoped tokens are for
reading usage, not ingesting.

**Issue a scoped project token** (returned once, in plaintext):

```bash
curl -X POST http://localhost:8081/api/admin/issue-token \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project": "my-org/my-tool", "description": "local test"}'
```

**List tokens** (filter by `?project=owner/repo`):

```bash
curl "http://localhost:8081/api/admin/list-tokens?project=my-org/my-tool" \
  -H "Authorization: Bearer $TOKEN"
```

See the [self-hosting guide](self-hosting.md#12-administration-projects--tokens)
for full admin endpoint details.

### Change the master token

`my_test_token` is public, so replace it before relying on this stack for
anything beyond local dev. The API can't issue or revoke master tokens, so use
the bootstrap script
([`scripts/bootstrap_admin_token.py`](https://github.com/nipreps/migas-server/blob/main/scripts/bootstrap_admin_token.py)) with
`--rotate`. Run it inside the server container, where the database connection is
already configured:

```bash
docker compose exec migas-server \
  python /src/scripts/bootstrap_admin_token.py --rotate
```

It prints a new token; save it, it can't be recovered. The old `my_test_token`
stops working at once. To bake a different one into fresh stacks instead, edit
the seeded hash in [`deploy/docker/init.sql`](https://github.com/nipreps/migas-server/blob/main/deploy/docker/init.sql) and
recreate the volume ([9](#9-stop-the-stack)).

---

## 7. View the dashboard

Open the usage visualization in a browser:

```
http://localhost:8081/viz/
```

After sending a few breadcrumbs for a project, you can chart its usage there.

---

## 8. Live reload during development

The stack mounts your working tree into the container and runs uvicorn with
`--reload`, so source edits are picked up automatically. In watch mode, changes
to `pyproject.toml`, `uv.lock`, or the `Dockerfile` also trigger a rebuild:

```bash
docker compose watch
```

Set environment knobs in the `environment:` block of
[`docker-compose.yml`](https://github.com/nipreps/migas-server/blob/main/docker-compose.yml): `MIGAS_BYPASS_RATE_LIMIT`,
`MIGAS_GEOLOC`, the rate-limit variables, and so on. The
[configuration reference](self-hosting.md#6-configuration-reference) lists them
all.

---

## 9. Stop the stack

```bash
make compose-down
```

Postgres data persists in `./mounts/db` between runs. To start fresh (re-run
`init.sql`, wipe all telemetry), delete it while the stack is down:

```bash
make compose-down
rm -rf mounts/db
make compose-up
```

---

## 10. Troubleshooting

**Port already in use (5433, 6380, or 8081).** You likely have a local Postgres
or Redis running. If they were installed via Homebrew, stop them with the helper
script:

```bash
.maint/services stop
```

(`.maint/services start` brings them back.) Otherwise stop the conflicting
service, or change the mapping: edit the service's `ports:` entry in
[`docker-compose.yml`](https://github.com/nipreps/migas-server/blob/main/docker-compose.yml) — the value is `"HOST:CONTAINER"`,
so adjust the **left** number only (e.g. `"9090:8080"` to serve the API on
`localhost:9090`). Leave the container port unchanged, then re-run
`make compose-up` to apply.

**`hatch: command not found` during `make compose-up`.** The build needs `hatch`
to compute the version. Install it with `uv tool install hatch` and retry.

**Database changes not taking effect.** `init.sql` only runs the first time the
Postgres data directory is created. After schema changes, recreate the volume as
shown in [9](#9-stop-the-stack).
