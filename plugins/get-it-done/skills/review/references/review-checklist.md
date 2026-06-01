# Code Review Checklist — Universal Engineering Standards

> **For**: code-reviewer agent
> **Usage**: Go through every item against the diff. Mark ✅ / ❌ / ➖.
> **Severity**: Major = must fix before PR; Minor = fix in-place OK.
> **Categories 1–8**: Universal quality standards applicable to any language or framework.

---

## Category 1: Correctness

| # | Item | Default Severity |
|---|------|-----------------|
| 1.1 | Business logic matches the requirements and acceptance criteria | Major |
| 1.2 | Edge cases and boundary conditions are handled | Major |
| 1.3 | No off-by-one errors in loops or index-based access | Major |
| 1.4 | Conditional branches cover all meaningful states (no implicit fall-through) | Major |
| 1.5 | Return values and status codes are correct for each scenario | Major |

---

## Category 2: Error Handling

| # | Item | Default Severity |
|---|------|-----------------|
| 2.1 | All external calls (DB, HTTP, file I/O, APIs) are wrapped with appropriate error handling | Major |
| 2.2 | Errors are not silently swallowed (at minimum, logged before swallowing) | Major |
| 2.3 | User-facing error messages do not expose internal stack traces or sensitive data | Major |
| 2.4 | Null / undefined / empty input is checked at entry points; meaningful error returned | Major |
| 2.5 | Retry logic (if any) has a bounded retry count and backoff strategy | Major |

---

## Category 3: Security

| # | Item | Default Severity |
|---|------|-----------------|
| 3.1 | No sensitive data (tokens, passwords, PII) logged or included in error responses | Major |
| 3.2 | Queries use parameterised statements or ORMs; no string concatenation for queries | Major |
| 3.3 | Input from external sources is validated / sanitised before use | Major |
| 3.4 | New API endpoints have appropriate authentication/authorisation checks | Major |
| 3.5 | No hardcoded credentials or secrets in code | Major |

---

## Category 4: Data Integrity

| # | Item | Default Severity |
|---|------|-----------------|
| 4.1 | Writes that must be atomic are wrapped in a transaction or equivalent mechanism | Major |
| 4.2 | Concurrent modification scenarios are considered (optimistic lock / version check) | Major |
| 4.3 | No unintended data mutation (objects modified by reference when immutability expected) | Major |
| 4.4 | Schema or data format changes are backward-compatible or accompanied by a migration plan | Major |

---

## Category 5: Performance

| # | Item | Default Severity |
|---|------|-----------------|
| 5.1 | No N+1 query patterns or equivalent repeated expensive calls in loops | Major |
| 5.2 | Large result sets are paginated or streamed; not loaded entirely into memory | Major |
| 5.3 | No unbounded loops that could run indefinitely on bad input | Major |
| 5.4 | New queries on frequently-called paths have appropriate indexes considered | Minor |

---

## Category 6: Code Quality

| # | Item | Default Severity |
|---|------|-----------------|
| 6.1 | No leftover debug code (commented-out blocks, console.log, print statements, throwaway logs) | Minor |
| 6.2 | Magic numbers/strings are replaced with named constants or configuration values | Minor |
| 6.3 | Function / method names accurately describe what they do | Minor |
| 6.4 | No duplicated logic that could be extracted into a shared helper | Minor |
| 6.5 | Functions are reasonably sized (single responsibility; not doing many unrelated things) | Minor |
| 6.6 | No unused variables, imports, or dead code paths added | Minor |

---

## Category 7: Test Coverage

| # | Item | Default Severity |
|---|------|-----------------|
| 7.1 | Changed business logic has corresponding unit test coverage | Major |
| 7.2 | Tests cover the happy path and at least one failure/edge case | Major |
| 7.3 | All existing tests still pass (no regressions) | Major |
| 7.4 | Tests are deterministic (no dependency on external state or time without mocking) | Major |
| 7.5 | Test assertions are meaningful (not just "does not throw") | Minor |

---

## Category 8: Maintainability

| # | Item | Default Severity |
|---|------|-----------------|
| 8.1 | Non-obvious logic has a brief inline comment explaining the "why" | Minor |
| 8.2 | TODO comments include a ticket reference (not "TODO: fix later") | Minor |
| 8.3 | Public API surface (function signatures, types) is consistent with existing conventions | Minor |
| 8.4 | Configuration changes are documented (at minimum, a comment next to the key) | Minor |

---

## Category 9: Quality Gate (Definition of Done)

| # | Item | Default Severity |
|---|------|-----------------|
| 9.1 | Build succeeds with zero errors | Major |
| 9.2 | All automated tests pass | Major |
| 9.3 | No new lint warnings or compiler warnings introduced compared to baseline | Major |
| 9.4 | No tests were deleted or weakened to make them pass; behavior changes are documented | Major |
