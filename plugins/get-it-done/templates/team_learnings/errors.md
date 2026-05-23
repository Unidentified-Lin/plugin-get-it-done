# Error Learnings

_Reflector-maintained channel for recurring failures, near-misses, and edge cases observed in validation cycles._
_Distinct from `current.md` (behavioural rules / best practices): this file tracks **what goes wrong**, not what works._
_Every worker agent reads this at run-start to avoid known traps._

## Schema

```
### ERR-XXX | Category | Severity: high | medium | low | First seen: ISO | Last seen: ISO
- **Pattern**: One-sentence description of the recurring failure or near-miss.
- **Category**: MISSING_FEATURE | WRONG_BEHAVIOR | QUALITY | SECURITY | INCOMPLETE | STALE_STATE | SCHEMA_DRIFT | LIFECYCLE_GAP
- **Observed in**: VAL-XXX, VAL-XXX, ...
- **Root cause**: Why this keeps happening — instruction gap, schema mismatch, missing enforcement, etc.
- **Mitigation**: Concrete action agents must take to avoid it.
- **Status**: open | mitigated_in_rules | resolved
```

## Active Error Patterns

_(none — prior entries were tied to the deprecated PROP/heartbeat/archive machinery and have been pruned along with it.)_
