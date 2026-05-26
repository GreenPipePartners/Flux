# Coordination Core Area Files

Last updated: 2026-05-24 during Coordinator agent setup.

## Ownership

Coordinator owns agent-routing records, durable cross-agent handoffs, and the notice conventions used by Flux specialist agents.

Coordinator does not own application code, tests, architecture reports, dependency reports, security reports, site-audit reports, performance reports, type refactors, runtime config, generated data, or agent definitions outside its own setup.

## Owned Files

- `coordination/core_area_files.md` - this continuous coordination index.
- `coordination/delegation_register.md` - central append-only register of notices written, immediate delegations launched, blocked routing decisions, and cross-agent follow-ups.
- `coordination/daily/coordination_YYYY-MM-DD/coordination_YYYY-MM-DD.md` - append-only daily Coordinator activity ledger.

## Invocation Surface

- `.opencode/agents/coordinator.md` - Coordinator agent definition and routing prompt.
- `.opencode/commands/coordinate.md` - slash command that runs Coordinator for user-provided routing instructions.

## Writable Domain Notice Inboxes

- `architecture/agent_notices.md` - Architect notices.
- `testing/agent_notices.md` - Tester notices.
- `performance/agent_notices.md` - Performance notices.
- `site_audit/agent_notices.md` - Site Auditor notices.
- `dependencies/agent_notices.md` - Dependency Steward notices.
- `security/agent_notices.md` - Threat Watch notices.
- `typing/agent_notices.md` - Type Steward notices.
- `documentation/agent_notices.md` - Docs Steward notices.

## Notice Contract

Coordinator appends notices. Target agents append outcomes when they act on a notice. Prior notices should not be deleted, reordered, or rewritten.

Each notice should name one owning agent, one request, the horizon, priority, acceptance signal, relevant context paths, and any sequencing or blockers.

## Agent Map

- Architect: architecture review, boundaries, coupling, maintainability, structural performance risk, and Comp Surface architectural consistency.
- Tester: test additions, test execution, broad test audits, test intent logs, and failure explanation without production fixes.
- Performance: repeatable performance tests, benchmark fixtures, IO-loop visibility, performance records, and suspected performance causes.
- Site Auditor: running-site route/UI/accessibility/HTMX drift audits, browser interaction checks, and baseline comparison.
- Dependency Steward: dependency inventory, version watch, update impact, removal candidates, and dependency decisions without manifest edits.
- Threat Watch: dependency-scoped cybersecurity intelligence and exposure notes tied to the repository stack.
- Type Steward: Python typing boundaries, typed assets, ty checks, and small behavior-preserving typed refactors.
- Docs Steward: MkDocs documentation, surfaced process capture, docs navigation hygiene, and Flux.links/copy-context docs pointer alignment.
- Explore: fast codebase exploration when ownership is not yet clear.
- General: one-off research or multi-step work that does not fit a specialist.

## Conventions

- Immediate work may be delegated with the task tool only when the user asks for it now.
- Next-run and long-term work should usually become domain notices instead of immediate task launches.
- Split multi-agent requests into separate notices rather than one vague omnibus notice.
- Notices never override a target agent's own permissions or mission.
