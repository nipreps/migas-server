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
4. [First steps](#4-first-steps)
5. [Live reload during development](#5-live-reload-during-development)
6. [Stop the stack](#6-stop-the-stack)
7. [Troubleshooting](#7-troubleshooting)

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
> Postgres/Redis. See [troubleshooting](#7-troubleshooting) to change them.

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

## 4. First steps

The stack seeds the master token `my_test_token` and the `nipreps/nipreps`
project, so you can exercise the API right away. Using `http://localhost:8081`
as the instance URL and `my_test_token` as the master token:

- [Register a project](administration.md#register-a-project) and
  [issue tokens](administration.md#issue-a-project-token).
- [Send a breadcrumb](usage.md#send-a-breadcrumb) and
  [view the dashboard](usage.md#view-the-dashboard) at
  <http://localhost:8081/viz/>.

### Rotate the seeded token

`my_test_token` is public, so replace it before relying on this stack for
anything beyond local dev. Run the
[bootstrap script](administration.md#bootstrap-the-master-token) inside the
server container, where the database connection is already configured:

```bash
docker compose exec migas-server \
  python /src/scripts/bootstrap_admin_token.py --rotate
```

It prints a new token; save it, it can't be recovered. The old `my_test_token`
stops working at once. To bake a different one into fresh stacks instead, edit
the seeded hash in [`deploy/docker/init.sql`](https://github.com/nipreps/migas-server/blob/main/deploy/docker/init.sql) and
recreate the volume ([§6](#6-stop-the-stack)).

---

## 5. Live reload during development

The stack mounts your working tree into the container and runs uvicorn with
`--reload`, so source edits are picked up automatically. In watch mode, changes
to `pyproject.toml`, `uv.lock`, or the `Dockerfile` also trigger a rebuild:

```bash
docker compose watch
```

Environment knobs go in the `environment:` block of
[`docker-compose.yml`](https://github.com/nipreps/migas-server/blob/main/docker-compose.yml);
see the [configuration reference](configuration.md).

---

## 6. Stop the stack

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

## 7. Troubleshooting

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
shown in [§6](#6-stop-the-stack).
