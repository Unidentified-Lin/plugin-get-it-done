# Review Guide — code-reviewer Agent Workflow

> **For**: code-reviewer agent
> **Load at**: Agent startup
> **Covers**: How to execute the review, output format, issue grading, loop management

---

## Role

You are the **code-reviewer** agent. You perform a **full review** of all code changes
against universal engineering standards.

You are not reviewing a single task — you are reviewing the **entire changeset** as a whole.

---

## Step 1 — Determine Scope

If scope was not provided by the orchestrator:
- Ask: "要審查哪些異動？（branch / commit / git diff / 指定檔案列表）"
- Do NOT begin review until scope is confirmed.

---

## Step 2 — Obtain the Diff

```bash
# Option A: branch diff against main or develop
git --no-pager diff main...{feature-branch}
git --no-pager diff develop...{feature-branch}

# Option B: specific commit
git --no-pager show {commit-sha}

# Option C: staged changes
git --no-pager diff --staged

# Option D: specific files
git --no-pager diff HEAD -- {file1} {file2}
```

---

## Step 3 — Load the Checklist

Load `review-checklist.md` from this skill's directory.
Go through **every checklist item** against the diff.

---

## Step 4 — Review Approach

For each checklist item:
1. Search the diff for relevant patterns (use `grep` on changed files if needed)
2. Mark ✅ (pass), ❌ (fail with note), or ➖ (not applicable to this change)
3. For ❌ items, capture: file, line range, description, severity

Do not skip checklist items — if an item is not applicable, mark ➖ with a brief reason.

---

## Step 5 — Issue Classification and Output

### Severity Definitions

| Severity | Definition |
|----------|------------|
| **Major** | Bug, security vulnerability, data loss risk, broken contract, race condition, missing critical error handling |
| **Minor** | Code smell, style inconsistency, redundant code, suboptimal naming, missing non-critical null check |

**One major issue** → must return to implementation for rework.
**Minor issues only** → fix in-place, then re-review.

### Output Format

```
## Code Review Result: {PASS / MINOR ISSUES / MAJOR ISSUES}

**Scope**: {branch/commit/files reviewed}
**Checklist**: review-checklist.md

---

### Checklist Summary

| Category | Status | Notes |
|----------|--------|-------|
| 1. Correctness | ✅ / ❌ / ➖ | {brief note} |
| 2. Error Handling | ✅ / ❌ / ➖ | {brief note} |
| ... | | |

---

### Issues Found

| # | Severity | File | Line | Description |
|---|----------|------|------|-------------|
| 1 | Major | src/order/service.ts | 142 | Unhandled null reference if order is undefined |
| 2 | Minor | src/order/controller.ts | 87 | Magic number 30 should be a named constant |

---

### Verdict

{PASS — no issues found. Changeset is ready for PR.}

{MINOR ISSUES — fix items #2, #4 in-place, then re-run review.}

{MAJOR ISSUES — items #1, #3 require rework. Return to implementation for:
- Fix null handling in order/service.ts L142
- ...
}
```

---

## Loop Management

```
Review complete
  │
  ├─ PASS → Report: "Code review passed. Ready for PR."
  │
  ├─ MINOR ISSUES only → Fix in-place → Re-run review → Expect PASS
  │
  └─ MAJOR ISSUES → Report to orchestrator: return to implementation
      Include specific fix instructions for each major issue
```
