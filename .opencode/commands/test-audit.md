---
description: Run Tester across the project and write a test_audit.md report.
agent: tester
subtask: true
---

Run a comprehensive test audit across the project using Tester.

Arguments:
- Full invocation: `$ARGUMENTS`
- Optional output directory: `$1`

Interpret the first argument as the project-local output directory when it looks like a directory path. Treat all remaining words as the test scope. If the first argument is missing or does not look like a directory path, write to `test_audit.md` in the project root and treat the full invocation as the test scope. If no scope is provided, test the current project as comprehensively as possible.

If an output directory is provided, write the report to:

`$1/test_audit.md`

If no output directory is provided, write the report to:

`test_audit.md`

Discover and run every reasonable test suite you can find. Collect command results, blockers, recommendations for more autonomous test execution, and guidance on why failures are likely happening. If the audit reveals clear missing tests and there is enough context to add them safely, add focused tests in allowed test paths and update `test_log.md`.

Do not edit application code. Do not fix production behavior. You may write tests, test fixtures, `test_log.md`, and the target `test_audit.md`. After writing the report, summarize the report path, tests added or updated, failing suites, blocked suites, and highest-value autonomy recommendations in chat.
