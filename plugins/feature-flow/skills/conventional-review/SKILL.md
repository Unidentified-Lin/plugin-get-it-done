---
name: conventional-review
description: >-
  Reviews code changes against 91APP engineering standards using a structured
  checklist. Issues are classified as minor (fix-in-place) or major (return
  to implementation). Use after implementation is complete, or independently
  to review any code change. Requires a clear scope (branch, commit, git diff,
  or file list) — will ask the user to specify scope if not provided.

  Triggers on: "程式碼審查", "code review", "審查", "review", "review code",
  "conventional review", "檢查程式碼品質", requests to check code before PR.

  Do NOT trigger for planning requests — use `plan` instead.
  Do NOT trigger for implementation requests — use `execute` instead.
---

# Conventional Review Skill

This skill drives the full code review pipeline (step E) using a structured
91APP engineering checklist.

## Startup

Before doing anything else:
1. Run `/skills info conventional-review` to get this skill's absolute directory path. Store it as `{skill-dir}`.
2. Read `{skill-dir}/../../references/main-flow.md` — full pipeline map and step positioning table.

When spawning the conventional-reviewer sub-agent, pass these **absolute paths** in the task prompt:
- The review scope (branch / commit / file list)
- `{skill-dir}/references/conventional-review-guide.md`
- `{skill-dir}/references/conventional-review-checklist.md`

## Entry Behavior

| Situation | Action |
|-----------|--------|
| Clear scope provided (git diff / branch / commit / file list) | Proceed directly to review |
| Scope unclear | Ask user: "要審查哪些異動？（branch / commit / 指定檔案）" — do NOT start review until confirmed |

## What this skill does

1. Confirms the review scope with the user if not already clear.
2. Spawns **conventional-reviewer** sub-agent via `task` tool (using
   `conventional-reviewer.agent.md` + `references/conventional-review-guide.md` +
   `references/conventional-review-checklist.md` as prompt context) to audit all changes.
3. Presents tiered results: **輕微** issues are fixed in-place by re-spawning the
   sub-agent; **重大** issues are escalated back to `execute`.

## Sub-agent spawned

- **conventional-reviewer** — spawned via `task` tool; runs the full E1+E2 review
  in an isolated context and returns a structured report. Non-interactive.

## References to include in sub-agent prompt

Absolute paths are passed via the task prompt (see Startup above). Files are located at:

| File | Purpose |
|------|---------|
| `{skill-dir}/references/conventional-review-guide.md` | conventional-reviewer workflow + output format |
| `{skill-dir}/references/conventional-review-checklist.md` | 91APP engineering standards checklist |
