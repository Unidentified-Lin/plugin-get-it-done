# Domain Knowledge

_Project-specific facts about the **problem domain** — what this project is solving, who uses it, what the rules of the domain are._
_Read by: Planner, Analyst (and Executor when domain logic affects implementation)._
_Updated by: Reflector when a domain fact surfaces that future cycles should know._

## Active Knowledge

_(empty — populated as Reflector observes domain-specific facts that matter)_

## Format

```
### DK-XXX | Source: VAL-XXX | <stakeholder-quote> | <observation>
**Fact**: One clear statement about the domain.
**Why it matters**: Which decisions this changes (PRD scope, NFR target, validation strictness, etc.).
**Confidence**: high | medium | low (low = inferred, hasn't been confirmed by stakeholder)
```

## What belongs here vs not

✅ **Belongs**: "this is a multi-tenant SaaS", "all data must be HIPAA-compliant", "users are non-technical accountants", "the legacy system this replaces had a 30-second timeout that users adapted to".

❌ **Does NOT belong**:
- Tech-stack details → `tech_stack.md`
- Code paths and quirks → `codebase_map.md`
- Architecture decisions made → `decisions.md`
- Cross-project agent-team patterns → `${CLAUDE_PLUGIN_DATA}/team_learnings/`
