# Sending & viewing telemetry

How to send telemetry to a running instance and view it. Examples use
`$MIGAS_URL` for your instance (`http://localhost:8081` for
[Compose](getting-started.md), `https://migas.example.org` otherwise) and
`$PROJECT` for an `owner/repo` project slug.

## Send a breadcrumb

A breadcrumb is a single telemetry ping. It needs no token, but the project must
already be registered (see [Administration](administration.md#register-a-project)).
`?wait=true` ingests synchronously; without it the call returns `202` and
ingestion runs in the background.

```bash
curl -X POST "$MIGAS_URL/api/breadcrumb?wait=true" \
  -H "Content-Type: application/json" \
  -d '{
    "project": "'"$PROJECT"'",
    "project_version": "1.0.0",
    "language": "python",
    "language_version": "3.11",
    "ctx": {"platform": "linux", "is_ci": false},
    "proc": {"status": "C"}
  }'
```

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

## View the dashboard

Open the usage visualization at `$MIGAS_URL/viz/`. After sending a few
breadcrumbs for a project, you can chart its usage there. Charting a project
requires a token with access to it (see
[Administration](administration.md#tokens)).
