---
name: execute
description: >-
  Implements code changes task-by-task using sub-agents. If a frozen plan
  document exists, proceeds directly to implementation. If not, asks the user
  whether to plan first (redirects to `plan` skill) or implement immediately
  based on agent's current understanding. If called with no context, asks the
  user what to implement before proceeding.

  Triggers on: "開始執行", "開始實作", "幫我實作", "execute", "implement",
  "run plan", "直接做", direct feature/bug descriptions implying
  implementation intent.

  Do NOT trigger for planning-only requests — use `plan` instead.
  Do NOT trigger for code review requests — use `conventional-review` instead.
---

# Execute Skill

This skill drives the implementation pipeline (step D). It reads tasks from a
frozen planning document and executes them one by one via sub-agents.

## Startup

You (the main agent) are the **orchestrator** for this skill. You do not implement
tasks yourself — you spawn sub-agents for isolated execution.

Before doing anything else:
1. Run `/skills info execute` to get this skill's absolute directory path. Store it as `{skill-dir}`.
2. Read `{skill-dir}/../../references/main-flow.md` — full pipeline map and step positioning table.

When spawning sub-agents, always pass these **absolute paths** in the task prompt:
- Planning document: the frozen plan's full path
- For task-executor: `{skill-dir}/references/execution-guide.md`
- For task-reviewer: `{skill-dir}/references/review-guide.md`

## Entry Behavior

| Situation | Action |
|-----------|--------|
| Frozen planning document found | Proceed directly to D — no planning needed |
| Requirement given but no plan | Ask user: "是否需要先完整規劃？" — Yes → suggest `plan` skill; No → agent summarises understanding, user confirms, then creates ad-hoc task descriptions and implements |
| Called with no context | Ask user: "你想修改什麼？" — wait for description, then continue as "requirement given but no plan" |

## What this skill does

1. Determines whether a frozen planning document exists (status = "已凍結，進入執行").
2. If yes: iterates through each pending task following the **D1 → D2 → D3** sequence:
   - **D1**: Spawns **task-executor** sub-agent via `task` tool (using `task-executor.agent.md` +
     `references/execution-guide.md` as prompt context) to implement the task's code changes
   - **D2**: Spawns **task-reviewer** sub-agent via `task` tool (using `task-reviewer.agent.md` +
     `references/review-guide.md` as prompt context) to review the completed task
   - **D3** (conditional): If D2 passes **and** the task's test flag is enabled, spawns
     **task-executor** again for test validation
3. Manages retry loops: minor issues are fixed in place by re-spawning task-executor;
   major issues return to C2 for replanning (involve the user).
4. After all tasks pass, prompt the user to run `/feature-flow:conventional-review`.

## Sub-agents spawned

All sub-agents are spawned via the `task` tool and run in **isolated contexts** — they do
not interact with the user directly; their output is returned to you (the orchestrator).

| Sub-agent | Agent file | Reference to include | When |
|-----------|-----------|---------------------|------|
| task-executor | `task-executor.agent.md` | `references/execution-guide.md` | D1 (implement) and D3 (test validation, conditional) |
| task-reviewer | `task-reviewer.agent.md` | `references/review-guide.md` | D2 (review, after D1 completes) |

## Reference files for sub-agents

Sub-agents receive absolute paths via the task prompt (see Startup above).
For reference, the files are located at:

| File | Include for |
|------|-------------|
| `references/execution-guide.md` | task-executor — execution rules + D3 test strategy |
| `references/review-guide.md` | task-reviewer — review criteria + issue grading |
