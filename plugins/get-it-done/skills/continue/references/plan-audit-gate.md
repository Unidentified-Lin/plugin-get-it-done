# Plan audit gate — quality check before EXECUTING

> **Load when**: `SKILL.md` Step 9 says to run the plan audit gate (planner return has `next_phase_request: EXECUTING`).

The autonomous path has no human plan review — this gate is its substitute. It catches the most expensive failure mode (a whole goal executed against vague or unverifiable criteria) for the cost of one extra spawn.

```
audit_fails := count of [PLAN_AUDIT_FAIL] lines in progress_log.md SINCE the latest
               [NEW_GOAL] or [GOAL_REFINED] line (current goal only)
IF audit_fails >= 2:
    # Avoid planner↔reviewer ping-pong; two strikes and we proceed with a warning.
    append "<ISO> [PLAN_AUDIT_SKIPPED] max audit rounds reached; proceeding to EXECUTING"
    rm -f .get-it-done/plan_audit.md
    set phase = EXECUTING
ELSE:
    spawn get-it-done:plan-reviewer (single Agent call, NOT a batch member) with mode `queue-audit`
    and absolute paths to: .get-it-done/task_queue.md, .get-it-done/metrics.md,
    .get-it-done/goal.md, .get-it-done/prd.md (if it exists).
    Parse its ---agent-return--- block (role: plan-reviewer, verdict: pass|fail, fail_reasons).
    IF verdict == pass (or the return is malformed — the gate must not deadlock the pipeline):
        append "<ISO> [PLAN_AUDIT_PASS]" (or "[PLAN_AUDIT_PASS] (malformed return — waved through)")
        rm -f .get-it-done/plan_audit.md
        set phase = EXECUTING
    IF verdict == fail:
        write the full fail_reasons list to .get-it-done/plan_audit.md (dispatcher-owned file;
        overwrite). Append "<ISO> [PLAN_AUDIT_FAIL] <one-line summary>".
        keep phase = PLANNING — next tick re-spawns planner, which reads plan_audit.md
        (listed in its inputs) and MUST address every issue before re-emitting EXECUTING.
```
