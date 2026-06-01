# Conventional Review Checklist — Engineering Standards

> **For**: conventional-reviewer agent (E1 review reference)  
> **Scope**: 適用於 .NET Core / .NET 6+ 專案；.NET Framework 專案不適用本規範。  
> **Usage**: Go through every item against the diff. Mark ✅ / ❌ / ➖.  
> **Severity**: 重大 (Major) = must fix before PR; 輕微 (Minor) = fix in-place OK.  
> **Categories**: 1–8 = universal quality; 9–14 = team coding conventions & structure.

---

## Category 1: Correctness

| # | Item | Default Severity |
|---|------|-----------------|
| 1.1 | Business logic matches the requirements and acceptance criteria | 重大 |
| 1.2 | Edge cases identified in 需求重點/限制條件 are handled | 重大 |
| 1.3 | No off-by-one errors in loops or index-based access | 重大 |
| 1.4 | Conditional branches cover all meaningful states (no implicit fall-through) | 重大 |
| 1.5 | Return values and status codes are correct for each scenario | 重大 |

---

## Category 2: Error Handling

| # | Item | Default Severity |
|---|------|-----------------|
| 2.1 | All external calls (DB, HTTP, file I/O) are wrapped with appropriate error handling | 重大 |
| 2.2 | Exceptions are not silently swallowed (at minimum, logged before swallowing) | 重大 |
| 2.3 | User-facing error messages do not expose internal stack traces or sensitive data | 重大 |
| 2.4 | Null / empty input is checked at entry points; meaningful error returned | 重大 |
| 2.5 | Retry logic (if any) has a bounded retry count and backoff strategy | 重大 |

---

## Category 3: Security

| # | Item | Default Severity |
|---|------|-----------------|
| 3.1 | No sensitive data (tokens, passwords, PII) logged or included in error responses | 重大 |
| 3.2 | SQL queries use parameterised statements or ORM; no string concatenation | 重大 |
| 3.3 | Input from external sources is validated / sanitised before use | 重大 |
| 3.4 | New API endpoints have appropriate authentication/authorisation checks | 重大 |
| 3.5 | No hardcoded credentials or secrets in code | 重大 |

---

## Category 4: Data Integrity

| # | Item | Default Severity |
|---|------|-----------------|
| 4.1 | Database writes that must be atomic are wrapped in a transaction | 重大 |
| 4.2 | Concurrent modification scenarios are considered (optimistic lock / version check) | 重大 |
| 4.3 | No unintended data mutation (objects modified by reference when immutability expected) | 重大 |
| 4.4 | Schema changes are backward-compatible or accompanied by a migration plan | 重大 |

---

## Category 5: Performance

| # | Item | Default Severity |
|---|------|-----------------|
| 5.1 | No N+1 query patterns in loops | 重大 |
| 5.2 | Large result sets are paginated or streamed; not loaded entirely into memory | 重大 |
| 5.3 | No unbounded loops that could run indefinitely on bad input | 重大 |
| 5.4 | New DB queries on frequently-called paths have appropriate indexes considered | 輕微 |

---

## Category 6: Code Quality

| # | Item | Default Severity |
|---|------|-----------------|
| 6.1 | No leftover debug code (commented-out blocks, `Console.WriteLine`, throwaway logs) | 輕微 |
| 6.2 | Magic numbers/strings are replaced with named constants or configuration values | 輕微 |
| 6.3 | Method names accurately describe what they do | 輕微 |
| 6.4 | No duplicated logic that could be extracted into a shared helper | 輕微 |
| 6.5 | Methods are reasonably sized (single responsibility; not doing 5 things at once) | 輕微 |
| 6.6 | No unused variables, imports, or dead code paths added | 輕微 |

---

## Category 7: Test Coverage

| # | Item | Default Severity |
|---|------|-----------------|
| 7.1 | Changed business logic has corresponding unit test coverage | 重大 |
| 7.2 | Tests cover the happy path and at least one failure/edge case | 重大 |
| 7.3 | All existing tests still pass (no regressions) | 重大 |
| 7.4 | Tests are deterministic (no dependency on external state or time without mocking) | 重大 |
| 7.5 | Test assertions are meaningful (not just "does not throw") | 輕微 |

---

## Category 8: Maintainability

| # | Item | Default Severity |
|---|------|-----------------|
| 8.1 | Non-obvious logic has a brief inline comment explaining the "why" | 輕微 |
| 8.2 | TODO comments include a ticket reference (not "TODO: fix later") | 輕微 |
| 8.3 | Public API surface (method signatures, DTOs) is consistent with existing conventions | 輕微 |
| 8.4 | Configuration changes are documented (at minimum, a comment next to the key) | 輕微 |

---

## Category 9: Coding Conventions

| # | Item | Default Severity |
|---|------|-----------------|
| 9.1 | Inline comments inside method bodies use `////` (four slashes) for logic explanations; each major logic block has at least one `////` comment | 輕微 |
| 9.2 | Boolean checks use explicit `== false` instead of `!` operator (e.g., `if (isValid == false)` not `if (!isValid)`) | 輕微 |
| 9.3 | Each file contains only one class; additional classes must be private/internal nested classes if needed | 輕微 |
| 9.4 | DTO class names follow the project's suffix convention (e.g., `Entity`, `Dto`, `Model`) consistently across all layers | 輕微 |
| 9.5 | All methods are asynchronous when involving I/O, with `Async` suffix (e.g., `GetOrderAsync`) | 輕微 |
| 9.6 | Constructor injection is the only DI pattern used; no `new` instantiation of service dependencies | 重大 |
| 9.7 | Newly introduced services/repositories are registered in the DI container (e.g., `ServiceCollectionExtension`) | 重大 |
| 9.8 | `using` statements are applied to all `IDisposable` objects; no manual `Dispose()` calls | 輕微 |
| 9.9 | No magic numbers/strings — replaced with named constants, enums, or config values | 輕微 |
| 9.10 | `StringBuilder` used for string concatenation in loops; `string.Compare()` for case-insensitive checks | 輕微 |

---

## Category 10: Architecture & Structure

| # | Item | Default Severity |
|---|------|-----------------|
| 10.1 | File length does not exceed 500 lines | 輕微 |
| 10.2 | Method length does not exceed 50 lines | 輕微 |
| 10.3 | Cyclomatic complexity per method ≤ 10 (no deeply nested branches) | 輕微 |
| 10.4 | Constructor has ≤ 5 injected dependencies; if exceeded, consider splitting the class | 輕微 |
| 10.5 | Layering is respected: Controller → Service → Repository; no layer-skipping calls (e.g., Controller calling Repository directly) | 重大 |
| 10.6 | Business logic resides in Service layer, not in Controllers or Repositories | 重大 |
| 10.7 | Cross-layer utilities are placed in the shared Common/Utils project, not duplicated per layer | 輕微 |
| 10.8 | Each Service has a corresponding interface (`I{Name}Service` + `{Name}Service`) | 輕微 |
| 10.9 | Multi-tenant isolation is enforced: requests are scoped to the authenticated tenant/shop context; no cross-tenant data leakage | 重大 |

---

## Category 11: Naming Conventions

| # | Item | Default Severity |
|---|------|-----------------|
| 11.1 | Classes, structs, delegates use PascalCase (e.g., `OrderService`, `CartItem`) | 輕微 |
| 11.2 | Interfaces have `I` prefix (e.g., `IOrderRepository`) | 輕微 |
| 11.3 | Private fields use `_` + camelCase (e.g., `_orderRepository`) | 輕微 |
| 11.4 | Parameters and local variables use camelCase (e.g., `orderId`, `shopId`) | 輕微 |
| 11.5 | Enum types include a suffix (e.g., `Enum` or `Type`) per project convention (e.g., `PaymentStatusEnum`) | 輕微 |
| 11.6 | Method names follow Verb + Noun pattern (e.g., `GetOrder`, `CreatePayment`, `ValidateInput`) | 輕微 |
| 11.7 | Boolean properties/variables use `Is`/`Can`/`Has` prefix in positive form (e.g., `IsEnabled`, not `IsNotDisabled`) | 輕微 |
| 11.8 | No abbreviations in identifiers — use full words (`command` not `cmd`, `button` not `btn`) | 輕微 |
| 11.9 | 2-char acronyms stay uppercase (`ID`, `UI`); 3+ char acronyms use PascalCase (`Xml`, `Http`, `Api`) | 輕微 |
| 11.10 | Identifier names are ≤ 3 words; longer names indicate the concept should be decomposed | 輕微 |

---

## Category 12: Documentation & Comments

| # | Item | Default Severity |
|---|------|-----------------|
| 12.1 | All public classes have `/// <summary>` XML documentation | 輕微 |
| 12.2 | All public methods have `/// <summary>` with `<param>` and `<returns>` as applicable | 輕微 |
| 12.3 | Constructor and private fields have `/// <summary>` (per project convention) | 輕微 |
| 12.4 | Test methods have `/// <summary>` describing the test intent (complements `DisplayName`) | 輕微 |
| 12.5 | Migrated/legacy code includes knowledge-preservation markers (`WHY`, `EDGE`, `RISK`, `VERIFY`); unused markers are explicitly `N/A` | 輕微 |

---

## Category 13: Test Conventions

| # | Item | Default Severity |
|---|------|-----------------|
| 13.1 | Test class naming follows `{ClassUnderTest}Test` pattern | 輕微 |
| 13.2 | Test method naming follows `{Method}_{Scenario}_{Expected}` pattern | 輕微 |
| 13.3 | `[Fact]` / `[Theory]` has a `DisplayName` in the team's language describing intent | 輕微 |
| 13.4 | Tests are structured with clear AAA (Arrange–Act–Assert) separation | 輕微 |
| 13.5 | All external dependencies are mocked (repositories, HTTP clients, loggers); no real I/O in unit tests | 重大 |
| 13.6 | Each test verifies one behavior/outcome (single responsibility) | 輕微 |
| 13.7 | Parameterized tests (`[Theory]`) are used for multiple input scenarios rather than duplicating test methods | 輕微 |
| 13.8 | Assertions use expressive library (e.g., FluentAssertions) rather than bare `Assert.True` | 輕微 |

---

## Category 14: Quality Gate (Definition of Done)

| # | Item | Default Severity |
|---|------|-----------------|
| 14.1 | Build succeeds with zero errors | 重大 |
| 14.2 | All unit tests pass | 重大 |
| 14.3 | No new compiler warnings introduced compared to baseline | 重大 |
| 14.4 | No tests were deleted or weakened to make them pass; behavior changes are documented | 重大 |
| 14.5 | Indentation is 4 spaces consistently; no tab characters | 輕微 |
