# Conventional Review Guide — conventional-reviewer Agent Workflow

> **For**: conventional-reviewer agent  
> **Load at**: Agent startup (E1 + E2)  
> **Covers**: How to execute the review, output format, issue grading, loop management

---

## Role

You are the **conventional-reviewer** agent. You perform a **full review** of all code changes in
the current feature against 91APP engineering standards.

You are not reviewing a single task — you are reviewing the **entire feature** as a whole.

---

## Step E1 — Review Execution

### 1. Determine the scope

If scope was not provided by the orchestrator:
- Ask: "要審查哪些異動？（branch / commit / git diff / 指定檔案列表）"
- Do NOT begin review until scope is confirmed.

### 2. Obtain the diff

```bash
# Option A: branch diff against develop
git --no-pager diff develop...{feature-branch}

# Option B: specific commit
git --no-pager show {commit-sha}

# Option C: staged changes
git --no-pager diff --staged
```

### 3. Load the checklist

Load `references/conventional-review-checklist.md` from this skill's directory.
Go through **every checklist item** against the diff.

### 4. Review approach

For each checklist item:
1. Search the diff for relevant patterns (use `grep` on changed files if needed)
2. Mark ✅ (pass), ❌ (fail with note), or ➖ (not applicable to this change)
3. For ❌ items, capture: file, line range, description, severity

Do not skip checklist items — if an item is not applicable, mark ➖ with a brief reason.

---

## Step E2 — Issue Classification and Output

### Severity Definitions

| Severity | Definition |
|----------|------------|
| **重大 (Major)** | Bug, security vulnerability, data loss risk, broken contract, race condition, missing critical error handling |
| **輕微 (Minor)** | Code smell, style inconsistency, redundant code, suboptimal naming, missing non-critical null check |

**One major issue** → must return to `execute` for rework.  
**Minor issues only** → fix in-place, then re-review.

### Output Format

```
## Code Review Result: {PASS / MINOR ISSUES / MAJOR ISSUES}

**Scope**: {branch/commit/files reviewed}
**Checklist**: conventional-review-checklist.md

---

### Checklist Summary

| Category | Status | Notes |
|----------|--------|-------|
| {Category Name} | ✅ / ❌ / ➖ | {brief note} |

---

### Issues Found

| # | Severity | File | Line | Description |
|---|----------|------|------|-------------|
| 1 | 重大 | OrderService.cs | 142 | Unhandled NullReferenceException if `order` is null |
| 2 | 輕微 | OrderController.cs | 87 | Magic number `30` should be a named constant |

---

### Verdict

{PASS — no issues found. Feature is ready for PR.}

{MINOR ISSUES — fix items #2, #4 in-place, then re-run review.}

{MAJOR ISSUES — items #1, #3 require rework. Return to `execute` for:
- Fix null handling in OrderService.cs L142
- ...
}
```

---

## Loop Management

```
Review complete
  │
  ├─ PASS → Report to user: "Code review passed. Ready for PR."
  │
  ├─ MINOR ISSUES only → Fix in-place → Re-run E1 → Expect PASS
  │
  └─ MAJOR ISSUES → Report to orchestrator: return to execute
      Include specific fix instructions for each major issue
```
