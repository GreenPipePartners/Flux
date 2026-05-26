---
description: Run Tester to add, run, or document tests for a requested area.
agent: tester
subtask: true
---

Run a testing session using Tester.

Arguments:
- Full invocation: `$ARGUMENTS`

Treat the invocation as the behavior, risk, bug, module, or test target. If no specific target is provided, inspect the project test structure and recommend the next highest-value test target before adding new tests.

For the requested target:
- understand the behavior or risk being tested
- add focused tests when useful and safe
- update `test_log.md` or a package-local `test_log.md` with test intent and covered cases
- run focused tests first, then broader relevant suites when practical
- explain likely causes when tests fail
- recommend what would make future testing more autonomous

Do not edit application code. Do not fix production behavior unless explicitly asked. If the test requires a new application seam, dependency, persistent data, external service, database, or Ignition gateway state, document the need and ask for direction.

When done, summarize tests added or run, log updates, failures, suspected causes, and next recommended test moves.
