---
name: blueprint
description: >-
  Analyzes requirements and produces a progressive planning document covering
  scope definition, requirements clarification, solution proposals, and task
  breakdown (A+B+C pipeline). At the end of planning (C3), also initializes
  .get-it-done/task_queue.md in get-it-done format so /continue can execute the plan
  autonomously. Use when starting a new feature, analyzing a requirement, or
  producing a plan before implementation.

  Triggers on: "開始新功能", "分析需求", "規劃", "我要開發", "plan feature",
  "analyze requirement", "start planning", ticket/issue ID with planning intent.

  Do NOT trigger for direct implementation requests — use /objective or /continue instead.
  Do NOT trigger for code review requests — use /review instead.
---

# Blueprint Skill

This skill drives the full interactive planning pipeline (steps A through C) and produces a
frozen planning document that can be handed off to `/continue` for autonomous execution.

## Platform Setup

Before doing anything else:
1. Locate this skill's absolute directory path:
   - **Claude Code**: Run `/skills info blueprint` or derive from `${CLAUDE_PLUGIN_ROOT}/skills/blueprint/`
   - **GitHub Copilot**: Run `/skills info blueprint`
   Store the result as `{skill-dir}`.
2. Read `{skill-dir}/../../references/platform-adapter.md` — cross-platform operations reference.
3. Read `{skill-dir}/../../references/main-flow.md` — full pipeline map.

## What this skill does

Spawn the **planner** sub-agent, passing the following absolute paths in the prompt:
- `{skill-dir}/references/planning-guide.md`
- `{skill-dir}/references/plan-template.md`
- `{skill-dir}/references/task-breakdown-guide.md`
- `{skill-dir}/references/task-template.md`
- `{skill-dir}/references/plan-reviewer-guide.md`
- `{skill-dir}/references/scope-scanner-guide.md`
- `{skill-dir}/references/scope-verifier-guide.md`
- `{skill-dir}/../../references/platform-adapter.md`
- The user's original input (ticket ID or natural language description)

**Spawn protocol:**
- **Claude Code**: Use `Agent` tool with `subagent_type: "get-it-done:interactive-planner"`, `maxTurns: 60`
- **GitHub Copilot**: Use `task` tool with `agent_type: "get-it-done:interactive-planner"`

## Pipeline (A → B → C)

The planner sub-agent follows `planning-guide.md` to iteratively build a planning document:

- **A1**: Input parsing (ticket ID or natural language)
- **B1**: Create planning document skeleton + requirements confirmation loop with user
- **B2**: Spawn **scope-scanner** for method-level change scope → **scope-verifier** validates (max 3 loops) → planner presents scope to user
- **B3**: Produce discussion list from B1+B2 → discuss topics one by one with user → consolidate decisions
- **B4**: Spawn **scope-scanner** for impact scope → **scope-verifier** validates → user confirms
- **C1–C3**: Task breakdown and freeze

## After C3 — Handoff to /continue

After the user confirms the task list and plan-reviewer passes, the planner must:

1. Mark the planning document status as `已凍結，進入執行`
2. **Initialize get-it-done execution state** (see `task-breakdown-guide.md` C3 section):
   - Bootstrap `.get-it-done/` if not already present
   - Write `.get-it-done/goal.md` with the feature description
   - Write `.get-it-done/task_queue.md` with tasks in v2 DAG format
   - Write `.get-it-done/state.md` YAML block with `phase: EXECUTING`
3. Tell the user: "規劃完成，執行 `/continue` 開始自主執行"

## Key Rules

- **Document path**: `{project-root}/docs/plans/{xxx}-plan/{xxx}-plan.md` — derive `{xxx}` from feature name or ticket ID
- **Task file path**: `{project-root}/docs/plans/{xxx}-plan/tasks/{n:02d}-{task-slug}-task.md`
- **Ticket systems**: read work item body + acceptance criteria only. Never write back.
- **File path verification**: verify every path exists via `glob`/`grep` before writing into task definitions.
- **Every task must have**: concrete file paths, actionable steps (function-level), verification method, and test flag.
- **Freeze**: mark document status `已凍結，進入執行`; initialize .get-it-done/ state; tell the user to run `/continue`.
- **Scanner/verifier loop limit**: Maximum 3 scanner↔verifier loops per invocation. If exceeded → escalate to user.

## Sub-agents spawned

| Sub-agent | When | Role |
|-----------|------|------|
| `get-it-done:planner` | Skill startup | Drives full interactive A+B+C pipeline |
| `get-it-done:scope-scanner` | B2 and B4 | Codebase scope and impact inventory |
| `get-it-done:scope-verifier` | After each scanner pass | Validates scanner output (max 3 loops) |
| `get-it-done:plan-reviewer` | After C3 user confirmation | Audits completeness before handoff |

## Output

A planning document at `{project-root}/docs/plans/{xxx}-plan/{xxx}-plan.md` with individual task files in `tasks/`, plus an initialized `.get-it-done/` directory ready for `/continue`.
