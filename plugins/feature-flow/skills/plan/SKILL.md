---
name: plan
description: >-
  Analyzes requirements and produces a progressive planning document covering
  scope definition, requirements clarification, solution proposals, and task
  breakdown. Use when starting a new feature, analyzing a requirement, or
  producing a plan before implementation. Output is a frozen planning document
  ready for execution.

  Triggers on: "開始新功能", "分析需求", "規劃", "我要開發", "plan feature",
  "analyze requirement", "start planning", VSTS Work Item ID with planning
  intent.

  Do NOT trigger for direct implementation requests — use `execute` instead.
  Do NOT trigger for code review requests — use `conventional-review` instead.
---

# Plan Skill

This skill drives the full planning pipeline (steps A through C) and produces a
frozen planning document that can be handed off to `execute`.

## Startup

Before doing anything else:
1. Run `/skills info plan` to get this skill's absolute directory path. Store it as `{skill-dir}`.
2. Read `{skill-dir}/../../references/main-flow.md` — full pipeline map and step positioning table.
3. Spawn the **planner** sub-agent via the `task` tool, passing these absolute paths in the prompt:
   - `{skill-dir}/references/planning-guide.md`
   - `{skill-dir}/references/plan-template.md`
   - `{skill-dir}/references/task-breakdown-guide.md`
   - `{skill-dir}/references/task-template.md`
   - `{skill-dir}/references/plan-reviewer-guide.md`
   - `{skill-dir}/references/scope-scanner-guide.md`
   - `{skill-dir}/references/scope-verifier-guide.md`
   - The user's original input (VSTS Work Item ID or natural language description)

## What this skill does

1. Accepts a requirement as input — either a VSTS Work Item ID or a natural
   language description in the conversation.
2. The **planner** sub-agent follows `references/planning-guide.md` to iteratively build and
   refine a planning document:
   - **A1**: Input parsing (VSTS Work Item or conversation)
   - **B1**: Create planning document skeleton + requirements confirmation loop with user
   - **B2**: Spawn **scope-scanner** for method-level change scope inventory → **scope-verifier** validates (max 3 loops) → planner presents scope summary to user for confirmation
   - **B3**: Produce discussion list from B1+B2 → discuss topics one by one with user → consolidate decisions into implementation direction → user confirms
   - **B4**: Spawn **scope-scanner** for impact scope inventory → **scope-verifier** validates → user confirms (may return to B3 or B2)
   - **C1~C3**: Task breakdown and freeze
3. After the user confirms the task list (C3), the planner spawns a **plan-reviewer** sub-agent
   (via `task` tool using `plan-reviewer.agent.md` as the prompt) to validate the frozen document.
4. On review pass, inform the user that the plan is ready and suggest running
   `/feature-flow:execute`.

## Key Rules

- **Document path**: `{project-root}/docs/feature-flow/{xxx}-plan/{xxx}-plan.md` — derive `{xxx}` from feature name or VSTS ID (e.g., `vsts502199-add-login`)
- **Task file path**: `{project-root}/docs/feature-flow/{xxx}-plan/tasks/{n:02d}-{task-slug}-task.md`
- **VSTS Work Items**: read body + Acceptance Criteria only. Never write back.
- **File path verification**: verify every path exists via `glob`/`grep` before writing into task definitions.
- **Every task must have**: concrete file paths, actionable steps (method-level), verification method, and test flag.
- **Freeze**: mark document status `已凍結，進入執行`; tell the user the plan is ready and suggest `/feature-flow:execute`.
- **Scanner/verifier loop limit**: Maximum 3 scanner↔verifier loops per invocation. Exceeded → planner escalates to user.

## Sub-agents spawned

- **planner** — spawned at skill startup via `task` tool; drives the full interactive A+B+C planning pipeline with the user. Receives all reference file paths in its task prompt.
- **scope-scanner** — spawned by the planner during B2/B4 via `task` tool; analyzes codebase for method-level scope inventories. Operates in two modes: change-scope (B2) and impact-scope (B4). Auto-spawns scope-verifier for validation.
- **scope-verifier** — spawned by scope-scanner after each inventory via `task` tool; independently validates scope accuracy and completeness. Returns structured verification report.
- **plan-reviewer** — spawned by the planner after C3 via `task` tool; audits completeness in an isolated context.

## Output

A planning document saved at `{project-root}/docs/feature-flow/{xxx}-plan/{xxx}-plan.md`
with status marked as **已凍結，進入執行**, plus individual task files at
`{project-root}/docs/feature-flow/{xxx}-plan/tasks/{n}-{task-slug}-task.md`.
