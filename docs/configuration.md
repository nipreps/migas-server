# Configuration

The server is configured entirely through environment variables. How you set
them depends on the deployment: a systemd `EnvironmentFile` for
[self-hosting](self-hosting.md), the `environment:` block of
[`docker-compose.yml`](https://github.com/nipreps/migas-server/blob/main/docker-compose.yml)
for [Compose](getting-started.md), or `--set-env-vars` for
[Cloud Run](cloud-hosting.md).

## Database

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | Full connection URL. Coerced to `postgresql+asyncpg`. Use this for any remote DB. |
| `DATABASE_USER` | — | Used only if `DATABASE_URL` is unset. |
| `DATABASE_PASSWORD` | — | Used only if `DATABASE_URL` is unset. |
| `DATABASE_NAME` | — | Used only if `DATABASE_URL` is unset. |
| `DATABASE_HOST` | `localhost` | **Alembic only** — the running server ignores this. |
| `DATABASE_PORT` | `5432` | **Alembic only** — the running server ignores this. |
| `GCP_SQL_CONNECTION` | — | Cloud SQL socket (`project:region:instance`). Leave unset outside GCP. |

The server builds its connection URL one of two ways:

- **`DATABASE_URL`** — a single connection string. Use this for any remote
  database.
- **Discrete `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_NAME`** — used
  only when `DATABASE_URL` is unset.

> [!IMPORTANT]
> The discrete form does **not** read a host or port at runtime — it connects to
> the local default (Unix socket / `localhost:5432`). If your database is on
> another host, you must use `DATABASE_URL`. (Alembic's `env.py` does honor
> `DATABASE_HOST` / `DATABASE_PORT`, so migrations can reach a remote DB with the
> discrete form, but the running server can't — use `DATABASE_URL` everywhere to
> avoid surprises.)

## Redis

| Variable | Default | Notes |
|---|---|---|
| `MIGAS_REDIS_URI` | — | **Required.** `redis://[:password@]host:port`. |
| `REDIS_TLS_URL` | — | TLS endpoint (`rediss://…`). Takes precedence over `MIGAS_REDIS_URI`. |

## Rate limiting & request size

| Variable | Default | Notes |
|---|---|---|
| `MIGAS_REQUEST_WINDOW` | `60` | Sliding-window length in seconds. |
| `MIGAS_MAX_REQUESTS_PER_WINDOW` | `100` | Allowed requests per window per client. |
| `MIGAS_MAX_REQUEST_SIZE` | `2500` | Max request body size in bytes. |
| `MIGAS_BYPASS_RATE_LIMIT` | unset | Set to any non-empty value to disable rate limiting (not recommended in prod). |

## Geolocation

| Variable | Default | Notes |
|---|---|---|
| `MIGAS_GEOLOC` | unset | Set to `1`/`true` to enable IP geolocation. |
| `MIGAS_GEOLOC_DIR` | `.` | Directory containing `city.mmdb` and `asn.mmdb`. |

Geolocation tags telemetry with coarse city/ASN info. The server reads two
MaxMind-format files, `city.mmdb` and `asn.mmdb`, from `MIGAS_GEOLOC_DIR` (bring
your own). Download them (hosted on OSF, no MaxMind key needed):

```bash
uv run scripts/download_geodbs.py <geodb-dir>
```

Then set `MIGAS_GEOLOC=1` and point `MIGAS_GEOLOC_DIR` at `<geodb-dir>` (any
location the server can read). With `MIGAS_GEOLOC` unset, the files aren't needed
and geolocation is skipped.

## Misc

| Variable | Default | Notes |
|---|---|---|
| `MIGAS_DEV` | unset | Enables SQLAlchemy SQL echo. **Never set in production.** |
