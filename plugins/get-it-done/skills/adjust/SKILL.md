---
name: adjust
description: 修訂或具體化既有目標 — soft 為附加澄清/約束（保留 task_queue / prd / findings / workspace），hard 為重寫 Goal/Success（清空 planner artifacts）。兩種模式皆保留 progress_log、validation_log、.get-it-done/context 與 A-side learnings。Usage：/adjust <修訂訊息>。階段性開發中發現方向歪掉或需要更具體規格時使用。
---

You are executing **/adjust** — the entry point the user reaches for during staged development, when the direction needs correcting or the requirement needs to be made more specific. Compare it with the other two entry points:

- `/objective` — sets a brand-new goal, resets **all** per-goal artifacts.
- `/adjust` — revises the current active goal, selectively preserving existing planner artifacts.
- `/continue` — the dispatcher's main loop.

`/adjust` never calls `/continue` itself — at the end it tells the user to run `/continue` once ready, so planner re-plans against the new goal.

## Parse the message

Extract the content after `/adjust` in the user's message. If empty, ask the user to provide a revision message and stop.

## Step 0a: Resolve GID_BASE (which goal to revise)

`GID_BASE` = that goal's worktree (`<repo>.gid-goals/<slug>`). Every `.get-it-done/...` path in the rest of this skill is under `"$GID_BASE/.get-it-done/..."`, and every `python3 "$GID_PY" <cmd>` (except `git-preflight`/`goals`/`goal-worktree-init`) takes `--base "$GID_BASE"`.

```
GID_PY := "${CLAUDE_PLUGIN_ROOT}/skills/continue/scripts/gid.py"
```

Read `../../references/gid-base.md` §"Resolve" and follow it, then `export GID_BASE`.

## Step 0: Bootstrap (defensive, idempotent)

Read `../../references/platform-adapter.md` §7 "`bootstrap.py init` invocation" and run the block matching your platform, with `--base "${GID_BASE:-.}"` (or `$env:GID_BASE` on Windows).

If `"$GID_BASE/.get-it-done/state.md"` still doesn't exist after bootstrap, stop and tell the user to initialize with `/objective <goal>` first.

## Step 1: Read state and decide whether to pause first

Read the YAML block at the top of `.get-it-done/state.md`. Handle based on `phase` / `status`:

```
IF phase == IDLE OR goal_set == false:
    EXIT — "目前沒有 active goal，無從修訂。請改用 /objective <goal> 設定新目標。"

IF phase == COMPLETE:
    Ask the user: 「目標已完成。要重新打開並修訂嗎？這會走 hard 流程：清空 planner artifacts、保留 progress/validation log。」
    If no → EXIT; if yes → force hard mode (skip the soft option in Step 2).

IF status == RUNNING (dispatcher is running or was interrupted last time):
    # Important: /adjust is a synchronous user action. If status=RUNNING, the previous
    # /continue crashed during spawn / was truncated by context exhaustion / was
    # interrupted. Those sub-agents' returns can no longer be recovered (their sessions
    # ended). So the in-flight markers MUST be actively cleared here, otherwise
    # task_queue would be left with a Claimed_by that never closes — after Step 3 flips
    # state to PLANNING/WAITING, the next /continue's Step 2 won't run crash recovery
    # (its condition is RUNNING), and those claimed/validating tasks would be stuck forever.
    paused_batch := state.batch_id

    # Script path: `rollback-claims` does the whole in-flight rollback deterministically —
    # task_queue (claimed→pending, validating→executed, clear claim; persisted Validation
    # Results / Artifact / Attempts kept), milestones (clear mval claims), research_requests
    # (open+claimed RQs → reassignable), and parks state.md at phase=AWAITING_HUMAN,
    # status=WAITING, batch_ended_at=now, active_agents=[] (goal_set unchanged). It echoes
    # {rolled_back:{tasks,milestones,rqs}}.
    python3 "$GID_PY" log-append --file progress_log.md --base "$GID_BASE" \
        --line "<ISO> [ADJUST_PAUSE_REQUESTED] batch=<paused_batch> — user 透過 /adjust 介入；clearing in-flight claims"
    rolled := python3 "$GID_PY" rollback-claims --base "$GID_BASE"

    # Manual fallback (script unavailable): do the four sub-steps by hand — task_queue rollback
    # (claimed→pending, validating→executed, clear Claimed_by/Claimed_at, keep Validation
    # Results/Artifact/Attempts), clear milestone mval claims, clear open-RQ analyst claims, then
    # rewrite the state.md YAML block to schema_version=2 / phase=AWAITING_HUMAN / status=WAITING /
    # batch_id=null / batch_started_at=null / batch_ended_at=<now> / active_agents=[] /
    # goal_set=<unchanged> / last_updated=<now>.

    Tell the user: 「前一輪 batch <paused_batch> 的 in-flight 標記已清理（claimed→pending、validating→executed）；那些 sub-agent 的結果若有崩潰中遺失將由 planner / 下一輪 executor 重新處理。」
    Continue on into Step 2 (Step 3 will later flip phase from AWAITING_HUMAN to PLANNING).

OTHERWISE (status == WAITING, phase ∈ {PLANNING, ANALYZING, EXECUTING, REPORTING, AWAITING_HUMAN}):
    Proceed directly to Step 2.
```

## Step 2: Decide the mode (soft / hard)

Read `.get-it-done/goal.md`, show the user the existing `## Goal` / `## Context & Constraints` / `## Success Definition`.

Decide based on the semantics of the user's message:

- **Clear pivot / rewrite** (keywords: 「改成」「換方向」「pivot」「重新做」「目標改為」「另一個目標」) → go hard.
- **Clearly just adding spec / constraints** (keywords: 「另外」「加上」「補充」「限制」「要求」「順便」「另外要求」「請確保」) → go soft.
- **Ambiguous** → ask via `AskUserQuestion`:

  > 「想要 soft 還是 hard 修訂？soft：在現有 goal.md 附加澄清/約束，保留 task_queue/prd/findings/workspace。hard：重寫 Goal/Success、清空 planner artifacts（同 /objective 的 reset，但保留 progress/validation log 與 context）。」
  >
  > 預設 soft（更安全）。

If Step 1 already forced hard (the COMPLETE path), skip straight to Step 3b.

## Step 3a: Soft path

1. **Revise `.get-it-done/goal.md`** (use Edit, preserve other content):
   - Append a bullet to the end of `## Context & Constraints`: `- (Refined <ISO>) <summary of the revision>`. If it was `(none)` or empty → replace with the new bullet.
   - If the user's message mentions a change to success criteria: append `- (Refined <ISO>) <new success criteria>` to the end of `## Success Definition`.
   - If the `## Refinement History` section doesn't exist, add at the end of the file:

     ```markdown

     ## Refinement History

     - <ISO>: <user's original message>
     ```

     If it already exists → append a `- <ISO>: <user's original message>` bullet.

2. **Preserve** the following files unchanged: `.get-it-done/task_queue.md`, `.get-it-done/prd.md`, `.get-it-done/research_requests.md`, `.get-it-done/findings/*`, `.get-it-done/workspace/*`, `.get-it-done/metrics.md`.

3. **Reset the `.get-it-done/state.md` YAML block** to fresh PLANNING state, preserving the `## Batch` history (no `--clear-history` — this is the same goal, history stays):
   ```bash
   python3 "$GID_PY" reset-state --phase PLANNING --base "$GID_BASE"
   ```
   (writes `schema_version: 2`, `phase: PLANNING`, `status: WAITING`, batch fields null, `active_agents: []`, `goal_set: true`, `last_updated: <now>`). Manual fallback: overwrite the YAML block by hand to those values, preserving everything below it.

4. **Append to `.get-it-done/progress_log.md`**:
   ```bash
   python3 "$GID_PY" log-append --file progress_log.md --base "$GID_BASE" --line "<ISO> [GOAL_REFINED] soft — <first 100 chars of the user's message>"
   ```

5. Skip to Step 4.

## Step 3b: Hard path

Confirm with the user: 「即將 hard 替換目標。task_queue.md、prd.md、findings、workspace 將被清空（progress_log、validation_log、context 保留）。確認嗎？」If no → EXIT.

1. **Overwrite `.get-it-done/goal.md`** (first read the old file to extract prior Refinement History entries, so they accumulate rather than being lost):
   ```markdown
   # Active Goal

   ## Status
   Active — team is working on this goal (refined via /adjust at <ISO>).

   ## Goal
   <new goal content from the user's message>

   ## Context & Constraints
   <if given by the user; otherwise "None specified.">

   ## Success Definition
   <if given by the user; otherwise derive from the goal>

   ## Set By
   Human (via /adjust — hard refinement)

   ## Set At
   <ISO now>

   ## Refinement History
   <if the old goal.md already had a ## Refinement History section, preserve all its existing bullets here as-is>
   - <ISO>: hard — <user's original message>
   ```

   Note: first Read the old goal.md to extract the prior `## Refinement History` section's bullets (if any), append them under the new section, then append this hard entry. This avoids wiping out prior refinement history on every hard overwrite.

2. **Reset planner artifacts** (same as `/objective` Step 4, unified via `bootstrap.py reset` — all paths are `--base`-relative to avoid relative-path mis-writes in multi-goal mode):
   ```bash
   BOOTSTRAP="${CLAUDE_PLUGIN_ROOT}/skills/objective/scripts/bootstrap.py"   # Copilot: {plugin-root}/skills/objective/scripts/bootstrap.py
   # Overwrites: force-copy task_queue.md / metrics.md / research_requests.md / findings/_meta.md,
   # deletes findings/RQ-*.md, clears workspace/, removes prd.md and plan_audit.md
   python3 "$BOOTSTRAP" reset --base "${GID_BASE:-.}"

   # hard reset is GOAL-SCOPED: clears THIS goal's task worktrees + gid/T-* branches (never other
   # goals), keeping the goal worktree itself + its branch. (soft does NOT reset.) Back-compat
   # (GID_BASE unset) falls back to the global worktree-reset-all.
   if [ -n "$GID_BASE" ]; then
     python3 "${CLAUDE_PLUGIN_ROOT}/skills/continue/scripts/gid.py" goal-reset --base "$GID_BASE" 2>/dev/null || true
   else
     python3 "${CLAUDE_PLUGIN_ROOT}/skills/continue/scripts/gid.py" worktree-reset-all 2>/dev/null || true
   fi
   ```

3. **Leave untouched**: `.get-it-done/progress_log.md`, `.get-it-done/validation_log.md`, `.get-it-done/context/*`, `${CLAUDE_PLUGIN_DATA}/team_learnings/*`, and the `## Batch` history block inside `.get-it-done/state.md`.

   Note: this is **deliberately different** from `/objective` here — `/objective` deletes the old `## Batch` blocks (since it's a brand-new goal with irrelevant history), but `/adjust` hard is a direction change within the SAME goal's context, so batch history is preserved for tracing prior attempts.

4. **Reset the `.get-it-done/state.md` YAML block** to fresh PLANNING state, preserving the `## Batch` history (no `--clear-history` — see step 3's note: same goal, history kept for tracing prior attempts):
   ```bash
   python3 "$GID_PY" reset-state --phase PLANNING --base "$GID_BASE"
   ```
   Manual fallback: overwrite the YAML block by hand to `schema_version: 2` / `phase: PLANNING` / `status: WAITING` / batch fields null / `active_agents: []` / `goal_set: true` / `last_updated: <now>`, preserving everything below it.

5. **Append to `.get-it-done/progress_log.md`**:
   ```bash
   python3 "$GID_PY" log-append --file progress_log.md --base "$GID_BASE" --line "<ISO> [GOAL_REFINED] hard — <first 100 chars of the new goal>"
   ```

## Step 4: Closing message (Traditional Chinese, user-facing)

Output a short summary:

```
目標已修訂（<soft|hard>）。

修訂內容：<user 訊息一句摘要>
goal.md 變更：<soft: 新增 N 條 constraint / hard: 全文重寫>
保留：progress_log、validation_log、.get-it-done/context、A-side learnings
<soft 時：保留 task_queue / prd / findings / workspace>
<hard 時：已清空 task_queue / prd / findings / workspace>

當前階段：PLANNING（status: WAITING）
下一步：執行 /continue 讓 planner 依新 goal 重新規劃。
```

## Design notes

- This skill is the sole writer; it follows the same contract as `/objective` — only the dispatcher and this skill may touch shared state such as `.get-it-done/state.md`, `.get-it-done/progress_log.md`, `.get-it-done/task_queue.md`.
- Soft mode deliberately does NOT decide, on Planner's behalf, "which tasks need to be redone" — that's Planner's job (planner.md's PR rules cover replanning logic). This skill only flips phase back to PLANNING and writes the new constraint into goal.md; Planner will naturally read it on the next `/continue`.
- The RUNNING path pauses via AWAITING_HUMAN (rather than ABORT) — sub-agent results that were spawned but never persisted are recovered by the next `/continue`'s Step 2 crash recovery, so nothing is wasted needlessly.
