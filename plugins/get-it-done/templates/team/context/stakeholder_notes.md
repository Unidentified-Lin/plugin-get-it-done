# Stakeholder Notes

_Project-specific people-context: who cares about what, what trade-offs have been pre-decided by stakeholders, what's politically/organizationally sensitive._
_Read by: Planner (for scope and priority), Validator (for "is this what the stakeholder asked for?"-checks)._
_Updated by: Reflector when stakeholder context surfaces during AWAITING_HUMAN resolution or in goal text._

## Active Notes

_(empty — populated as stakeholder context surfaces)_

## Format

```
### SN-XXX | Role: <stakeholder role, not name unless explicitly OK> | Sensitivity: low | medium | high
**Context**: One paragraph — what this stakeholder cares about, what they've already decided, what they want left alone.
**Source**: VAL-XXX or `/objective` quote or AWAITING_HUMAN resolution.
```

## What belongs here vs not

✅ **Belongs**: "the eng-lead wants zero scope creep on milestone 1; new features go to milestone 2 even if they look small", "the design team has already chosen the colour palette; agents should not propose alternatives", "compliance wants no PII in any log line".

❌ **Does NOT belong**:
- Domain facts ("HIPAA applies") → `domain_knowledge.md`
- Architectural choices already made → `decisions.md`
- Personal info beyond role (don't write names, emails, etc. unless explicitly OK)
