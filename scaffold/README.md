# Flux Scaffold

This directory is a scaffold around Flux, not Flux source architecture.

Gardens preserve local node/module context. Labyrinths preserve bounded cross-node path context. The Meta-Architect reviews curator output and decides whether findings become Build work, tests, docs, or architecture updates.

## Authority Rules

- Canonical truth remains source code, tests, migrations, Master Design, and accepted architecture logs.
- Garden and labyrinth curators may write only scaffold notes, scaffold test proposals, scaffold trial logs, and scaffold findings.
- Curators must not modify application source, migrations, templates, production tests, dependency files, runtime config, or generated production data.
- Curators must cite source files and existing tests for every finding.
- A labyrinth observes cross-node behavior; it never owns project behavior.
- Transcript conclusions are disposable until distilled into a finding, test, docs change, or architecture note.

## Low Curator Mode

Use a lower-reasoning model or `Low` reasoning mode when the runner supports it. If the runner cannot set model-level reasoning, enforce Low mode by prompt:

- use short evidence lists
- do not infer beyond cited files
- do not propose application edits
- prefer one bounded contract over broad analysis
- stop after the requested output schema is filled

## Starter Pilot

- Garden: `scaffold/gardens/flux_plane/`
- Labyrinth: `scaffold/labyrinths/current_state_display__plane__spot__web/`

Expansion is allowed only after the pilot proves it reduces confusion or catches a real boundary risk.
