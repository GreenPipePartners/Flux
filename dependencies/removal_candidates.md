# Dependency Removal Candidates

Review date: 2026-05-24

## Summary

Flux has a generally small Python runtime surface outside the Django web app and Fluxy. Removal attention should focus on environment residue, overlapping dev tools, and optional/tool-local dependencies that are not part of the runtime mission.

## Candidates

| Candidate | Current evidence | Cost / risk | Recommendation | Confidence |
| --- | --- | --- | --- | --- |
| `waitress` | Previously present as 3.0.2 in `web/Flux` venv only; absent from manifest/lock; now removed from the environment. | Reintroduction would recreate unsupported Windows-runtime residue. | **Removed. Keep out.** | High |
| `pyright` | Previously declared in Fluxy dev dependencies and CI; now removed in favor of ty. | Reintroduction would split type-checker authority and add nodeenv/transitive tooling cost. | **Removed. Keep out unless explicitly reapproved.** | High |
| `dj-database-url` overlap with `django-environ` | `settings.py` uses `django-environ` for env casting and `dj_database_url.parse()` for `DATABASE_URL`. `django-environ` can parse DB URLs in common usage, but local code currently uses both. | Small runtime dependency but overlapping responsibility. Removing requires settings refactor and DATABASE_URL coverage. | **Needs evidence.** Do not remove yet; add a focused test/refactor later if dependency minimization is worth the change. | Medium |
| `@opencode-ai/plugin` | `.opencode/package.json` pins 1.14.41; not app runtime. npm missing prevented local graph verification. | Tool-only package with Node/npm transitive surface; may be necessary for opencode agents. | **Needs owner evidence.** Keep if opencode workflow depends on it; remove if no plugin code/agent needs it. | Medium |
| Fluxy optional `mcp` extra | Owned by upstream PyPI `fluxy-ign`; not installed by Flux root runtime. | Can pull ASGI/server transitive dependencies when installed. | **Keep optional only.** Do not install in web/runtime env by default. | Medium |
| Fluxy optional `sqlalchemy` extra | Owned by upstream PyPI `fluxy-ign`; not installed by Flux root runtime. | Adds ORM/database abstraction surface outside Django. | **Keep optional only.** Do not promote to runtime unless a concrete integration owns it. | Medium |
| Vendored HTMX-compatible local runtime | Local static runtime reports `2.0.4-flux-local`; required by HTMX-first templates. | Replacing with upstream HTMX may change behavior; keeping local fork can hide drift. | **Do not remove now.** Document supported `hx-*` subset and test coverage; revisit with browser tests. | Medium |

## Not Candidates Today

- `orjson`: clear performance job in chart JSON paths; keep.
- `psycopg[binary]`: clear QuestDB/PostgreSQL wire job; keep but watch binary packaging for deployment environments.
- `ty`: beta but now explicitly owns Fluxy type checking; keep and monitor diagnostic churn.
- `playwright`: large but earns cost through browser e2e coverage for HTMX/Comp Surface behavior; keep.
- `django-htmx`: tiny and directly enables `request.htmx`; keep while HTMX-first architecture stands.
- `whitenoise`: direct staticfiles deployment job; keep for Linux/gunicorn app serving.
- `httpx`: core Fluxy HTTP client; keep.

## Next Removal Actions

1. Add focused `DATABASE_URL` settings coverage before attempting to remove either `dj-database-url` or `django-environ`.
2. Ask whether `.opencode` dependency is necessary for active opencode agents; remove if unused.
3. Watch ty diagnostic churn now that it is the Fluxy authority.
