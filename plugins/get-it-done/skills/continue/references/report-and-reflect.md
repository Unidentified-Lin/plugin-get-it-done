# `report_and_reflect()` — runs once when the goal closes

> **Load when**: `SKILL.md` Step 5 or Step 11 says to run `report_and_reflect()` (phase == REPORTING).

Reflector is NOT part of the relay. It runs once per goal, after every task reaches `Status: done`.

```
1. Read .get-it-done/goal.md, .get-it-done/task_queue.md, last ~20 entries of .get-it-done/validation_log.md.
1.5 Degraded-validation sweep: grep .get-it-done/validation_log.md for "DEGRADED:" and
    "INDIRECT_EVIDENCE:" among entries belonging to this goal (since the latest [NEW_GOAL]/[GOAL_REFINED]).
    Two distinct markers — treat them differently:
    - `INDIRECT_EVIDENCE:` — structural platform limitation (e.g. validator had no shell/build
      access and used dispatcher-provided output or source inspection as a proxy). Expected
      in code/config tasks when the agent runtime lacks shell tools. Does NOT require human
      manual verification — the dispatcher already provided the evidence. Do NOT include in
      the ⚠️ 人工確認清單.
    - `DEGRADED:` — unexpected inability to verify (e.g. browser unavailable for a UI test,
      external API unreachable for an integration test). Requires human follow-up. IF any
      `DEGRADED:` entries found:
      - append "<ISO> [DEGRADED_VALIDATION] <task IDs + reasons>" to progress_log.md
      - the [GOAL_COMPLETE] message MUST include a prominent "⚠️ 人工確認清單" section
        listing each degraded task ID, the reason, and what the human should manually verify.
        The goal still closes — but the user must not discover the gap by accident.
1.6 Final commit consolidation (worktree mode): IF git_state.json `commit_granularity == goal`,
    run `python3 "$GID_PY" consolidate-final` (collapses every milestone commit into one; skips
    cleanly if already a single commit or the branch is pushed). For the default `milestone`
    granularity, history is already one-commit-per-milestone from Step 9 — no action.
2. Append to .get-it-done/progress_log.md:
     "<ISO> [GOAL_COMPLETE] <goal one-liner>. <N> tasks completed across <M> milestones; first-pass rate <X>/<Y>. Key deliverables: <bullet list of .get-it-done/workspace/exec-*/ artifact paths>."
3. Rewrite state.md YAML: phase=COMPLETE, status=WAITING, batch_id=null, batch_started_at=null, batch_ended_at=null, active_agents=[], last_updated=<ISO>. Remove the most recent `## Batch` block IFF its `next_phase == REPORTING` (it's now stale).
4. Emit the [GOAL_COMPLETE] paragraph to the user (including the ⚠️ 人工確認清單 when step 1.5 found degraded validations). In worktree mode, report the goal branch and that the user's own branch is untouched: read `goal_branch` from git_state.json and add — "原始碼變更已累積在分支 `<goal_branch>`（<N> commits，每 milestone 一個；`git log --oneline <goal_base>..<goal_branch>`）。你的工作分支與工作目錄未被更動 —— 請自行 review / merge / 開 PR 此分支。" **Do NOT auto-merge into the user's branch.** Leave the `_goal` worktree and `gid/goal-<slug>` branch in place (only `/objective` or `/adjust hard` wipes them).
5. **Reflector gate (skip for small goals).** Count the task entries (`### T-XXX:` headings) in `.get-it-done/task_queue.md`.
   - **`task_count <= 2`** → do NOT spawn reflector. A goal this small carries too little signal to be worth an opus reflection pass (no batch-parallelization dynamics, ≤2 validation cycles, no DAG-shape evidence). Append `<ISO> [REFLECT_SKIPPED] task_count=<N> (<=2; small goal)` to progress_log.md and skip to step 6.
   - **`task_count >= 3`** → resolve the persistent per-project B-side dir first, then spawn reflector:
     ```bash
     BSIDE=$(python3 "$GID_PY" bside-dir --base "${GID_BASE:-.}" --plugin-data "$PLUGIN_DATA")   # → {"ok":true,"path":...}; use .path
     ```
     Spawn reflector via Agent tool. Prompt: "Execute your reflector role per agents/reflector.agent.md. The goal just COMPLETE'd. **bside_context_dir: `<BSIDE.path>`** (absolute — write/read ALL B-side learnings here, NOT .get-it-done/context/). Analyse validation_log + progress_log + the most recent batch handoffs. Update A-side and B-side learnings per your classification matrix. Do NOT change .get-it-done/state.md phase. Do NOT emit an agent-return block — your output is the file writes themselves."
     (If `bside-dir` fails — e.g. Python/git unavailable — fall back to passing `bside_context_dir: .get-it-done/context` so reflection still runs, degraded to the old per-goal scope; append `<ISO> [BSIDE_FALLBACK] <reason>` to progress_log.md.)
6. Reflector returns (or was skipped); EXIT. Reflection failures are logged ([REFLECT_FAIL]) but do NOT roll back COMPLETE.
```
