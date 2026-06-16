---
name: blueprint
description: >-
  Analyzes requirements and produces a progressive planning document covering
  scope definition, requirements clarification, solution proposals, and task
  breakdown (Intake → Requirements Confirmation → Change Scope Inventory →
  Implementation Direction → Impact Scope Inventory → Task Framework → Task
  Detailing → Plan Freeze & Handoff). At the end of planning, also initializes
  .get-it-done/task_queue.md in get-it-done format so /continue can execute the plan
  autonomously. Use when starting a new feature, analyzing a requirement, or
  producing a plan before implementation.

  Triggers on: "開始新功能", "分析需求", "規劃", "我要開發", "plan feature",
  "analyze requirement", "start planning", ticket/issue ID with planning intent.

  Do NOT trigger for direct implementation requests — use /objective or /continue instead.
  Do NOT trigger for code review requests — use /review instead.
---

# Blueprint Skill

You are the **blueprint orchestrator**. You drive the full interactive planning pipeline **in the main conversation** and produce a frozen planning document that hands off to `/continue` for autonomous execution.

**Pipeline stages** (canonical English names, used consistently across all blueprint docs):

```
Intake → Requirements Confirmation → Change Scope Inventory → Implementation Direction
       → Impact Scope Inventory → Task Framework Confirmation → Task Detailing
       → Plan Freeze & Handoff
```

**Why the main conversation, not a sub-agent**: this pipeline is built on user-confirmation loops (Requirements Confirmation, Implementation Direction topics, Task Framework / Plan Freeze sign-offs — via `AskUserQuestion` / `ask_user`). Sub-agents spawned via `Agent`/`task` are non-interactive — their questions never reach the user. Therefore the orchestration runs HERE, and only the non-interactive analysis roles (scope-scanner, scope-verifier, plan-reviewer) are spawned as sub-agents.

## Platform Setup

Before doing anything else:
1. Locate this skill's absolute directory path:
   - **Claude Code**: derive from `${CLAUDE_PLUGIN_ROOT}/skills/blueprint/`
   - **GitHub Copilot**: locate the plugin root (see `platform-adapter.md` Section 2), then `{plugin-root}/skills/blueprint/`
   Store the result as `{skill-dir}`.
2. Read `{skill-dir}/../../references/platform-adapter.md` — cross-platform operations reference.
3. Read `{skill-dir}/references/planning-guide.md` — your operational manual for Intake through Impact Scope Inventory.
4. When entering the Task Breakdown stages, read `{skill-dir}/references/task-breakdown-guide.md`.

Reference paths you will pass to sub-agents (always as **absolute paths** — sub-agents start with a fresh context):
- `{skill-dir}/references/scope-scanner-guide.md`
- `{skill-dir}/references/scope-verifier-guide.md`
- `{skill-dir}/references/plan-reviewer-guide.md`
- `{skill-dir}/references/plan-template.md`, `{skill-dir}/references/task-template.md` (used by you directly)
- `{skill-dir}/../../references/platform-adapter.md`

## Pipeline — you drive every stage

Follow `planning-guide.md` stage by stage:

- **Intake**: Parse the input (ticket ID or natural language). If empty, ask: "你想開發什麼功能？"
- **Requirements Confirmation**: Create the planning document skeleton from `plan-template.md` + requirements confirmation loop with the user. **One question per turn** (`AskUserQuestion` on Claude Code / `ask_user` on Copilot, with choices).
- **Change Scope Inventory**: Scanner→verifier loop (orchestrated by YOU — see below) for method-level change scope → present scope → user confirms.
- **Implementation Direction**: Produce discussion list → discuss topics one by one with the user → consolidate decisions → user confirms.
- **Impact Scope Inventory**: Scanner→verifier loop for impact scope → present impact → user confirms.
- **Task Framework Confirmation → Task Detailing → Plan Freeze & Handoff**: per `task-breakdown-guide.md`.

## Scanner→Verifier loop (both scope inventories) — orchestrator-driven

scope-scanner has no agent-spawning tool — **you** run the verification loop:

```
FOR iteration k = 1..3:
    1. Spawn get-it-done:scope-scanner with: plan doc path, mode (change-scope | impact-scope),
       absolute path to scope-scanner-guide.md + platform-adapter.md, iteration k,
       and (k > 1) the verifier's issue list from the previous iteration to fix.
    2. After the scanner returns, spawn get-it-done:scope-verifier with: plan doc path,
       same mode, absolute path to scope-verifier-guide.md, iteration k.
    3. Read the verifier's report:
       - PASS → exit loop, present the scope to the user.
       - issues found AND k < 3 → next iteration (scanner fixes with the issue list).
       - issues found AND k == 3 → escalate to the user with the unresolved issue list;
         let the user decide (accept as-is / adjust requirements / abort).
4. Confirm the matching summary annotation exists in the plan doc
   (`<!-- scope-verifier(change-scope): -->` or `<!-- scope-verifier(impact-scope): -->`).
   If the verifier forgot it, re-state its verdict in the doc yourself before presenting
   to the user.
```

**Spawn protocol** (see `platform-adapter.md` Section 4 — sub-agents MUST run as isolated subagents, not inline):
- **Claude Code**: `Agent` tool with `subagent_type: "get-it-done:scope-scanner"` / `"get-it-done:scope-verifier"` / `"get-it-done:plan-reviewer"`
- **GitHub Copilot**: delegate to the discoverable custom agent by name (`get-it-done-scope-scanner`, etc.) and instruct it to run in its own context and return only its result — don't let Copilot run the analysis inline.

## Plan Freeze & Handoff — to /continue

After the user confirms the task list:

1. Spawn **get-it-done:plan-reviewer** with the planning document path and the absolute path to `plan-reviewer-guide.md`. Do not proceed without it.
   - PASS → continue below.
   - RETURN TO TASK DETAILING / IMPLEMENTATION DIRECTION / REQUIREMENTS CONFIRMATION → go back to that stage, fix, re-confirm with the user, re-run plan-reviewer.
2. Mark the planning document status as `已凍結，進入執行`.
3. **Initialize get-it-done execution state** (follow the Plan Freeze & Handoff section of `task-breakdown-guide.md` exactly):
   - Bootstrap `.get-it-done/` if not already present (platform-adapter.md Section 7)
   - Write `.get-it-done/goal.md` with the feature description
   - Write `.get-it-done/task_queue.md` in v2 DAG format **including the `## Milestones` section**
   - Write `.get-it-done/metrics.md` (validators read acceptance criteria from here by stable ID — single source of truth for criteria)
   - Write `.get-it-done/state.md` YAML block with `phase: EXECUTING`
   - Append `[/PLAN_COMPLETE]` to `.get-it-done/progress_log.md`
4. Tell the user: "規劃完成，執行 `/continue` 開始自主執行"

## Key Rules

- **Document path**: `{project-root}/docs/plans/{xxx}-plan/{xxx}-plan.md` — derive `{xxx}` from feature name or ticket ID
- **Task file path**: `{project-root}/docs/plans/{xxx}-plan/tasks/{n:02d}-{task-slug}-task.md`
- **One question per turn** during the Requirements Confirmation and Implementation Direction loops.
- **Always update the planning document immediately** after each stage — no "fill in later".
- **Ticket systems**: read work item body + acceptance criteria only. Never write back.
- **File path verification**: verify every path exists via `glob`/`grep` before writing into task definitions.
- **Every task must have**: concrete file paths, actionable steps (function-level), verification method, and test flag.
- **Planning-stage gate**: do not enter the Task Breakdown stages until Impact Scope Inventory is confirmed by the user.
- **Scanner/verifier loop limit**: maximum 3 iterations per mode. If exceeded → escalate to the user.
- **Do not proceed past Plan Freeze & Handoff** without a plan-reviewer PASS.

## Sub-agents spawned (all non-interactive)

| Sub-agent | When | Role |
|-----------|------|------|
| `get-it-done:scope-scanner` | Change Scope Inventory and Impact Scope Inventory (per loop iteration) | Codebase scope / impact inventory written into the plan doc |
| `get-it-done:scope-verifier` | After each scanner pass | Independently validates the scanner's inventory |
| `get-it-done:plan-reviewer` | After the user confirms Plan Freeze | Audits the frozen plan before handoff |

## Output

A planning document at `{project-root}/docs/plans/{xxx}-plan/{xxx}-plan.md` with individual task files in `tasks/`, plus an initialized `.get-it-done/` directory ready for `/continue`.
