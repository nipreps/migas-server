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
6. [Configuration reference](#6-configuration-reference)
7. [Geolocation databases (optional)](#7-geolocation-databases-optional)
8. [Run the server](#8-run-the-server)
9. [Run under systemd](#9-run-under-systemd)
10. [Reverse proxy & TLS](#10-reverse-proxy--tls)
11. [Bootstrap the first admin token](#11-bootstrap-the-first-admin-token)
12. [Administration: projects & tokens](#12-administration-projects--tokens)
13. [Upgrades](#13-upgrades)

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
[7](#7-geolocation-databases-optional)).

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

The server builds its connection URL one of two ways. **Which one you use
matters for remote databases:**

### Option A — `DATABASE_URL` (recommended for any non-local database)

Set a single connection string. The driver is always coerced to
`postgresql+asyncpg`, so you can supply a plain `postgresql://` URL:

```env
DATABASE_URL=postgresql+asyncpg://migas:change-me@db.example.org:5432/migas
```

### Option B — discrete variables

```env
DATABASE_USER=migas
DATABASE_PASSWORD=change-me
DATABASE_NAME=migas
```

> [!IMPORTANT]
> With discrete variables, the **runtime** connection
> (`connections.py`) does *not* read a host or port — it connects to the local
> default (Unix socket / `localhost:5432`). If your database is on another host,
> you **must** use `DATABASE_URL` (Option A). The discrete-variable form is only
> suitable when Postgres is local to the server.
>
> (Alembic's `env.py` *does* honor optional `DATABASE_HOST`/`DATABASE_PORT`, so
> migrations can reach a remote DB with discrete vars — but the running server
> will not. Use `DATABASE_URL` everywhere to avoid surprises.)

---

## 4. Provision Redis

Redis is required, for rate limiting and GitHub-project caching. Point the server
at it with:

```env
MIGAS_REDIS_URI=redis://:password@redis.example.org:6379
```

For a TLS endpoint you may instead set `REDIS_TLS_URL` (a `rediss://…` URL).
When both are set, `REDIS_TLS_URL` takes precedence.

---

## 5. Initialize the database schema

**Use Alembic migrations.** This is the version-tracked way to create and update
the schema. From the repo root, with your database variables set (see
[6](#6-configuration-reference)):

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
[13](#13-upgrades)).

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
> ([11](#11-bootstrap-the-first-admin-token)). It also is not revision-aware —
> Alembic won't know what state the database is in. Prefer `alembic upgrade head`.

---

## 6. Configuration reference

The server is configured entirely through environment variables. Put them in an
env file (e.g. `/etc/migas/migas.env`) referenced by your `systemd` unit.

### Database

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | Full connection URL. Coerced to `postgresql+asyncpg`. Use this for any remote DB. |
| `DATABASE_USER` | — | Used only if `DATABASE_URL` is unset. |
| `DATABASE_PASSWORD` | — | Used only if `DATABASE_URL` is unset. |
| `DATABASE_NAME` | — | Used only if `DATABASE_URL` is unset. |
| `DATABASE_HOST` | `localhost` | **Alembic only** — the running server ignores this. |
| `DATABASE_PORT` | `5432` | **Alembic only** — the running server ignores this. |
| `GCP_SQL_CONNECTION` | — | GCP Cloud SQL socket path. Leave unset when self-hosting. |

### Redis

| Variable | Default | Notes |
|---|---|---|
| `MIGAS_REDIS_URI` | — | **Required.** `redis://[:password@]host:port`. |
| `REDIS_TLS_URL` | — | TLS endpoint (`rediss://…`). Takes precedence over `MIGAS_REDIS_URI`. |

### Rate limiting & request size

| Variable | Default | Notes |
|---|---|---|
| `MIGAS_REQUEST_WINDOW` | `60` | Sliding-window length in seconds. |
| `MIGAS_MAX_REQUESTS_PER_WINDOW` | `100` | Allowed requests per window per client. |
| `MIGAS_MAX_REQUEST_SIZE` | `2500` | Max request body size in bytes. |
| `MIGAS_BYPASS_RATE_LIMIT` | unset | Set to any non-empty value to disable rate limiting (not recommended in prod). |

### Geolocation

| Variable | Default | Notes |
|---|---|---|
| `MIGAS_GEOLOC` | unset | Set to `1`/`true` to enable IP geolocation. |
| `MIGAS_GEOLOC_DIR` | `.` | Directory containing `city.mmdb` and `asn.mmdb`. |

### Misc

| Variable | Default | Notes |
|---|---|---|
| `MIGAS_DEV` | unset | Enables SQLAlchemy SQL echo. **Never set in production.** |

---

## 7. Geolocation databases (optional)

Geolocation tags telemetry with coarse city/ASN info. The server reads two
MaxMind-format files, `city.mmdb` and `asn.mmdb`, from `MIGAS_GEOLOC_DIR` (bring
your own).

Download them (hosted on OSF, no MaxMind key needed):

```bash
uv run scripts/download_geodbs.py /var/lib/migas/geodb
```

Then enable the feature:

```env
MIGAS_GEOLOC=1
MIGAS_GEOLOC_DIR=/var/lib/migas/geodb
```

With `MIGAS_GEOLOC` unset, the files aren't needed and geolocation is skipped.

---

## 8. Run the server

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
> Run it behind a reverse proxy ([10](#10-reverse-proxy--tls)) rather than
> exposing uvicorn to the internet directly.

Check it responds. A `401` here is expected — the endpoint needs a token — and
confirms the server is up:

```bash
curl -i http://127.0.0.1:8080/api/auth/projects
```

---

## 9. Run under systemd

Create an env file at `/etc/migas/migas.env` with the variables from
[6](#6-configuration-reference), e.g.:

```env
DATABASE_URL=postgresql+asyncpg://migas:change-me@localhost:5432/migas
MIGAS_REDIS_URI=redis://:password@localhost:6379
MIGAS_GEOLOC=1
MIGAS_GEOLOC_DIR=/var/lib/migas/geodb
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

## 10. Reverse proxy & TLS

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

## 11. Bootstrap the first admin token

Every `/api/admin/*` endpoint requires a master token (an admin token whose
project is `master`). The API can't create master tokens, so a fresh database
has none; create the first with the bootstrap script.

[`scripts/bootstrap_admin_token.py`](https://github.com/nipreps/migas-server/blob/main/scripts/bootstrap_admin_token.py)
generates a token, stores its BLAKE2b hash, ensures the `master` project row
exists, and prints the raw token once. It's short and reuses the server's own
hashing and database code, so read it first if you'd rather run the steps by
hand. Run it from the repo root with the server's `DATABASE_URL` / `DATABASE_*`
variables:

```bash
uv run python scripts/bootstrap_admin_token.py
# or with an explicit env file:
MIGAS_ENV_FILE=/etc/migas/migas.env uv run python scripts/bootstrap_admin_token.py
```

It prints the token once; save it, it can't be recovered from the database:

```
Master token created. Save it now — it cannot be recovered:

    m_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

Use it as a bearer token:  Authorization: Bearer <token>
```

If a master token already exists the script refuses to run. Add `--rotate` to
replace it; the old token stops working at once:

```bash
uv run python scripts/bootstrap_admin_token.py --rotate
```

---

## 12. Administration: projects & tokens

All admin endpoints are under `/api/admin/` and require the master token:

```
Authorization: Bearer m_PASTE_YOUR_RAW_TOKEN
```

Never pass tokens as URL parameters.

### Register a project

A project must be registered before it can receive telemetry or have tokens
issued. Use the `owner/repo` form.

```bash
curl -X POST https://migas.example.org/api/admin/register \
  -H "Authorization: Bearer $MASTER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project": "nipreps/fmriprep"}'
```

### Issue a project token

Returns a scoped token once, in plaintext, for a registered project. Master
tokens can't be issued this way.

```bash
curl -X POST https://migas.example.org/api/admin/issue-token \
  -H "Authorization: Bearer $MASTER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project": "nipreps/fmriprep", "description": "CI token"}'
```

Response:

```json
{ "success": true, "token": "m_…", "message": "Token issued successfully." }
```

### List tokens

Filter by `?project=owner/repo`. Returns hashed tokens and metadata
(`created_at`, `last_used`), never the raw token.

```bash
curl "https://migas.example.org/api/admin/list-tokens?project=nipreps/fmriprep" \
  -H "Authorization: Bearer $MASTER_TOKEN"
```

### Revoke a token

Deletes a token by its hashed value (from `list-tokens`). Master tokens can't be
revoked here.

```bash
curl -X POST https://migas.example.org/api/admin/revoke-token \
  -H "Authorization: Bearer $MASTER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"token": "<hashed-token>"}'
```

---

## 13. Upgrades

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
