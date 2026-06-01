# Task Breakdown Guide — C1, C2, C3 Rules

> **For**: planner agent  
> **Load at**: Entering C phase (after B4 confirmed)  
> **Covers**: C1 framework confirmation, C2 task fill, C3 freeze

---

## Step C1 — Framework Confirmation

Present the current task list skeleton to the user and ask:

> "以下是目前的任務框架，方向正確嗎？有遺漏或需要調整的項目嗎？"

Use `ask_user` with choices:
- "框架正確，繼續細化" → proceed to C1-post (scaffold task files)
- "需要調整" → collect feedback, adjust tasks, re-present

**Exit condition**: User confirms the framework is directionally correct.

---

## Step C1-post — Scaffold Task Files

Immediately after C1 confirmation, create all task files as stubs **before** any C2 investigation. This gives the user a clear picture of scope and lets C2 proceed task-by-task.

**Task file path convention**:

```
{project-root}/docs/feature-flow/{xxx}-plan/tasks/{n:02d}-{task-slug}-task.md
```

- `{xxx}` matches the plan folder name (e.g., `vsts502199-add-login`)
- `{n:02d}` is zero-padded task number (01, 02, …)
- `{task-slug}` is a lowercase-hyphenated short title (e.g., `update-order-service`)

**For each task**:
1. Read `task-template.md` (path provided in your task prompt; see Startup in SKILL.md).
2. Create the task file using the template — fill in task number and title only; leave all other fields as `{TBD}`.
3. Update the main plan document's 任務清單 summary table to reference the new file.

After all task files are created, proceed to C2.

---

## Step C2 — Task Fill (Surgical Codebase Investigation)

For each task, open its task file at `tasks/{n}-{task-slug}-task.md` and perform a **surgical** codebase investigation:
- Use `grep` / `glob` to locate exact file paths, class names, method signatures.
- Do NOT explore broadly — only look up what is needed for this specific task.

Fill each task file's sections:

```markdown
## 任務說明
一句話描述此任務做什麼（具體，含方法/模組名）

## 檔案路徑
- `path/to/File.cs` — 說明此檔案的角色

## 實作步驟
1. 具體步驟（動詞開頭，含方法名稱）
2. …

## 驗證方式
如何確認這個任務做對了
```

Also update the 測試旗標 in the task file and sync it back to the main plan document's 任務清單 summary table.

### Test Flag Rules

Set **☑ 需要測試** when:
- The task modifies business logic, calculations, or conditional branching
- The task adds or changes API contract (request/response shape)
- The task touches security, permission, or data validation logic

Set **☐ 不需要測試** when:
- The task is pure config change (no logic)
- The task adds a new endpoint that is already covered by integration tests
- The task is UI-only (no backend logic change)

### Quality bar for C2 fill

A task is considered fully filled when:
- [ ] File path(s) point to actual existing files (verified via `glob`/`grep`)
- [ ] Implementation steps use concrete method/class names, not vague descriptions
- [ ] Verification method is specific and checkable (not "make sure it works")
- [ ] Test flag is explicitly set

---

## Step C3 — Final Confirmation and Freeze

Present the complete task list to the user:

> "以下是完整的任務清單，請確認後我將凍結規劃文件並進入執行。"

Use `ask_user` with choices:
- "確認，凍結並進入執行" → freeze all documents; trigger plan-reviewer
- "需要調整" → return to C2 for the specific tasks mentioned

**After C3 confirmation**:
1. Update main plan document status line to: `**目前狀態**: 已凍結，進入執行`
2. Update each task file's **狀態** field to `待執行（Pending）` (already the default).
3. Automatically trigger **plan-reviewer** agent (load `references/plan-reviewer-guide.md`).

---

## Freeze Conditions

The document may only be frozen (C3 pass) when ALL of the following are true:

- [ ] 需求重點 is precise (contains success criteria and boundaries)
- [ ] 異動範圍 lists concrete projects, APIs, schemas — not just "TBD"
- [ ] 實作方向重點 describes the chosen approach with enough detail to implement
- [ ] All task files exist at `tasks/{n}-{task-slug}-task.md`
- [ ] Every task file has: file paths (verified), steps (concrete), verification, test flag — no TBD
- [ ] Main plan document 任務清單 summary table is up to date with all task file links
