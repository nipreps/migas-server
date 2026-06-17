# Administration

Managing the admin token, registering projects, and issuing access tokens. These
steps are the same however the server is deployed; only the way you *run* the
bootstrap script differs (noted below and in each deployment guide).

Examples use these shell variables: `$MIGAS_URL` for your instance
(`http://localhost:8081` for [Compose](getting-started.md),
`https://migas.example.org` otherwise), `$TOKEN` for the master token, and
`$PROJECT` for an `owner/repo` project slug. Pass tokens as
`Authorization: Bearer <token>`, never as URL parameters.

## Tokens

There are two kinds:

- **Master token** — project `master`, system-wide admin. Required for every
  `/api/admin/*` endpoint. The API can **not** create or revoke master tokens.
- **Scoped (project) token** — tied to one project, read-only access to that
  project's data:
    - its usage statistics via `GET /api/usage/{owner}/{repo}`;
    - that project (and nothing else) in the dashboard selector and
      `GET /api/auth/projects`.

  A scoped token can't reach other projects or any admin endpoint.

Sending breadcrumbs needs no token at all (see [Usage](usage.md)) — scoped
tokens are for *reading* usage, not ingesting.

## Bootstrap the master token

A fresh database has no master token, and the API can't create one. Create the
first with
[`scripts/bootstrap_admin_token.py`](https://github.com/nipreps/migas-server/blob/main/scripts/bootstrap_admin_token.py):
it generates a token, stores its BLAKE2b hash, ensures the `master` project row
exists, and prints the raw token once.

```bash
uv run python scripts/bootstrap_admin_token.py
```

```
Master token created. Save it now — it cannot be recovered:

    m_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

Use it as a bearer token:  Authorization: Bearer <token>
```

If a master token already exists the script refuses to run; add `--rotate` to
replace it (the old token stops working at once). Save the printed token — it
can't be recovered from the database.

> [!NOTE]
> Running the script differs by deployment: inside the container for
> [Compose](getting-started.md#4-first-steps), and over the Cloud SQL Auth Proxy
> for [Cloud Run](cloud-hosting.md#7-bootstrap-the-admin-token). See each guide
> for the exact invocation.

## Register a project

A project must be registered before it can receive telemetry or have tokens
issued. Use the `owner/repo` form.

```bash
curl -X POST $MIGAS_URL/api/admin/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"project\": \"$PROJECT\"}"
```

## Issue a project token

Returns a scoped token once, in plaintext, for a registered project. Master
tokens can't be issued this way.

```bash
curl -X POST $MIGAS_URL/api/admin/issue-token \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"project\": \"$PROJECT\", \"description\": \"CI token\"}"
```

```json
{ "success": true, "token": "m_…", "message": "Token issued successfully." }
```

## List tokens

Filter by `?project=owner/repo`. Returns hashed tokens and metadata
(`created_at`, `last_used`), never the raw token.

```bash
curl "$MIGAS_URL/api/admin/list-tokens?project=$PROJECT" \
  -H "Authorization: Bearer $TOKEN"
```

## Revoke a token

Deletes a token by its hashed value (from `list-tokens`). Master tokens can't be
revoked here.

```bash
curl -X POST $MIGAS_URL/api/admin/revoke-token \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"token": "<hashed-token>"}'
```
