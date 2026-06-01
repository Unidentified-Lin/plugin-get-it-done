# feature-flow

Complete feature development lifecycle plugin for 91APP engineers.

## Skills

| Skill | Description |
|-------|-------------|
| `plan` | Analyze requirements → produce a frozen planning document (A+B+C) |
| `execute` | Implement code changes task-by-task using sub-agents (D) |
| `conventional-review` | Full code review against 91APP engineering standards (E) |

## Typical Full Flow

```
/feature-flow:plan  →  /feature-flow:execute  →  /feature-flow:conventional-review
```

Each skill can also be used independently.

## Agents

| Agent | Role |
|-------|------|
| `plan-reviewer` | Reviews frozen planning documents for completeness (after C3) |
| `task-executor` | Executes a single implementation task (D1+D3) |
| `task-reviewer` | Reviews completed task output for spec compliance and code quality (D2) |
| `conventional-reviewer` | Full review of all changes against 91APP checklist (E1+E2) |

> Requirement understanding, planning document construction, and task breakdown (A+B+C) are now handled directly by the main agent via the `plan` skill.

## Planning Document Location

Planning documents are saved to `{project-root}/docs/feature-flow/{xxx}-plan/{xxx}-plan.md`, with individual task files at `{project-root}/docs/feature-flow/{xxx}-plan/tasks/`.


## Main flow reference: `skills/plan/references/main-flow.md` — contains the full pipeline map and step positioning table for quick reference during all phases.