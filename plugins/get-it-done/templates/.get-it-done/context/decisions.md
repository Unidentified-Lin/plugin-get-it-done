# Architectural Decisions

_Project-specific decisions that have been made and are settled. Future cycles read this so they don't re-litigate questions that already have answers._
_Read by: Planner, Analyst, Executor, Validator._
_Updated by: Reflector when a non-trivial decision is made during a cycle (typically during PLANNING or after AWAITING_HUMAN resolution)._

## Active Decisions

_(empty — populated as decisions are made)_

## Format

```
### AD-XXX | Status: accepted | superseded-by-AD-YYY | deprecated
**Decision**: One-sentence statement of what was decided.
**Date**: ISO date.
**Context**: What forced the decision (2-3 sentences max).
**Alternatives considered**: Brief, what was rejected and why.
**Consequences**: What downstream choices this locks in.
```

## What belongs here vs not

✅ **Belongs**: "AD-001: use SQLite for v1, migrate to Postgres at v2 when multi-user lands", "AD-002: optimistic UI for all writes, accepting staleness; rejected pessimistic with loading spinner because the prod traffic pattern makes it noticeably slower".

❌ **Does NOT belong**:
- Tactical tech choices that aren't strategic → `tech_stack.md`
- Reasoning about domain rules → `domain_knowledge.md`
- "What we tried but didn't merge" — superseded decisions stay here with `Status: superseded-by-...`; experimental dead-ends don't need an entry.
