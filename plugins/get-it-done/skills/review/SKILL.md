---
name: review
description: >-
  Reviews code changes against universal engineering standards using a structured
  checklist (correctness, error handling, security, data integrity, performance,
  code quality, test coverage, maintainability). Issues are classified as Minor
  (fix in-place) or Major (return to implementation). Use after implementation
  is complete, or independently to review any code change. Requires a clear
  scope (branch, commit, git diff, or file list) — will ask the user to specify
  scope if not provided.

  Triggers on: "程式碼審查", "code review", "審查", "review", "review code",
  "review changes", "檢查程式碼品質", requests to check code before PR.

  Do NOT trigger for planning requests — use /plan instead.
  Do NOT trigger for implementation requests — use /objective or /continue instead.
---

# Review Skill

This skill drives the full code review pipeline using a structured engineering checklist.

## Platform Setup

Before doing anything else:
1. Locate this skill's absolute directory path:
   - **Claude Code**: `${CLAUDE_PLUGIN_ROOT}/skills/review/` or run `/skills info review`
   - **GitHub Copilot**: Run `/skills info review`
   Store the result as `{skill-dir}`.
2. Read `{skill-dir}/../../references/platform-adapter.md` — cross-platform operations reference.

## Entry Behavior

| Situation | Action |
|-----------|--------|
| Clear scope provided (git diff / branch / commit / file list) | Proceed directly to review |
| Scope unclear | Ask user: "要審查哪些異動？（branch / commit / 指定檔案）" — do NOT start review until confirmed |

## What this skill does

Spawn the **code-reviewer** sub-agent, passing these **absolute paths** in the prompt:
- The review scope (branch / commit / file list)
- `{skill-dir}/references/review-guide.md`
- `{skill-dir}/references/review-checklist.md`
- `{skill-dir}/../../references/platform-adapter.md`

**Spawn protocol:**
- **Claude Code**: Use `Agent` tool with `subagent_type: "get-it-done:code-reviewer"`
- **GitHub Copilot**: Use `task` tool with `agent_type: "get-it-done:code-reviewer"`

## Loop Management

```
Review complete
  │
  ├─ PASS → Report to user: "Code review passed. Ready for PR."
  │
  ├─ MINOR ISSUES only → Fix in-place → Re-run review → Expect PASS
  │
  └─ MAJOR ISSUES → Report to user: return to implementation
      Include specific fix instructions for each major issue
```

## Output

A tiered review report: **PASS** / **MINOR ISSUES** (with fix instructions) / **MAJOR ISSUES** (with rework instructions).
