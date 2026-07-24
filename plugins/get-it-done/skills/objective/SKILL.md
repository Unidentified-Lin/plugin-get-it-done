---
name: objective
description: >-
  Sets a new business goal for the autonomous agent team and launches the first dispatcher cycle. Usage: /objective <goal description>. Bootstraps the project's .get-it-done/ workspace from plugin templates if missing, resets per-goal files, initializes v2 state schema (batch-aware), and starts the planning → execution → validation loop.
---

You are executing **/objective**. This is how the user sets a business goal for the autonomous agent team. The v2 state schema (batch-aware) is the YAML block in `.get-it-done/state.md`; the agent-return YAML contract and the rest of the spec (phases, transitions, crash recovery, git isolation) live in `.get-it-done/STATE_SPEC.md` — read them after bootstrap if you need to refresh on the shapes.

## Where state lives

| Path | Resolves to | Scope | Purpose |
|---|---|---|---|
| `.get-it-done/...` | `<project>/.get-it-done/...` | **per-project**, in git | Runtime state + per-project learnings (B) |
| `${CLAUDE_PLUGIN_DATA}/team_learnings/...` | `~/.claude/plugins/data/get-it-done-<scope>/team_learnings/...` | **per-user, cross-project** | Cross-project agent-team learnings (A) |

The plugin install dir (`${CLAUDE_PLUGIN_ROOT}`) is read-only — templates only.

## Parse the goal

Extract the goal from the user's message — everything after `/objective`. If empty, ask for one and stop.

## Step 0a: Create the goal worktree (multi-goal — establishes GID_BASE)

Each goal runs in its **own git worktree** under `<repo>.gid-goals/<slug>/` so multiple goals can run concurrently from one repo-root window without colliding, and your own checkout stays clean. Read `../../references/gid-base.md` §"Create" and follow it to establish `GID_BASE`. Tell the user, at the end, that this goal lives in worktree `$GID_BASE` and runs independently of other goals/windows.

## Step 0: Bootstrap

**When to use `/blueprint` first**: If the requirement is complex or ambiguous (needs interactive scope analysis, design decisions, impact assessment), consider running `/blueprint` first. `/blueprint` produces a frozen planning document and initializes `.get-it-done/` state automatically — you can then run `/continue` directly instead of `/objective`.

Read `../../references/platform-adapter.md` §7 "`bootstrap.py init` invocation" and run the block matching your platform, with `--base "${GID_BASE:-.}"` (or `$env:GID_BASE` on Windows). (`goal-worktree-init` already created `$GID_BASE/.get-it-done/git_state.json`; `init` preserves it via skip-existing logic.)

`.get-it-done/workspace/` (per-executor scratch) and `.get-it-done/findings/` (per-analyst findings) are sub-agent write surfaces — bootstrap only creates the directory; sub-agents fill files.

## Step 1: Check for an active goal (in THIS goal's worktree)

**Multi-goal note:** distinct goals coexist in separate worktrees — a new goal with a new slug never conflicts with other active goals. This check only matters when the slug you derived already exists (re-running `/objective` for the same goal).

Read `"$GID_BASE/.get-it-done/state.md"`. If `goal_set: true` and `phase` is not `IDLE` or `COMPLETE`, ask:

> "此 worktree 已有一個進行中的目標。要取代它（從頭開始）還是保留它（取消此命令）？（其他目標不受影響）"

選擇「保留」則停止。選擇「取代」則繼續。

If the file is pre-v2 (no `schema_version` or `schema_version < 2`), treat as replacing — overwriting the YAML block to v2 is the intended migration path. (A brand-new goal worktree has fresh template state, so this is a no-op for it.)

## Step 2: Reset team state (v2 schema)

**Script path.** `reset-state` overwrites the state.md YAML block to a fresh planning state and, with `--clear-history`, strips any leftover `## Batch <id>` / legacy `## Handoff` blocks from a prior goal (a brand-new goal has no relevant history) while preserving the "Batch history" prose section. The spec prose lives in `.get-it-done/STATE_SPEC.md`, refreshed separately by `bootstrap.py reset` — do not touch it here.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/continue/scripts/gid.py" reset-state --phase PLANNING --clear-history --base "${GID_BASE:-.}"
```

This writes `phase: PLANNING`, `status: WAITING`, all batch fields null, `active_agents: []`, `goal_set: true`, `last_updated: <now>`.

**Manual fallback** (script unavailable): overwrite the YAML block by hand to those values (preserving everything below it), and delete any `## Batch <id>` / `## Handoff` blocks from the bottom.

## Step 3: Write the goal

Overwrite `.get-it-done/goal.md`:

```markdown
# Active Goal

## Status
Active — team is working on this goal.

## Goal
<full goal text from user>

## Context & Constraints
<any constraints the user mentioned, or "None specified.">

## Success Definition
<what "done" looks like — infer from the goal if not explicit>

## Set By
Human (via /objective)

## Set At
<ISO timestamp>
```

## Step 4: Reset per-goal working files

Force-copy per-goal scaffold files and clear stale artifacts via `bootstrap.py reset`, then clean up task worktrees via `gid.py`:

```bash
BOOTSTRAP="${CLAUDE_PLUGIN_ROOT}/skills/objective/scripts/bootstrap.py"   # Copilot: {plugin-root}/skills/objective/scripts/bootstrap.py
python3 "$BOOTSTRAP" reset --base "${GID_BASE:-.}"

# GOAL-SCOPED reset of task worktrees + gid/T-* branches (multi-goal: NEVER wipes other goals).
# For a brand-new goal this is a no-op; for replace-goal it clears stale task worktrees.
# Back-compat (GID_BASE unset) falls back to worktree-reset-all.
if [ -n "$GID_BASE" ]; then
  python3 "${CLAUDE_PLUGIN_ROOT}/skills/continue/scripts/gid.py" goal-reset --base "$GID_BASE" 2>/dev/null || true
else
  python3 "${CLAUDE_PLUGIN_ROOT}/skills/continue/scripts/gid.py" worktree-reset-all 2>/dev/null || true
fi
```

**Do NOT overwrite** (preserved when `/objective` resets / replaces a goal *in this worktree*):
- `.get-it-done/progress_log.md` (append-only history)
- `.get-it-done/validation_log.md` (append-only history)
- `.get-it-done/context/*` (per-project domain/tech/codebase/decisions/stakeholder — B side)
- everything under `${CLAUDE_PLUGIN_DATA}/team_learnings/` (A side, untouched by /objective)

> **Multi-goal scope note:** in multi-goal worktree mode each goal has its **own** `.get-it-done/`, so `progress_log.md` / `validation_log.md` are **per-goal-worktree** — they are append-only *within a goal's lifetime* (across `/adjust` and across a `/objective` reset/replace of the same slug), **not** a single ledger merged across distinct goals. The only truly cross-goal, cross-project store is A-side `${CLAUDE_PLUGIN_DATA}/team_learnings/`. (B-side `context/` is slated to move to a stable per-project location so it too accumulates across goals — see project notes.)

Append to `.get-it-done/progress_log.md`:

```
<ISO timestamp> [NEW_GOAL] <first 100 chars of goal>
```

## Step 5: Launch the dispatcher

`GID_BASE` is already exported for this window (Step 0a), so `/continue` inherits the active goal — it will resolve to the same worktree. Invoke the `continue` skill to start the first cycle (see `platform-adapter.md` Section 9 for cross-platform skill invocation):
- **Claude Code**: Skill tool with `skill: "continue"` (or `skill: "get-it-done:continue"` if a name collision requires it).
- **GitHub Copilot** (no Skill tool): read `{plugin-root}/skills/continue/SKILL.md` and execute its instructions inline, in this same session.

## Step 6: Confirm to user

After the first cycle completes, output (in 繁體中文 per project convention):

```
目標已設定，agent 團隊已啟動。

目標：<one-line summary>
工作 worktree：<$GID_BASE>（分支 gid/goal-<slug>；獨立於其他目標/視窗，你的 checkout 保持乾淨）
當前階段：<phase from state.md>
最後一個 batch：<batch_id from last ## Batch block, or "(尚無)">
下一步行動：<intent line from latest ## Batch block, or "spawn planner">

dispatcher 已啟動並會自我循環推進，直到目標完成（COMPLETE）、卡在人為決策（AWAITING_HUMAN）、或抵達 planner 規劃時標記的 PauseAfter 檢查點（PLANNED_PAUSE，soft EXIT，下次 /continue 自動接續）。要中途修訂或具體化需求請使用 /adjust <修訂訊息>（會保留 progress_log、validation_log 與 context）。
```
