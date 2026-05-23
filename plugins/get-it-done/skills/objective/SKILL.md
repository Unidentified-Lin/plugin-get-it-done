---
name: objective
description: Sets a new business goal for the autonomous agent team and launches the first dispatcher cycle. Usage: /objective <goal description>. Bootstraps the project's team/ workspace from plugin templates if missing, resets per-goal files, initializes v2 state schema (batch-aware), and starts the planning → execution → validation loop.
---

You are executing **/objective**. This is how the user sets a business goal for the autonomous agent team. Both the v2 state schema (batch-aware) and the new agent-return YAML contract live in `team/state.md` — read it after bootstrap if you need to refresh on the shapes.

## Where state lives

| Path | Resolves to | Scope | Purpose |
|---|---|---|---|
| `team/...` | `<project>/team/...` | **per-project**, in git | Runtime state + per-project learnings (B) |
| `${CLAUDE_PLUGIN_DATA}/team_learnings/...` | `~/.claude/plugins/data/get-it-done-<scope>/team_learnings/...` | **per-user, cross-project** | Cross-project agent-team learnings (A) |

The plugin install dir (`${CLAUDE_PLUGIN_ROOT}`) is read-only — templates only.

## Parse the goal

Extract the goal from the user's message — everything after `/objective`. If empty, ask for one and stop.

## Step 0: Bootstrap

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — refusing to read templates from / }"
: "${CLAUDE_PLUGIN_DATA:?CLAUDE_PLUGIN_DATA is not set — refusing to write learnings to / }"

# A — cross-project agent-team learnings
mkdir -p "${CLAUDE_PLUGIN_DATA}/team_learnings/agent_rules"
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team_learnings/" "${CLAUDE_PLUGIN_DATA}/team_learnings/"

# B — per-project state + sub-agent scratch surfaces
mkdir -p team/context team/findings team/workspace
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team/" team/
```

`team/workspace/` (per-executor scratch) and `team/findings/` (per-analyst findings) are sub-agent write surfaces — bootstrap only creates the directory; sub-agents fill files.

## Step 1: Check for an active goal

Read `team/state.md`. If `goal_set: true` and `phase` is not `IDLE` or `COMPLETE`, ask:

> "已有一個進行中的目標。要取代它（從頭開始）還是保留它（取消此命令）？"

選擇「保留」則停止。選擇「取代」則繼續。

If the file is pre-v2 (no `schema_version` or `schema_version < 2`), treat the project as replacing — overwriting the YAML block to v2 is the intended migration path.

## Step 2: Reset team state (v2 schema)

Overwrite the YAML block at the top of `team/state.md` (preserve everything below it — the State Machine docs, Phase Definitions, Transition Rules, batch lifecycle, agent-return contract):

```yaml
schema_version: 2
phase: PLANNING
status: WAITING
batch_id: null
batch_started_at: null
batch_ended_at: null
active_agents: []
goal_set: true
last_updated: <ISO timestamp>
```

Also remove any leftover `## Batch <id>` blocks (or legacy `## Handoff` blocks) from prior goals at the bottom of state.md — they're stale and would confuse a future reader.

## Step 3: Write the goal

Overwrite `team/goal.md`:

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

Overwrite per-goal scaffold files with explicit `cp -f` commands (ensures no stale v1-style files interfere):

```bash
# (1) Overwrite per-goal scaffolds from templates
cp -f "${CLAUDE_PLUGIN_ROOT}/templates/team/task_queue.md" team/task_queue.md
cp -f "${CLAUDE_PLUGIN_ROOT}/templates/team/metrics.md" team/metrics.md
cp -f "${CLAUDE_PLUGIN_ROOT}/templates/team/research_requests.md" team/research_requests.md
cp -f "${CLAUDE_PLUGIN_ROOT}/templates/team/findings/_meta.md" team/findings/_meta.md

# (2) Clear leftover per-request findings files from prior goal
find team/findings -type f -name 'RQ-*.md' -delete

# (3) Clear executor scratch workspace (remove stale prior-goal artifacts)
rm -rf team/workspace
mkdir -p team/workspace

# (4) Remove stale team/prd.md (planner writes fresh when needed)
rm -f team/prd.md
```

**Do NOT overwrite** (these accumulate across goals and are preserved):
- `team/progress_log.md` (append-only history)
- `team/validation_log.md` (append-only history)
- `team/context/*` (per-project domain/tech/codebase/decisions/stakeholder — B side)
- everything under `${CLAUDE_PLUGIN_DATA}/team_learnings/` (A side, untouched by /objective)

Append to `team/progress_log.md`:

```
<ISO timestamp> [NEW_GOAL] <first 100 chars of goal>
```

## Step 5: Launch the dispatcher

Invoke the `continue` skill to start the first cycle. Use the Skill tool with `skill: "continue"` (or `skill: "get-it-done:continue"` if a name collision requires it).

## Step 6: Confirm to user

After the first cycle completes, output (in 繁體中文 per project convention):

```
目標已設定，agent 團隊已啟動。

目標：<one-line summary>
當前階段：<phase from state.md>
最後一個 batch：<batch_id from last ## Batch block, or "(尚無)">
下一步行動：<intent line from latest ## Batch block, or "spawn planner">

dispatcher 已啟動並會自我循環推進，直到目標完成、卡在人為決策、或 context 用盡。要暫停請編輯 team/state.md 並設定 phase: AWAITING_HUMAN。
```
