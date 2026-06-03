# Task Breakdown Guide — C1, C2, C3 Rules

> **For**: planner agent
> **Load at**: Entering C phase (after B4 confirmed)
> **Covers**: C1 framework confirmation, C2 task fill, C3 freeze + get-it-done handoff

---

## Step C1 — Framework Confirmation

Present the current task list skeleton to the user and ask:

> "以下是目前的任務框架，方向正確嗎？有遺漏或需要調整的項目嗎？"

Use `AskUserQuestion` (Claude Code) or `ask_user` (Copilot) with choices:
- "框架正確，繼續細化" → proceed to C1-post (scaffold task files)
- "需要調整" → collect feedback, adjust tasks, re-present

**Exit condition**: User confirms the framework is directionally correct.

---

## Step C1-post — Scaffold Task Files

Immediately after C1 confirmation, create all task files as stubs **before** any C2 investigation.

**Task file path convention**:

```
{project-root}/docs/plans/{xxx}-plan/tasks/{n:02d}-{task-slug}-task.md
```

- `{xxx}` matches the plan folder name (e.g., `issue502-add-login`)
- `{n:02d}` is zero-padded task number (01, 02, …)
- `{task-slug}` is a lowercase-hyphenated short title

**For each task**:
1. Read `task-template.md` (path provided in your task prompt).
2. Create the task file using the template — fill in task number and title only; leave other fields as `{TBD}`.
3. Update the main plan document's 任務清單 summary table to reference the new file.

After all task files are created, proceed to C2.

---

## Step C2 — Task Fill (Surgical Codebase Investigation)

For each task, open its task file and perform a **surgical** codebase investigation:
- Use `grep` / `glob` to locate exact file paths, class names, function signatures.
- Do NOT explore broadly — only look up what is needed for this specific task.

Fill each task file's sections:

```markdown
## 任務說明
一句話描述此任務做什麼（具體，含函式/模組名）

## 檔案路徑
- `path/to/file.ts` — 說明此檔案的角色

## 實作步驟
1. 具體步驟（動詞開頭，含函式名稱）
2. …

## 驗證方式
如何確認這個任務做對了
```

Also set the 測試旗標 in the task file and sync it to the main plan document's 任務清單.

### Test Flag Rules

Set **☑ 需要測試** when:
- The task modifies business logic, calculations, or conditional branching
- The task adds or changes API contract (request/response shape)
- The task touches security, permission, or data validation logic

Set **☐ 不需要測試** when:
- The task is pure config change (no logic)
- The task is UI-only (no backend logic change)
- The task adds a new endpoint already covered by integration tests

### Quality bar for C2 fill

A task is considered fully filled when:
- [ ] File path(s) point to actual existing files (verified via `glob`/`grep`)
- [ ] Implementation steps use concrete function/class names, not vague descriptions
- [ ] Verification method is specific and checkable (not "make sure it works")
- [ ] Test flag is explicitly set

---

## Step C3 — Final Confirmation, Freeze, and Handoff

Present the complete task list to the user:

> "以下是完整的任務清單，請確認後我將凍結規劃文件並進入執行。"

Use `AskUserQuestion` / `ask_user` with choices:
- "確認，凍結並進入執行" → freeze documents; run plan-reviewer; then initialize .get-it-done/ state
- "需要調整" → return to C2 for the specific tasks mentioned

**After C3 confirmation**:
1. Update main plan document status line to: `**目前狀態**: 已凍結，進入執行`
2. Update each task file's **狀態** field to `待執行（Pending）`.
3. Automatically trigger **plan-reviewer** agent (passing planning document path and `plan-reviewer-guide.md` path).

**After plan-reviewer PASS → Initialize get-it-done execution state:**

Run bootstrap (see `platform-adapter.md` Section 7 for OS-specific commands):
```bash
# macOS / Linux
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set}"
: "${CLAUDE_PLUGIN_DATA:?CLAUDE_PLUGIN_DATA is not set}"
mkdir -p .get-it-done/context .get-it-done/findings .get-it-done/workspace
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team_learnings/" "${CLAUDE_PLUGIN_DATA}/team_learnings/"
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/.get-it-done/" .get-it-done/
```

Then write `.get-it-done/goal.md`:
```markdown
# Active Goal

## Status
Active — executing from /plan output.

## Goal
<feature name from planning document>

## Context & Constraints
<requirements and constraints from planning document 需求重點 + 限制條件>

## Success Definition
<from planning document 驗收標準 or derived from 需求重點>

## Set By
Human (via /plan)

## Set At
<ISO timestamp>
```

Write `.get-it-done/state.md` YAML block (overwrite only the YAML block at the top, preserve everything below it):
```yaml
schema_version: 2
phase: EXECUTING
status: WAITING
batch_id: null
batch_started_at: null
batch_ended_at: null
active_agents: []
goal_set: true
last_updated: <ISO timestamp>
```

Write `.get-it-done/task_queue.md` with all tasks in v2 DAG format. Use the schema from the existing template. Each task entry:

```markdown
### T-{n:03d}: {Task Title}

**Type**: code
**Milestone**: M1
**Status**: pending
**Attempts**: 0
**Claimed_by**: null
**Claimed_at**: null
**Artifact**: null
**Dependencies**: []
**Touches**: ["{file-path-1}", "{file-path-2}"]
**Validation Results**: []

#### Description
{task description from task file}

#### Acceptance Criteria
- [ ] {From task file 驗證方式}
```

Map tasks to milestones logically (group related tasks into 2–5 milestones). Set `Dependencies` based on the ordering you established in the task list. The `Touches` list should match the `檔案路徑` from each task file.

After all task entries, **append a `## Milestones` section** (required by the dispatcher for milestone gating):

```markdown
## Milestones

### M1: {Milestone Name}

**Tasks**: [T-001, T-002, T-003]
**Claimed_by**: null
**Claimed_at**: null
**ValidatorAttempts**: 0
**Validation Results**: []
**PauseAfter**: false
**PauseReason**: null
**Acceptance Criteria**:
- {Integration-level criterion that emerges from the milestone's tasks working together}
- {If no integration property is worth checking, write: "(none — per-task validation is sufficient)"}
```

Repeat for each milestone. Every task must belong to exactly one milestone.

Also write `.get-it-done/metrics.md` — validators read this for acceptance criteria by stable ID:

```markdown
## T-001: {Task Title}
**Type**: code
**Acceptance Criteria**:
- [ ] C1: {specific, binary criterion from task file 驗證方式}
- [ ] C2: {another criterion}
**Quality Bar**: {what separates a complete implementation from a partial one}

## T-002: {Task Title}
...
```

Append progress log entry:
```
<ISO timestamp> [/PLAN_COMPLETE] <feature name> — {n} tasks across {m} milestones, plan at docs/plans/{xxx}-plan/{xxx}-plan.md
```

Then tell the user:
```
規劃完成，執行狀態已初始化。

功能：<feature name>
任務數：<n>（<m> 個 milestone）
規劃文件：docs/plans/{xxx}-plan/{xxx}-plan.md

執行 `/continue` 開始自主執行。
```

---

## Freeze Conditions

The document may only be frozen (C3 pass) when ALL of the following are true:

- [ ] 需求重點 is precise (contains success criteria and boundaries)
- [ ] 異動範圍 lists concrete modules/services/APIs — not just "TBD"
- [ ] 實作方向重點 describes the chosen approach with enough detail to implement
- [ ] All task files exist at `tasks/{n}-{task-slug}-task.md`
- [ ] Every task file has: file paths (verified), steps (concrete), verification, test flag — no TBD
- [ ] Main plan document 任務清單 summary table is up to date with all task file links
