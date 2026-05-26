Outstanding Product Hardening
1. Review the dirty worktree
- The worktree is very large.
- Some changes predated this session or came from agents.
- Need separate “ours vs existing” review before commit/PR.

2. Package into coherent commits
- Suggested split:
-
Bootstrap-Bob fixture
-
Live scope CSV support
-
Trace scope CSV support
-
Sampling/demand/metadata
-
Flux.plane boundary
-
Flux.test runner
-
FieldAgent/Ignition acceptance cleanup
3.
Harden Flux.plane
-
It currently has a minimal boundary:
-
runtime bad-quality writes
-
Plane sample seeding
-
Next step is deciding whether Flux.plane becomes a real Django app/module with documented ownership of runtime/history writes.
4.
Historian recovery
-
getConfiguration history metadata is live.
-
Actual historian recovery logic is not complete.
-
Current path discovers metadata and samples live tags; it does not yet backfill from Ignition historian.
5.
Bootstrap-Bob as installed verification
-
Bootstrap-Bob is persistent in Flux and usable by acceptance.
-
Need decide whether it should be auto-installed/migrated for every installation or kept as explicit install_bootstrap_bob.
6.
Demand lease cleanup
-
Demand reset works from live/trace paths.
-
Lease semantics are still simple.
-
Later cleanup: named demand reasons, source tracking, lease refresh policies, operator/session attribution.
7.
Trace scope maturity
-
Generic trace scope import works.
-
UX still needs fuller production treatment:
-
stable dropdown source model
-
staged movement polish
-
compression disclosure hardening
-
embed control contract
8.
Security hygiene
-
WebDev AUTH_TOKEN values were scrubbed from files.
-
Need decide final auth stance:
-
auth disabled for local dev
-
tokenized for production
-
ensure deploy tooling never writes secrets into tracked files unintentionally
9.
Navigation seed resilience
-
I made live pages tolerate missing nav seed rows.
-
Need add/verify a small nav test if not already covered.
10.
Test DB workflow
-
--reuse-db is useful for Flux.test.
-
Stale reused DB can miss seed rows.
-
We should document:
-
use --create-db after migrations/seed changes
-
use --reuse-db for repeated closed-loop runs
Architecture Watch Items
-
Flux.cell is still correctly deferred.
-
Flux.lock is still correctly deferred.
-
Pressure is building around:
-
stale/recovery semantics
-
Bootstrap-Bob fixture identity
-
group/kind repeated shape
-
Not enough yet to force full Cell models, but close.
