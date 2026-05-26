---
description: Run the Performance agent to build or run repeatable performance tests and update performance records.
agent: performance
subtask: true
---

Run a performance testing session.

Arguments:
- Full invocation: `$ARGUMENTS`

Treat the invocation as the sensitive performance area, performance concern, or test target. If no specific area is provided, inspect current performance records and recommend the next highest-value performance test target before writing new tests.

For the requested performance area:
- define the performance hypothesis
- identify repeatable inputs and stable assertions
- implement or update tests only in allowed test/performance paths
- run the relevant tests or document blockers
- investigate failing tests without fixing application code
- update `performance.md`, `performance/performance_report.md`, `performance/performance_tests.md`, and `performance/performance_persistance.md`

Do not edit application code. Do not fix production behavior. If a test requires a production seam, dependency, persistent data, Ignition gateway state, or setup step that does not exist, document the need and ask for direction.

When done, summarize the tests added or run, the result, suspected failure causes, persistent data needs, and the next recommended performance move.
