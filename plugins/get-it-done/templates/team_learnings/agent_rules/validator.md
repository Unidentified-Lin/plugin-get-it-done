# Validator Dynamic Rules

_Learned behavioral rules specific to the Validator agent._
_Updated by Reflector. Read by Validator at the start of every run._

## Rules

### VR-001 | Priority: high
**Rule**: For research/audit deliverables, spot-check at least two pieces of cited evidence by opening the referenced file at the referenced line number. Record the spot-check in `Validator Notes`.
**Reason**: Line-level spot-checking is what makes the validation itself credible.

### VR-002 | Priority: high
**Rule**: When resetting a task to `Status: pending` on validation fail, also clear the `Artifact:` field (set to empty/null) so the next Executor cycle does not reuse a rejected file. Note the reset in Validator Notes.
**Reason**: A stale `Artifact:` path on a failed task risks corrupt append-rewrites on retry.

### VR-003 | Priority: low
**Rule**: When spot-checking an artifact's cited line range, verify BOTH endpoints (start and end line). If the artifact's claimed end line overshoots the actual end, record the discrepancy as a non-blocking near-miss in `notes` — do not fail the validation if the content at the cited start line + section header matches, but the precision lapse should be visible to Reflector.
**Reason**: End-line overshoot is a recurring precision near-miss; encoding the validator's discretion makes the response reproducible.

### VR-004 | Priority: high
**Rule**: In v2, the dispatcher does NOT cap retries. Set `escalate_to_blocked: true` in the agent-return ONLY when continued rework is unlikely to converge. Any one of the following is sufficient: (a) the same criterion ID has appeared in `fail_reasons` for **≥3 prior Validation Results** on this task and the latest artifact still fails the same ID; (b) the task as written cannot be satisfied without Planner changing the task definition (metrics describe an impossibility, or two criteria contradict); (c) the executor has shipped fundamentally different (and worse) attempts each time, suggesting they do not understand the task. Do NOT escalate for "this task is hard" or "I'm impatient at attempt 1-2".
**Reason**: Premature escalation strands work behind human review; late escalation burns tokens on a non-converging loop. The three criteria split the difference using observable signal in the task history.

### VR-005 | Priority: medium
**Rule**: When metrics.md is silent on a behavioral detail and `.get-it-done/prd.md` exists with a relevant `PRD-Ref:`, treat the PRD's Functional Requirements / Data Model / Edge Cases sections as the clarifier. But never pass or fail on PRD content that no metric covers — the metrics' binary criteria are the only judges. If the PRD demands something the metrics don't, the gap is a Planner problem (raise it via `fail_reasons` referencing the missing criterion, not the present PRD line).
**Reason**: PRD scope creep into validation produces unreproducible pass/fail outcomes and undermines the planner→validator contract.

### VR-006 | Priority: high
**Rule**: In `mode: milestone`, every entry you put in `task_ids_to_rework` MUST be backed by a specific evidence statement in `fail_reasons` that ties THAT task's contribution to an integration defect (not a generic "something's wrong"). Pattern: "T-007 produces field `userId: string` but T-013 consumes `user_id: number` (criterion M2-AC1: cross-task schema agreement)". When you cannot pinpoint a task whose work is the defect's source, that's the signal to leave `task_ids_to_rework: []` and let the dispatcher fall back to PLANNING — do NOT pad the list to avoid the structural-fail path.
**Reason**: Unbacked `task_ids_to_rework` entries flip tasks to needs_rework with no useful feedback for the executor, who then re-executes blindly and re-fails. Structural failures (the milestone itself is mis-shaped) need Planner intervention; padding the rework list with random tasks bypasses that and burns executor cycles.

## Format

```
### VR-XXX | Priority: high | medium | low
**Rule**: Specific behavioral instruction.
**Reason**: Why this rule exists (what failure it prevents).
```
