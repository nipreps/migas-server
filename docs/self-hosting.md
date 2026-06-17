# Self-Hosting A Migas Server

Run `migas-server` on your own host — bare metal or a VM — without Docker
Compose. You provide PostgreSQL and Redis; you install with
[`uv`](https://docs.astral.sh/uv/), create the schema with Alembic, and run the
server under `systemd` behind a reverse proxy.

> [!NOTE]
> For a quick local spin-up, use the [Docker Compose](getting-started.md) guide
> instead.

## Contents

1. [Architecture & prerequisites](#1-architecture--prerequisites)
2. [Install the application](#2-install-the-application)
3. [Provision PostgreSQL](#3-provision-postgresql)
4. [Provision Redis](#4-provision-redis)
5. [Initialize the database schema](#5-initialize-the-database-schema)
6. [Run the server](#6-run-the-server)
7. [Run under systemd](#7-run-under-systemd)
8. [Reverse proxy & TLS](#8-reverse-proxy--tls)
9. [Set up admin access](#9-set-up-admin-access)
10. [Upgrades](#10-upgrades)

---

## 1. Architecture & prerequisites

`migas-server` is an ASGI (FastAPI) app. A self-hosted deployment has three
parts you provide:

| Component | Role | You provide |
|---|---|---|
| **PostgreSQL** | Persists projects, users, telemetry crumbs, and auth tokens | A reachable database + role |
| **Redis** (≥ 6) | Rate limiting and GitHub API caching | A reachable Redis instance |
| **migas-server** | The ASGI app, run with `uvicorn` | This repository + Python |

It can also use MaxMind-format geolocation databases (see
[Configuration](configuration.md#geolocation)).

**Host requirements:**

- Python **3.10+** (3.13 is what the official image ships; any 3.10+ works)
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Network access from the host to your Postgres and Redis
- A reverse proxy (e.g. nginx) if you want TLS termination — recommended

---

## 2. Install the application

```bash
git clone https://github.com/nipreps/migas-server.git
cd migas-server

# Install runtime dependencies + Alembic (the `prod` extra pulls in `migrations`).
uv sync --extra prod
```

Optional extras:

- `--extra speedups` — adds `aiohttp[speedups]` and `redis[hiredis]` (C
  acceleration). Recommended for production.
- `--extra prod` — already includes the `migrations` extra (Alembic), required
  for schema setup and upgrades.

`uv sync` creates a project virtual environment at `.venv/`. The `migas-server`
console script and `alembic` are available via `uv run …` (or by activating the
venv).

---

## 3. Provision PostgreSQL

Create a database and a role the server will use:

```sql
CREATE ROLE migas WITH LOGIN PASSWORD 'change-me';
CREATE DATABASE migas OWNER migas;
```

Point the server at it with `DATABASE_URL` (required for any non-local database).
See [Configuration → Database](configuration.md#database) for the connection
variables and an important caveat about remote hosts.

---

## 4. Provision Redis

Redis is required, for rate limiting and GitHub-project caching. Point the server
at it with `MIGAS_REDIS_URI` (or `REDIS_TLS_URL` for a `rediss://` endpoint); see
[Configuration → Redis](configuration.md#redis).

---

## 5. Initialize the database schema

**Use Alembic migrations.** This is the version-tracked way to create and update
the schema. From the repo root, with your database variables set (see
[Configuration](configuration.md)):

```bash
uv run alembic upgrade head
```

Alembic reads the same variables as the server (via `alembic/env.py`) and loads a
`.env` file automatically. To point at a specific env file:

```bash
MIGAS_ENV_FILE=/etc/migas/migas.env uv run alembic upgrade head
```

This builds the `migas` schema and tables (`projects`, `users`, `crumbs`,
`auth`, `geoloc`). Re-running it after a `git pull` applies new migrations (see
[§10](#10-upgrades)).

**Or `init.sql`.** The repo ships
[`deploy/docker/init.sql`](https://github.com/nipreps/migas-server/blob/main/deploy/docker/init.sql), which creates the same
core tables in one shot:

```bash
psql "postgresql://migas:change-me@localhost:5432/migas" -f deploy/docker/init.sql
```

> [!WARNING]
> `init.sql` is intended for local development. It seeds a `master` project
> and two **publicly known test tokens**. If you use it for anything real, delete
> those seeded rows immediately and bootstrap your own master token
> ([§9](#9-set-up-admin-access)). It also is not revision-aware — Alembic won't
> know what state the database is in. Prefer `alembic upgrade head`.

---

## 6. Run the server

Launch the server with the `migas-server` console script, a thin wrapper over
`uvicorn`:

```bash
uv run migas-server --host 0.0.0.0 --port 8080 --proxy-headers
```

Flags:

| Flag | Default | Notes |
|---|---|---|
| `--host` | `0.0.0.0` | Bind address. Bind to `127.0.0.1` if a reverse proxy is in front. |
| `--port` | `8000` | Listen port. |
| `--proxy-headers` | off | **Enable when behind a reverse proxy** so client IPs/scheme are read from `X-Forwarded-*`. |
| `--workers` | `1` | Worker processes. |
| `--headers` | — | Extra `Name:Value` response headers. |

> [!NOTE]
> Run it behind a reverse proxy ([§8](#8-reverse-proxy--tls)) rather than
> exposing uvicorn to the internet directly.

Check it responds. A `401` here is expected — the endpoint needs a token — and
confirms the server is up:

```bash
curl -i http://127.0.0.1:8080/api/auth/projects
```

---

## 7. Run under systemd

Create an env file at `/etc/migas/migas.env` with the variables from
[Configuration](configuration.md), e.g.:

```env
DATABASE_URL=postgresql+asyncpg://migas:change-me@localhost:5432/migas
MIGAS_REDIS_URI=redis://:password@localhost:6379
MIGAS_GEOLOC=1
MIGAS_GEOLOC_DIR=/path/to/geodb
```

Create a service unit at `/etc/systemd/system/migas-server.service`:

```ini
[Unit]
Description=migas telemetry server
After=network-online.target postgresql.service redis.service
Wants=network-online.target

[Service]
Type=simple
User=migas
Group=migas
WorkingDirectory=/opt/migas-server
EnvironmentFile=/etc/migas/migas.env
ExecStart=/usr/bin/uv run migas-server --host 127.0.0.1 --port 8080 --proxy-headers
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Adjust `WorkingDirectory`, `User`, and the path to `uv` (`which uv`) for your
host. Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now migas-server
sudo systemctl status migas-server
journalctl -u migas-server -f
```

---

## 8. Reverse proxy & TLS

Terminate TLS at a reverse proxy and forward to uvicorn on `127.0.0.1`. Minimal
nginx config:

```nginx
server {
    listen 443 ssl;
    server_name migas.example.org;

    ssl_certificate     /etc/letsencrypt/live/migas.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/migas.example.org/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

With `--proxy-headers`, uvicorn honors the `X-Forwarded-*` headers above. Only
forward them from a proxy you trust.

---

## 9. Set up admin access

A fresh database has no admin credential. Bootstrap the master token by running
the [bootstrap script](administration.md#bootstrap-the-master-token) from the
repo root, with the server's environment:

```bash
uv run python scripts/bootstrap_admin_token.py
# or with an explicit env file:
MIGAS_ENV_FILE=/etc/migas/migas.env uv run python scripts/bootstrap_admin_token.py
```

Save the printed token. With it you can register projects and issue scoped
tokens — see [Administration](administration.md) for the token model and the
full admin API.

---

## 10. Upgrades

To update a running instance:

```bash
cd /opt/migas-server
git pull
uv sync --extra prod          # update dependencies
uv run alembic upgrade head   # apply any new migrations
sudo systemctl restart migas-server
```

Always run `alembic upgrade head` after pulling; releases may add migrations.
Check the [CHANGELOG](https://github.com/nipreps/migas-server/blob/main/CHANGELOG.md) before big version jumps.
