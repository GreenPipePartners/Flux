# Environment Variables

Retrieval date: 2026-05-24

This is the project-tracked environment ledger for variables that affect Flux security posture or external service exposure.

| Variable | Default/example | Scope | Dev posture | Non-dev requirement |
| --- | --- | --- | --- | --- |
| `FLUX_ENVIRONMENT` | `development` | Django settings / operator context | Documents local dev mode. | Set to the deployment name, for example `staging`, `site-dev`, or `production`. |
| `DJANGO_DEBUG` | `true` | Django web | Accepted for local development. | Must be `false`. |
| `DJANGO_SECRET_KEY` | `dev-only-insecure-flux-secret-key` | Django signing/session security | Accepted only for local development. | Must be unique, secret, and rotated if exposed. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Django host validation | Local-only default. | Must list only deployed hostnames/IPs. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Django CSRF | Empty is fine for local same-origin use. | Must include HTTPS origins when behind a proxy or alternate host. |
| `DATABASE_URL` | `postgres://flux:flux@localhost:5432/flux` | Django database | SQLite is used when blank; Postgres preferred for concurrent web/worker development. | Use site-specific credentials; do not reuse example creds. |
| `FLUXY_TOKEN` | `fluxy-auth-integration-token` | Ignition WebDev bridge | Required only when Fluxy WebDev uses `AUTH_TOKEN`. | Must be secret and scoped to the target gateway. |
| `QUESTDB_DSN` | `postgresql://admin:quest@localhost:8812/qdb` | Trace data plane | Local-only default. | Replace credentials and verify QuestDB is not routable from untrusted networks. |
| `QUESTDB_LATEST_CACHE_SECONDS` | `30` | Trace query cache | Performance tuning. | Tune per site load and freshness needs. |
| `QUESTDB_PROFILE_CACHE_SECONDS` | `60` | Trace profile cache | Performance tuning. | Tune per site load and freshness needs. |
| `QUESTDB_TRACE_CONCURRENCY` | `8` | Trace query gate | Limits concurrent QuestDB trace pressure. | Keep bounded; raise only with measured QuestDB capacity. |
| `FLUX_QUESTDB_HOST` | `localhost` | QuestDB monitor command | Local-only default. | Set to the private service host; avoid public bind. |
| `FLUX_QUESTDB_HTTP_PORT` | `9000` | QuestDB monitor command | Local QuestDB HTTP port. | Firewall or bind privately. |
| `FLUX_QUESTDB_PG_PORT` | `8812` | QuestDB monitor command | Local QuestDB Postgres-wire port. | Firewall or bind privately. |

## Notes

- Current development-only defaults are accepted for this phase, but this ledger gives us the checklist for any shared deployment.
- `Flux.auth` should own policy decisions later; this file is only the environment inventory, not the authorization design.
