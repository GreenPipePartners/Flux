# Threat Watch

Retrieval date: 2026-05-24

## Scope

Reviewed Flux's Python/Django web app, Fluxy Ignition client, local packages, optional Fluxy MCP stack, Playwright/dev tooling, QuestDB/PostgreSQL/Ignition documentation, npm OpenCode plugin tooling, Django settings, URL routing, lock files, and public advisory sources listed in `security/source_notes.md`. This rerun specifically validated the previously blocked version/audit commands after the OpenCode restart.

## Executive Summary

The two Python package findings are now remediated in the repository locks and local synced environments:

1. **Remediated in repo: `idna` upgraded from 3.14 to 3.16.** `web/Flux/pyproject.toml` and `fluxy/pyproject.toml` now require `idna>=3.15`; both locks resolve `idna==3.16`; synced local runtimes import `idna.__version__ == 3.16`; `pip-audit` now reports no known vulnerabilities for the synced web and Fluxy environments.
2. **Remediated in repo: optional Fluxy MCP Starlette upgraded from 1.0.0 to 1.1.0.** `fluxy[ mcp ]` now requires `starlette>=1.0.1`; the Fluxy lock resolves `starlette==1.1.0`; synced local runtime imports Starlette 1.1.0; `pip-audit` now reports no known vulnerabilities for the synced Fluxy all-extra environment.
3. **Remaining external boundary: PostgreSQL client/libpq.** `psycopg-binary==3.3.4` still reports bundled libpq `18.0`, and local `psql` is `18.3`; PostgreSQL's 2026-05-14 security release fixes client and server issues in 18.4/17.10/16.14/15.18/14.23. `uv lock --upgrade-package psycopg --upgrade-package psycopg-binary` found no newer psycopg package in this resolver state, so this remains an OS/client-package or future-wheel update boundary.
4. **No direct CISA KEV match promoted.** The CISA KEV catalog version checked was 2026.05.22. High-profile KEV products observed in the feed do not match Flux dependencies; Laravel Ignition remains unrelated to Inductive Automation Ignition.
5. **Django remains current in this repo.** Runtime check confirmed Django `5.2.14`, and `web/Flux/pyproject.toml` requires `django>=5.2.14,<6.0`.
6. **Local app exposure remains deployment-critical.** Django still has development defaults, and mutating Flux routes lack observed auth decorators. This is not a new public CVE, but it raises the impact of any reachable service or dependency issue.

## Dependency Exposure Summary

See `security/dependency_exposure.md` for the full inventory. Highest-confidence runtime dependencies: Python 3.14.4 in the local web environment, uv 0.11.11, Django 5.2.14, gunicorn 26.0.0, psycopg/psycopg-binary 3.3.4 with libpq 18.0, httpx 0.28.1, idna 3.16, django-htmx 1.27.0, local HTMX-compatible runtime, local uPlot 1.6.32, Playwright 1.59.0 for tests, optional Fluxy MCP dependencies `mcp==1.27.1`, `starlette==1.1.0`, `python-multipart==0.0.28`, `uvicorn==0.46.0`, QuestDB documented as 9.3.5 but local version endpoint only returned a PostgreSQL 12.3 compatibility string, PostgreSQL server version unknown, Ignition version unknown. Waitress is not a Flux dependency and has been removed from the web environment. `.opencode` npm audit found 0 vulnerabilities.

## Relevant Advisories

### GitHub/OSV GHSA-65pc-fj4g-8rjx / CVE-2026-45409 — idna remediated in repo lock

- **Sources:** GitHub Advisory Database, https://github.com/advisories/GHSA-65pc-fj4g-8rjx; OSV, https://osv.dev/vulnerability/CVE-2026-45409; upstream GitHub advisory, https://github.com/kjd/idna/security/advisories/GHSA-65pc-fj4g-8rjx; PyPI idna release page, https://pypi.org/project/idna/; all retrieved 2026-05-24.
- **Original local evidence:** `web/Flux/uv.lock` and `fluxy/uv.lock` locked `idna==3.14`; `pip-audit 2.10.0` found CVE-2026-45409 in both the web exported requirements and Fluxy all-extra requirements.
- **Remediation evidence:** `web/Flux/pyproject.toml` and `fluxy/pyproject.toml` now require `idna>=3.15`; `web/Flux/uv.lock` and `fluxy/uv.lock` now resolve `idna==3.16`; synced runtime import checks returned 3.16; `pip-audit --path ...site-packages` reported no known vulnerabilities for both synced environments.
- **Affected range / fixed version:** `idna <3.15`; fixed in 3.15. PyPI shows 3.16 available as of 2026-05-22.
- **Severity:** GitHub reviewed advisory, Moderate; CVSS v4 score 6.9; CWE-1333 in OSV/GitHub database data.
- **Exploitation status:** not promoted as CISA KEV during this review.
- **Exposure status:** **remediated in current repo lock and synced local environments**. Deployed environments still need to install the updated lock/package constraints.
- **Mitigation:** deploy the updated locks/package metadata; keep `idna>=3.15`; ensure any user-provided host/domain value is length-limited to valid DNS maximums before passing to HTTP/client URL construction.

### Starlette GHSA-86qp-5c8j-p5mr / CVE-2026-48710 / PYSEC-2026-161 — optional Fluxy MCP remediated in repo lock

- **Sources:** Starlette GitHub security advisory, https://github.com/Kludex/starlette/security/advisories/GHSA-86qp-5c8j-p5mr; OSV PYSEC-2026-161, https://osv.dev/vulnerability/PYSEC-2026-161; X41 advisory X41-2026-002, https://www.x41-dsec.de/lab/advisories/x41-2026-002-starlette/; PyPI Starlette release page, https://pypi.org/project/starlette/; all retrieved 2026-05-24.
- **Original local evidence:** `fluxy/uv.lock` locked `starlette==1.0.0`; `fluxy/pyproject.toml` exposes optional `mcp` extra; `uv tree --locked --all-groups` showed `mcp==1.27.1 -> starlette==1.0.0`; `pip-audit 2.10.0` found `PYSEC-2026-161` in the Fluxy all-extra requirements. `fluxy/src/fluxy/mcp/server.py` imports `FastMCP` only when the optional MCP support is installed and run.
- **Remediation evidence:** Fluxy `mcp` extra now includes `starlette>=1.0.1`; `fluxy/uv.lock` resolves `starlette==1.1.0`; synced runtime import checks returned Starlette 1.1.0; `pip-audit --path ...site-packages` reported no known vulnerabilities for the synced Fluxy all-extra environment.
- **Affected range / fixed version:** Starlette `<=1.0.0`; fixed in 1.0.1. PyPI shows 1.1.0 available as of 2026-05-23.
- **Severity:** GitHub advisory Moderate, CVSS v3.1 6.5; X41 rates High, CVSS 7.0.
- **Issue class:** invalid HTTP `Host` header can poison `request.url.path`, potentially bypassing middleware/endpoints that make security decisions from reconstructed URL paths rather than the raw request path.
- **Exploitation status:** not promoted as CISA KEV during this review.
- **Exposure status:** **remediated in current repo lock and synced local Fluxy all-extra environment**. Deployed/installed MCP environments still need to install the updated `fluxy[mcp]` metadata/lock.
- **Mitigation:** deploy the updated Fluxy package/lock; keep MCP local-only unless explicitly authenticated; reject invalid `Host` headers at any reverse proxy; avoid security checks based on `request.url.path` in Starlette/ASGI middleware.

### PostgreSQL May 2026 security release — local client affected; deployed server needs evidence

- **Sources:** PostgreSQL Security Information, https://www.postgresql.org/support/security/; release announcement, https://www.postgresql.org/about/news/postgresql-184-1710-1614-1518-and-1423-released-3297/; CVE-2026-6477 detail, https://www.postgresql.org/support/security/CVE-2026-6477/; retrieved 2026-05-24.
- **Local evidence:** `web/Flux/pyproject.toml` depends on `psycopg[binary]>=3.2`; `web/Flux/uv.lock` locks `psycopg==3.3.4` and `psycopg-binary==3.3.4`; runtime probe returned psycopg `3.3.4`, libpq version `18.0`; local `psql --version` returned `18.3`. `settings.py` uses `DATABASE_URL` when set. Deployed PostgreSQL server version remains unknown.
- **Affected range:** supported PostgreSQL 14-18 client/server releases before 18.4, 17.10, 16.14, 15.18, and 14.23 are affected by multiple 2026-05-14 fixes. The locally confirmed client-relevant issue is CVE-2026-6477, a libpq `lo_*` client memory overwrite issue fixed in 18.4/17.10/16.14/15.18/14.23 with CVSS 8.8. Server-side issues include CVE-2026-6479 unauthenticated DoS (CVSS 7.5), CVE-2026-6473 server integer-wrap allocation issues (CVSS 8.8), CVE-2026-6637 `refint` stack buffer overflow / SQL injection (CVSS 8.8), and related authorization, SQL injection, and information disclosure fixes.
- **Exploitation status:** not found as a direct CISA KEV match during this review.
- **Exposure status:** **confirmed affected client version locally** for libpq/psql below the fixed 18.x minor; **needs server version evidence** for the deployed PostgreSQL service. Flux app exposure to CVE-2026-6477 is limited unless it uses libpq large-object APIs or client utilities such as `psql`/`pg_dump` against a malicious or compromised PostgreSQL server. Server-side exposure remains possible for any deployed PostgreSQL 14-18 server below the fixed minor versions.
- **Mitigation:** update PostgreSQL client tools/libpq to 18.4 or the fixed minor for the deployed major line; upgrade `psycopg-binary` when a wheel bundling fixed libpq is available or prefer OS-provided patched libpq with non-binary psycopg where operationally practical; record deployed `select version();`; patch PostgreSQL server to the current minor release; prefer SCRAM over MD5 passwords; restrict database network reachability.

### Inductive Automation Ignition CVE-2025-13913 — needs gateway version evidence

- **Source:** CISA ICS Advisory ICSA-26-071-06, https://www.cisa.gov/news-events/ics-advisories/icsa-26-071-06, retrieved 2026-05-24.
- **Local evidence:** Fluxy deploys and calls Ignition WebDev resources; docs describe local and production Ignition gateways, Fluxy WebDev auth, tag writes, OPC configuration, and project import/export workflows. The actual Ignition Gateway version is not recorded in the repository.
- **Affected range:** Inductive Automation Ignition Software `<8.3.0`; CVE-2025-13913; CVSS v3.1 6.3; CWE-502 deserialization of untrusted data.
- **Exploitation status:** CISA advisory states no known public exploitation specifically targeting this vulnerability and that it is not remotely exploitable.
- **Exposure status:** **needs version evidence**. Possibly affected if Flux targets an 8.1.x / pre-8.3.0 gateway and privileged users import untrusted project/data files.
- **Mitigation:** upgrade target gateways to Ignition 8.3.0 or later where compatible; otherwise apply Inductive Automation hardening guidance, restrict project imports to trusted/signed sources, use dev/test/prod staging, and keep the Ignition service account least-privileged.

### Inductive Automation Ignition CVE-2025-13911 — needs platform and service-account evidence

- **Source:** CISA ICS Advisory ICSA-25-352-01, https://www.cisa.gov/news-events/ics-advisories/icsa-25-352-01, retrieved 2026-05-24.
- **Local evidence:** Flux automation can interact with Ignition and deploy/configure WebDev resources; repository docs include Ignition Gateway and Fluxy WebDev workflows. The target gateway OS and service-account privileges are unknown.
- **Affected range:** Inductive Automation Ignition `8.1.x|8.3.x`; CVE-2025-13911; CVSS v3.1 6.4; CWE-250 execution with unnecessary privileges.
- **Exploitation status:** CISA advisory states no known public exploitation specifically targeting this vulnerability and high attack complexity.
- **Exposure status:** **needs version/platform evidence**. Most concerning for Windows gateways where the Ignition Gateway service runs with excessive privileges and privileged users can upload project files containing scripts.
- **Mitigation:** run Ignition under a dedicated least-privileged service account, isolate gateways from corporate/domain privileges where feasible, enforce MFA/strong credential management for Designer/config-write users, and review import workflows.

### Django 5.2 security release stream — not confirmed affected at locked 5.2.14

- **Source:** Django security archive, https://docs.djangoproject.com/en/dev/releases/security/, retrieved 2026-05-24.
- **Local evidence:** `web/Flux/uv.lock` locks Django 5.2.14; `web/Flux/pyproject.toml` requires `django>=5.2.14,<6.0`; runtime probe via `uv run python -c "import django; print(django.get_version())"` returned 5.2.14.
- **Exploitation status:** not found as a CISA KEV match during this review; source is vendor security archive.
- **Exposure status:** **not affected / monitor**, assuming deployed lock is really 5.2.14. Older deployed 5.2 builds may be affected.
- **Relevant advisory classes from Django archive:** ASGI file upload DoS, session fixation/cache interaction, `Vary: *` cache exposure, ASGI header spoofing, admin privilege-abuse classes, and ORM edge-case SQL injection classes. Flux does not currently install or route `django.contrib.admin`.
- **Mitigation:** keep Django pinned to the latest 5.2.x lock; verify production runs the lockfile version, not a broad resolver install. Avoid public cache/session patterns unless explicitly reviewed. Treat ASGI advisories as relevant if `flux.asgi` is deployed behind uvicorn/daphne even though the default project setting names WSGI.

### CISA Known Exploited Vulnerabilities — no direct dependency finding promoted

- **Source:** CISA KEV catalog, https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json, catalog version 2026.05.22, retrieved 2026-05-24.
- **Local evidence:** Flux stack is Django/Python/HTMX/QuestDB/PostgreSQL/Ignition. Repository and source review did not show Drupal, Langflow, Ivanti, Fortinet, cPanel, Laravel Ignition, or other matching KEV products as Flux dependencies.
- **Exploitation status:** catalog contains known-exploited vulnerabilities, but no direct Flux dependency finding had both product and version evidence.
- **Exposure status:** **not affected / no direct match promoted** for repository dependencies; **needs runtime evidence** for server OS/browser/network appliances outside this repo.
- **Mitigation:** keep KEV checking in the daily workflow after deployed product versions are captured.

## Worrisome Local Exposure Findings

### Default insecure Django deployment settings

- **Evidence:** `web/Flux/src/flux/settings.py` defaults `DJANGO_DEBUG=True` and `DJANGO_SECRET_KEY` to `dev-only-insecure-flux-secret-key`.
- **Exposure status:** **accepted for development only**; possibly affected in any shared deployment not explicitly overriding env vars.
- **Why it matters:** debug mode and shared secret keys can expose internals and invalidate session/signing assumptions.
- **Mitigation:** fail startup when `DEBUG=False` and `DJANGO_SECRET_KEY` is missing/known-dev; require explicit `DJANGO_DEBUG=False`, strong secret, `ALLOWED_HOSTS`, trusted origins, and secure cookies for non-dev.

### Unauthenticated operational mutation surface

- **Evidence:** URL routes expose dashboard, serve, mine, build, cell, sim, live, charts; grep found state-changing POST views but no `login_required`/permission decorators in inspected modules. CSRF middleware is present.
- **Exposure status:** **possibly affected** if Flux binds beyond localhost or a trusted dev network.
- **Why it matters:** Flux can interact with Ignition/WebDev, simulator state, bridge tokens/config, database-backed setup, and generated tags. CSRF is not a substitute for authentication/authorization.
- **Mitigation:** add an explicit internal auth gate or network-only enforcement before any shared deployment; protect mutating endpoints first (`serve`, `sim`, `build`, dashboard bridge/setup paths).

### Django admin removed

- **Evidence:** `django.contrib.admin` is not present in `INSTALLED_APPS`, `/admin/` is not present in `flux.urls`, and `LOGIN_URL` no longer points to `admin:login`.
- **Exposure status:** **not present in current Flux web routing**.
- **Mitigation:** keep admin out of Flux routes unless an explicit future dev-only flag is added.

### QuestDB default credentials and service reachability

- **Evidence:** `QUESTDB_DSN` defaults to `postgresql://admin:quest@localhost:8812/qdb`; docs state QuestDB 9.3.5 and local ports 8812/9000; localhost `/exec?query=select version()` returned a PostgreSQL 12.3 compatibility string, not a reliable QuestDB product version.
- **Exposure status:** **possibly affected** if QuestDB is reachable off-host or default creds remain in shared environments.
- **Mitigation:** bind QuestDB to localhost/private interface only, rotate credentials, firewall ports 8812/9000, and avoid default DSN in production-like environments. Capture an authoritative QuestDB product version from its admin UI, logs, package metadata, or a vendor-documented version endpoint.

### Runtime browser libraries are local

- **Evidence:** `web/Flux/src/templates/flux/base.html` loads `flux/vendor/htmx/htmx.min.js`; uPlot is local under `flux/vendor/uplot/`.
- **Exposure status:** **no public-CDN runtime fetch observed**.
- **Mitigation:** keep browser libraries local. Replace the local HTMX-compatible runtime with the exact upstream vendored artifact when shell-based asset refresh is available.

## Not Applicable Or Deprioritized

- Laravel Ignition in CISA KEV is not Inductive Automation Ignition; no Laravel/PHP stack was detected.
- Drupal, Langflow, Ivanti, Fortinet, Palo Alto, Exchange, cPanel, and other high-profile KEV entries seen in the CISA feed were not reported as Flux findings because this repository does not show those products as dependencies or deployment requirements.
- GitHub Advisory GHSA-c83v-7274-4vgp / CVE-2026-22813 affects npm `opencode-ai <1.1.10`, not the detected `@opencode-ai/plugin==1.14.41`; no repository package evidence for `opencode-ai` was found.
- GitHub Advisory GHSA-3xgq-45jj-v275 / CVE-2024-21538 affects `cross-spawn >=7.0.0,<7.0.5` and `<6.0.6`; `.opencode/package-lock.json` locks `cross-spawn==7.0.6`, so this is not affected.
- GitHub Advisory GHSA-h8pj-cxx2-jfg2 / CVE-2021-41945 affects `httpx <0.23.0`; Flux locks `httpx==0.28.1`, so this is not affected.
- Starlette GHSA-7f5h-v6xp-fcq8 / CVE-2025-62727, GHSA-2c2j-9gv5-cj73 / CVE-2025-54121, GHSA-f96h-pmfr-66vw / CVE-2024-47874, and python-multipart GHSA-pp6c-gr5w-3c5g / CVE-2026-42561 remain not affected at locked `starlette==1.1.0` and `python-multipart==0.0.28`.
- Gunicorn, Playwright, psycopg package advisories, django-htmx, Whitenoise, and QuestDB did not produce an additional confirmed vulnerable-version finding through the sources retrieved today.

## Commands And Sources

- Files inspected with repository glob/read/grep tools: manifests, locks, `settings.py`, `urls.py`, `asgi.py`, templates, static vendor README, docs, package lock files, security notes, Fluxy MCP server.
- Commands run: `git status --short`; `uv --version`; `python --version`; `node --version && npm --version`; `psql --version`; `uv run python --version`; `uv run python -c "import django; print(django.get_version())"`; `uv run python -m playwright --version`; `uv run python -c "import psycopg; import psycopg.pq as pq; ..."`; localhost QuestDB `curl` version probe; `uv tree --locked --all-groups --depth 2`; full Fluxy `uv tree --locked --all-groups`; `uv pip list`; `uv pip list --format=freeze`; `uv lock --upgrade-package ...`; `uv sync --all-groups`; `uv sync --all-groups --all-extras`; patched runtime import checks; `uv tool run pip-audit --version`; `uv tool run pip-audit` project audits; `uv tool run pip-audit --no-deps --requirement ...` against temporary security-owned pinned requirement files; `uv tool run pip-audit --path ...site-packages`; `pip-audit --version`; `osv-scanner --version`; `uvx osv-scanner --version`; `npm audit --audit-level=low` in `.opencode`.
- Source URLs: CISA KEV feed, CISA ICS advisories for Inductive Automation, Django security archive, GitHub Security Advisories, OSV, PyPI project pages, PostgreSQL security pages and release announcement, X41 Starlette advisory; full URL list is in `security/source_notes.md`.
- Query terms: Django, gunicorn, Starlette, python-multipart, Playwright, httpx, idna, psycopg/libpq, `@opencode-ai/plugin`, `opencode-ai`, cross-spawn, QuestDB, PostgreSQL, Ignition, Inductive Automation, WebDev, htmx.

## Blockers

- `uv export` process-substitution audit commands were still blocked by the command allowlist, so temporary pinned requirement files under `security/` were used for `pip-audit` and deleted afterward.
- `uv run python -m django --version` remained blocked by the allowlist, but `uv run python -c "import django; print(django.get_version())"` confirmed Django 5.2.14.
- `osv-scanner` is not installed; `uvx osv-scanner --version` failed because `osv-scanner` was not found in the Python package registry. Use a packaged OSV Scanner binary or npm-based scanner if needed.
- `pip-audit --locked .` does not recognize `uv.lock` in this environment, so lock audits required exported/temporary pinned requirements.
- Direct `pip-audit` project audit failed for `web/Flux` and `build` when local editable packages (`flux-build`, `flux-mine`) were treated as PyPI requirements; external dependencies were audited separately.
- CVE Program pages returned JavaScript-only content in the earlier review, so CISA/GitHub/OSV/PostgreSQL/vendor pages were used for advisory detail.
- No deployed environment values were available for Django env vars, host binding, reverse proxy, PostgreSQL server version, Ignition version/platform/service account, or whether endpoints are internet/local-only.
- QuestDB runtime product version is still unresolved: the local endpoint responded, but only with a PostgreSQL compatibility string.
- No container/base-image manifests were found, so OS/openssl/browser package exposure was not assessed.

## Recommended Next Moves

1. Deploy the updated web/Flux and Fluxy locks/package metadata so runtime environments pick up `idna==3.16` and optional MCP `starlette==1.1.0`.
2. Update PostgreSQL client/libpq exposure outside this repo: upgrade local `psql`/libpq to 18.4+ and prefer a `psycopg-binary` wheel or system libpq build that reports a fixed minor version once available.
3. Capture deployed server versions: PostgreSQL `select version();`, Ignition Gateway version/platform/service account, authoritative QuestDB version, and Python/browser versions in the deployed runtime.
4. Patch or verify PostgreSQL server to 18.4/17.10/16.14/15.18/14.23 or newer for the deployed major line.
5. Verify Ignition 8.3.0+ where possible, or document 8.1.x/8.3.x hardening for project imports, Designer/config-write users, and service-account privileges.
6. Define `Flux.auth` before any non-local exposure; start with POST/mutation endpoints and bridge/setup pages.
7. Add a production startup guard for `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and secure cookie settings when deployment stops being dev-only.
