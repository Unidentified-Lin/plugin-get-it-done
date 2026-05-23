# Handoff Lessons

_Cross-project learnings specifically about agent-to-agent handoffs: what the previous agent needs to leave in its agent-return `notes`, its artifact file (executor scratch, analyst findings, PRD sections, etc.), and the task_queue / metrics so the next agent — typically a Validator on the same task, an Executor reading a Planner's task, or a Planner reading Analyst findings — can pick up without re-reading everything._

_Reflector writes here when a validation failure or cycle slowdown traces back to "the next agent didn't have what it needed at handoff time."_

## Lessons

_(none yet — new observations land here)_

## Format

```
### HL-XXX | From: <agent> | To: <agent> | Priority: high | medium | low
**Symptom**: What went wrong at handoff (next agent re-did work, asked redundant questions, missed context, etc.).
**Root cause**: What the upstream agent failed to leave behind.
**Required leave-behind**: Concrete checklist of what the upstream agent MUST include in its agent-return `notes`, in its artifact / scratch dir files, or in the planner-owned task_queue / metrics entries for this handoff to succeed.
**Observed in**: VAL-XXX, VAL-XXX, ...
```

## Why this is separate from `agent_rules/`

`agent_rules/<name>.md` captures "rules an agent must follow during its own work." `handoff_lessons.md` captures "the contract between two agents at the moment of transition." A handoff lesson typically generates **two** entries in agent_rules (one for the upstream agent's "what to leave" duty, one for the downstream agent's "what to expect" duty) — this file is where the underlying lesson lives.
