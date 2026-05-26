# Security Core Area Files

Last updated: 2026-05-24

## Ownership

Threat Watch owns dependency-scoped cybersecurity intelligence for Flux. Scope is limited to dependencies, frameworks, runtime services, tools, and documented deployment paths present in this repository.

## Security-Owned Files

- `security/threat_watch.md` — latest dependency-scoped threat intelligence report.
- `security/dependency_exposure.md` — detected dependency/runtime inventory and local exposure notes.
- `security/source_notes.md` — public source list, retrieval dates, query notes, commands, and limitations.
- `security/environment_variables.md` — security-relevant environment variable ledger.
- `security/core_area_files.md` — this continuous index.
- `security/daily/security_{YYYY-MM-DD}/security_{YYYY-MM-DD}.md` — append-only daily Threat Watch activity ledger.
- `security_audit.md` — optional root summary only when explicitly useful.

## Recurring Repository Evidence

- Python manifests and locks: `web/Flux/pyproject.toml`, `web/Flux/uv.lock`, `fluxy/pyproject.toml`, `fluxy/uv.lock`, `build/`, `mine/`, `sim/`, `deep/` manifests and locks.
- Django runtime files: `web/Flux/src/flux/settings.py`, `web/Flux/src/flux/urls.py`, `web/Flux/src/flux/asgi.py`, `web/Flux/src/flux/wsgi.py`, app `urls.py`/`views.py`, templates, and static vendor files.
- Tooling manifests: `.opencode/package.json`, `.opencode/package-lock.json`.
- Agent permission config: `.opencode/agents/threat-watch.md` controls Threat-Watch shell access; restart OpenCode after editing it because agent config is not hot-reloaded.
- Deployment/runtime docs: `docs/operator-guide.md`, `docs/ignition-dev-cell.md`, `docs/flux-architecture.md`, `README.md`, `fluxy/docs/`.

## Recurring Public Sources

- CISA Known Exploited Vulnerabilities catalog.
- CISA ICS advisories, especially Inductive Automation.
- Django security release archive.
- PostgreSQL security page and release announcements.
- GitHub Security Advisories for exact package names.
- OSV.dev package/list queries and OSV Scanner when allowed.
- Vendor advisories for Python, Playwright, QuestDB, Ignition/Inductive Automation, and other detected services.

## Recurring Commands

- `uv tree --locked --all-groups --depth 2` from each Python subproject.
- `uv pip list` when comparing a local virtualenv to lockfiles.
- Version checks now used by Threat Watch: `uv --version`, `python --version`, `node --version`, `npm --version`, `uv run python --version`, Django import version check, Playwright version check, `psql --version`, psycopg/libpq runtime version probe, and localhost-only QuestDB version probe.
- Defensive dependency audits: `uv tool run pip-audit` against project paths where possible; when local editable packages or unsupported `uv.lock` handling block native audit, create short-lived security-owned pinned requirement files, audit them with `pip-audit --no-deps --requirement`, record results, then delete the temporary files. Use `npm audit --audit-level=low` in `.opencode`.
- OSV Scanner is still a desired recurring command, but it needs an approved packaged binary or valid npm invocation; `uvx osv-scanner` is not sufficient because `osv-scanner` is not a Python package.
- `git status --short` and targeted `git diff -- security/...` before editing security reports.
- Repository glob/grep/read checks for manifests, auth decorators, mutating views, CDN usage, DB DSNs, and service version mentions.

## Log Conventions

- Daily files are append-only ledgers under `security/daily/security_{YYYY-MM-DD}/security_{YYYY-MM-DD}.md`.
- Each session entry records timestamp if known, task intent, files inspected, sources queried, commands run, findings, blockers, and next actions.
- Do not promote a public vulnerability unless local package/product evidence and an affected version range plausibly match. Use `confirmed affected`, `possibly affected`, `not affected`, or `needs version evidence`.
