---
description: Run Architect's default architecture review and write an arch_review.md report.
agent: architect
subtask: true
---

Do an architectural review of the codebase based on the project design, and write up remarks on opportunities to improve the codebase structurally.

Arguments:
- Full invocation: `$ARGUMENTS`
- Optional output directory: `$1`

Interpret the first argument as the project-local output directory when it looks like a directory path. Treat all remaining words as the review scope. If the first argument is missing or does not look like a directory path, write to `arch_review.md` in the project root and treat the full invocation as the review scope. If no scope is provided, review the current project architecture broadly.

If an output directory is provided, write the report to:

`$1/arch_review.md`

If no output directory is provided, write the report to:

`arch_review.md`

Before writing, inspect the relevant code and adjacent boundaries. If the output directory is ambiguous, outside the project, or would not produce a file named `arch_review.md`, ask for clarification instead of writing.

Do not edit application code. Do not write any other file. After writing the report, summarize the report path and the highest-severity findings in the chat.
