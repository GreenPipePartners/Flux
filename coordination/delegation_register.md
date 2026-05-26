# Coordination Delegation Register

## 2026-05-24 Coordinator setup

- Action: Created the Coordinator routing model and domain notice inbox convention.
- Notices written: none during setup.
- Immediate tasks launched: none during setup.
- Invocation surface: `.opencode/agents/coordinator.md` and `.opencode/commands/coordinate.md`.
- Domain inboxes: `architecture/agent_notices.md`, `testing/agent_notices.md`, `performance/agent_notices.md`, `site_audit/agent_notices.md`, `dependencies/agent_notices.md`, `security/agent_notices.md`, and `typing/agent_notices.md`.
- Next coordination action: use Coordinator for user-directed cross-agent handoffs, next-run reminders, and long-term specialist-agent context.

## 2026-05-24 Docs Steward setup

- Action: Added Docs Steward to the Coordinator routing map and domain notice inbox convention.
- Notices written: `documentation/agent_notices.md` received `2026-05-24-coordinator-001` for Flux.live service contract documentation.
- Immediate tasks launched: none during setup.
- Invocation surface: `.opencode/agents/docs-steward.md` and `.opencode/commands/document.md`.
- Domain inbox: `documentation/agent_notices.md`.
- Next coordination action: route surfaced process documentation, MkDocs navigation hygiene, and Flux.links docs-pointer work to Docs Steward.

## 2026-05-24 Ignition Bridges cleanup routing

- Action: Routed user-reported Ignition Bridges UI, documentation, and architecture concerns to specialist inboxes.
- Notices written: `site_audit/agent_notices.md` received `2026-05-24-coordinator-002` for Ignition Bridges Comp Surface cleanup audit; `documentation/agent_notices.md` received `2026-05-24-coordinator-003` for token/build/version explanations and docs links; `architecture/agent_notices.md` received `2026-05-24-coordinator-004` for persistent interface-health refresh service architecture.
- Immediate tasks launched: none; user asked to send items onward, not to execute specialist work immediately.
- Blocked/routing notes: User said “cleanup,” but no Cleanup agent exists in Coordinator map; UI cleanup observations were routed to Site Auditor for reproducible interaction findings and future cleanup handoff.
- Next coordination action: if the user wants immediate action, launch Site Auditor, Docs Steward, or Architect on the corresponding notice.

## 2026-05-24 Dashboard runtime/live/charts cleanup routing

- Action: Reviewed dashboard code paths enough to route user-reported OPC runtime, stale tag recovery, Flux.charts, Flux.serve, and table-copy issues to specialist inboxes.
- Immediate tasks launched: Explore task `ses_1a44cfa45ffejkhAzBgI3vY494` was launched for OPC runtime source discovery but returned no useful summary; Coordinator then used direct file inspection.
- Notices written: `architecture/agent_notices.md` received `2026-05-24-coordinator-005` for OPC server runtime truth/PID/port contract and `2026-05-24-coordinator-008` for Flux.charts stress-load restoration/pagination architecture.
- Notices written: `site_audit/agent_notices.md` received `2026-05-24-coordinator-006` for runtime service observability UI, `2026-05-24-coordinator-007` for Flux.live stale recovery/import cleanup, `2026-05-24-coordinator-009` for Flux.charts large-list cleanup, and `2026-05-24-coordinator-011` for table copy affordance coverage.
- Notices written: `documentation/agent_notices.md` received `2026-05-24-coordinator-010` for Import chart CSV help/example content.
- Blocked/routing notes: Direct Cleanup routing remains blocked because no Cleanup agent exists in the Coordinator map; UI cleanup requests were routed to Site Auditor. Actual OS process/port verification for OPC runtimes was blocked by current bash tool policy, so the truth question was routed to Architect based on code-level ambiguity.
- Next coordination action: if immediate work is desired, launch Architect for notices `005`/`008`, Site Auditor for notices `006`/`007`/`009`/`011`, or Docs Steward for notice `010`.
