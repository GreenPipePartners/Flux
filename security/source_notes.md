# Threat Watch Source Notes

Retrieval date: 2026-05-24

## Repository Evidence Inspected

- Manifests/locks: `web/Flux/pyproject.toml`, `web/Flux/uv.lock`, `fluxy/pyproject.toml`, `fluxy/uv.lock`, `build/pyproject.toml`, `mine/pyproject.toml`, `sim/pyproject.toml`, `deep/pyproject.toml`, `.opencode/package.json`, `.opencode/package-lock.json`.
- Runtime/config files: `web/Flux/src/flux/settings.py`, `web/Flux/src/flux/urls.py`, `web/Flux/src/flux/asgi.py`, `web/Flux/src/templates/flux/base.html`, `web/Flux/src/static/flux/vendor/README.md`, `web/Flux/.env.example`, `fluxy/src/fluxy/mcp/server.py`, docs under `docs/` mentioning Ignition, QuestDB, PostgreSQL, Fluxy, and Playwright.
- Searches performed with repository grep/glob for: Django settings, admin routes, CSRF/auth decorators, mutating views, QuestDB DSNs, PostgreSQL/QuestDB/Ignition references, htmx CDN usage, dependency manifests, `idna`, `starlette`, MCP, and Starlette request URL/path usage.

## Commands Run

- `git status --short`
- `uv --version` → `uv 0.11.11`
- `python --version` → `Python 3.14.4`
- `node --version && npm --version` → Node `v25.9.0`, npm `11.12.1`
- `psql --version` → `psql (PostgreSQL) 18.3`
- `uv run python --version` in `web/Flux` → `Python 3.14.4`
- `uv run python -m django --version` attempted but still blocked by allowlist.
- `uv run python -c "import django; print(django.get_version())"` in `web/Flux` → `5.2.14`
- `uv run python -m playwright --version` in `web/Flux` → `Version 1.59.0`
- `uv run python -c "import psycopg; import psycopg.pq as pq; print(psycopg.__version__); print(pq.version()); print(pq.version_pretty(pq.version()))"` in `web/Flux` → psycopg `3.3.4`, libpq integer `180000`, pretty `18.0`
- `curl -fsS http://127.0.0.1:9000/exec?query=select%20version%28%29` → QuestDB SQL endpoint responded with `PostgreSQL 12.3, compiled by Visual C++ build 1914, 64-bit, QuestDB`
- `uv tree --locked --all-groups --depth 2` in `web/Flux` and `fluxy`; full `uv tree --locked --all-groups` in `fluxy` for optional MCP transitive dependencies.
- `uv pip list` and `uv pip list --format=freeze` in `web/Flux` and `fluxy`.
- `uv run python -m pip list --format=freeze` attempted in `web/Flux` and `fluxy`, but project virtualenvs do not include pip.
- `pip-audit --version` and `osv-scanner --version` attempted directly; neither binary is installed.
- `uv tool run pip-audit --version` and `uvx pip-audit --version` succeeded with `pip-audit 2.10.0`.
- `uvx osv-scanner --version` failed because `osv-scanner` was not found in the Python package registry.
- `uv tool run pip-audit --locked .` in Python subprojects failed with `no lockfiles found in .` because pip-audit did not recognize `uv.lock` here.
- `uv tool run pip-audit --skip-editable --progress-spinner off .`:
  - `fluxy`, `mine`, `sim`, and `deep`: `No known vulnerabilities found` for project-resolved default/dev dependencies.
  - `web/Flux` failed resolving local `flux-build` as a PyPI package.
  - `build` failed resolving local `flux-mine` as a PyPI package.
- `uv tool run pip-audit --skip-editable --no-deps --progress-spinner off --requirement <(uv export ...)` attempted for subprojects but blocked by command allowlist/process substitution.
- Temporary security-owned pinned requirement files were created from lock/list evidence, audited, then deleted:
  - `uv tool run pip-audit --no-deps --progress-spinner off --requirement /home/bobby/Projects/11006-PRW-flux/security/.tmp-web-requirements.txt` → found `idna==3.14` / CVE-2026-45409, fixed 3.15.
  - `uv tool run pip-audit --no-deps --progress-spinner off --requirement /home/bobby/Projects/11006-PRW-flux/security/.tmp-fluxy-all-requirements.txt` → found `idna==3.14` / CVE-2026-45409 and `starlette==1.0.0` / PYSEC-2026-161.
- `npm audit --audit-level=low` in `.opencode` → `found 0 vulnerabilities`.
- Remediation commands after the initial findings:
  - `uv lock --upgrade-package idna` in `web/Flux` → upgraded `idna` 3.14 to 3.16.
  - `uv lock --upgrade-package idna --upgrade-package starlette` in `fluxy` → upgraded `idna` 3.14 to 3.16 and `starlette` 1.0.0 to 1.1.0.
  - Added explicit security floors in manifests: `web/Flux` and `fluxy` now require `idna>=3.15`; Fluxy MCP extra now requires `starlette>=1.0.1`.
  - `uv lock` in `web/Flux` and `fluxy` after manifest edits.
  - `uv sync --all-groups` in `web/Flux`; `uv sync --all-groups --all-extras` in `fluxy`.
  - Runtime verification: web `idna.__version__` returned `3.16`; Fluxy `idna.__version__` returned `3.16` and `starlette.__version__` returned `1.1.0`.
  - `uv tool run pip-audit --skip-editable --progress-spinner off --path ...site-packages` against synced web and Fluxy environments → no known vulnerabilities found; editable local packages skipped.
  - `uv lock --upgrade-package psycopg --upgrade-package psycopg-binary` in `web/Flux` resolved without an available package update; psycopg remains 3.3.4 with bundled libpq 18.0.

## Public Sources Queried

- CISA Known Exploited Vulnerabilities catalog, catalog version `2026.05.22`, retrieved 2026-05-24: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
- CISA ICS advisories for Inductive Automation, retrieved 2026-05-24:
  - Advisory index filtered to Inductive Automation: https://www.cisa.gov/news-events/ics-advisories?f%5B0%5D=ics_advisory_vendor%3A359
  - ICSA-26-071-06 / CVE-2025-13913: https://www.cisa.gov/news-events/ics-advisories/icsa-26-071-06
  - ICSA-25-352-01 / CVE-2025-13911: https://www.cisa.gov/news-events/ics-advisories/icsa-25-352-01
- Django security archive, retrieved 2026-05-24: https://docs.djangoproject.com/en/dev/releases/security/
- Django 5.2 security archive, retrieved 2026-05-24: https://docs.djangoproject.com/en/5.2/releases/security/
- PostgreSQL, retrieved 2026-05-24:
  - Security Information: https://www.postgresql.org/support/security/
  - 2026-05-14 release announcement: https://www.postgresql.org/about/news/postgresql-184-1710-1614-1518-and-1423-released-3297/
  - CVE-2026-6477 detail: https://www.postgresql.org/support/security/CVE-2026-6477/
  - CVE-2026-6479 detail: https://www.postgresql.org/support/security/CVE-2026-6479/
- idna / CVE-2026-45409, retrieved 2026-05-24:
  - GitHub Advisory Database GHSA-65pc-fj4g-8rjx: https://github.com/advisories/GHSA-65pc-fj4g-8rjx
  - Upstream idna advisory: https://github.com/kjd/idna/security/advisories/GHSA-65pc-fj4g-8rjx
  - OSV record: https://osv.dev/vulnerability/CVE-2026-45409
  - PyPI idna release page: https://pypi.org/project/idna/
- Starlette / PYSEC-2026-161 / CVE-2026-48710, retrieved 2026-05-24:
  - Starlette GitHub advisory GHSA-86qp-5c8j-p5mr: https://github.com/Kludex/starlette/security/advisories/GHSA-86qp-5c8j-p5mr
  - OSV PYSEC-2026-161: https://osv.dev/vulnerability/PYSEC-2026-161
  - X41 advisory X41-2026-002: https://www.x41-dsec.de/lab/advisories/x41-2026-002-starlette/
  - PyPI Starlette release page: https://pypi.org/project/starlette/
- GitHub Security Advisories, retrieved 2026-05-24:
  - Django search: https://github.com/advisories?query=ecosystem%3Apip+django
  - httpx search and GHSA-h8pj-cxx2-jfg2: https://github.com/advisories?query=ecosystem%3Apip+httpx and https://github.com/advisories/GHSA-h8pj-cxx2-jfg2
  - psycopg search: https://github.com/advisories?query=ecosystem%3Apip+psycopg
  - Starlette search and previously checked advisories: https://github.com/advisories?query=ecosystem%3Apip+starlette, https://github.com/advisories/GHSA-7f5h-v6xp-fcq8, https://github.com/advisories/GHSA-2c2j-9gv5-cj73, https://github.com/advisories/GHSA-f96h-pmfr-66vw
  - python-multipart advisory: https://github.com/advisories/GHSA-pp6c-gr5w-3c5g
  - OpenCode searches and GHSA-c83v-7274-4vgp: https://github.com/advisories?query=type%3Areviewed+ecosystem%3Anpm+package%3A%40opencode-ai%2Fplugin, https://github.com/advisories?query=type%3Areviewed+ecosystem%3Anpm+package%3Aopencode-ai, https://github.com/advisories/GHSA-c83v-7274-4vgp
  - cross-spawn search and GHSA-3xgq-45jj-v275: https://github.com/advisories?query=ecosystem%3Anpm+cross-spawn and https://github.com/advisories/GHSA-3xgq-45jj-v275
- OSV.dev list queries, retrieved 2026-05-24:
  - `django ecosystem:PyPI`: https://osv.dev/list?q=django%20ecosystem:PyPI
  - `gunicorn ecosystem:PyPI`: https://osv.dev/list?q=gunicorn%20ecosystem:PyPI
  - `starlette ecosystem:PyPI`: https://osv.dev/list?q=starlette%20ecosystem:PyPI
  - `playwright ecosystem:PyPI`: https://osv.dev/list?q=playwright%20ecosystem:PyPI
  - package-scoped variants for Django, Gunicorn, Starlette, Playwright, idna, and `@opencode-ai/plugin`.
- CVE Program records attempted earlier on 2026-05-24, but webfetch returned JavaScript-only placeholder pages: https://www.cve.org/CVERecord?id=CVE-2025-13913, https://www.cve.org/CVERecord?id=CVE-2025-13911, https://www.cve.org/CVERecord?id=CVE-2026-6479.
- QuestDB release-note URLs attempted earlier on 2026-05-24 returned 404: https://questdb.com/docs/release-notes/, https://questdb.io/docs/release-notes/, https://questdb.com/docs/reference/release-notes/.

## Limitations

- `pip-audit` did not directly understand `uv.lock` in this environment and failed on local editable path packages when auditing full project paths. Findings for web/Flux and Fluxy all-extras therefore came from temporary pinned requirement files derived from lock/list evidence, not from a native uv.lock audit.
- `uv export` process substitution was still blocked by the command allowlist, even after restart; temporary files were used and then removed.
- OSV Scanner was not available as a local binary, and `uvx osv-scanner` is not valid because the scanner is not in the Python package registry. A packaged OSV Scanner binary or approved npm invocation is still needed for independent OSV lock matching.
- The CISA KEV feed is very large and tool output was truncated. No finding was promoted solely from KEV unless it matched detected local technology with version evidence.
- PostgreSQL server, authoritative QuestDB runtime version, Ignition Gateway, deployed Python patch level, and actual production environment variables were not available from this repository.
- Future-dated dependency versions appear in `uv.lock` relative to ordinary public package state; findings are therefore scoped to repository evidence and retrieved public advisory pages only.
- GitHub Advisory Database search pages are broad unless the `package:` qualifier is used. Broad search results were only used as discovery; package-qualified or specific advisory pages were used for exposure decisions where possible.
- Waitress was removed from the web virtualenv after the dependency review. It is unsupported Windows-runtime residue and is not a Flux dependency.

## Recommended Follow-up Source Queries

- Re-run `pip-audit` after future PostgreSQL client/libpq dependency changes or any lock refresh.
- Run OSV Scanner from an approved packaged binary or approved npm command against the `uv.lock` and npm lock files.
- Check vendor advisories for deployed Ignition, QuestDB, PostgreSQL server, Python, Playwright browsers, and OS base images after runtime versions are known.
- Re-check CISA ICS advisories after capturing Ignition version/platform and CISA KEV after capturing all externally reachable product versions.
