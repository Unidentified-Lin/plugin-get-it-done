# Planning Document Template

> **Usage**: Copy this template when creating a new planning document (Requirements Confirmation stage).
> Save to: `{project-root}/docs/plans/{xxx}-plan/{xxx}-plan.md`
> Replace all `{...}` placeholders. Remove hint lines (starting with `>`).

---

# {Feature Name} — Planning Document

**Status**: 草稿（Draft）
**Created**: {YYYY-MM-DD}
**Ticket / Issue**: {#ID or N/A}

---

## 需求重點

> 1~3 句說明「要做什麼、為什麼」。Requirements Confirmation 澄清後逐步精確化至含邊界條件。

{TBD — 待 Requirements Confirmation 填入}

---

## 限制條件

> 明確的 non-goals、技術限制、相依條件、已知風險。Requirements Confirmation 過程中持續更新。

- {TBD}

---

## 異動範圍

> 依需求性質彈性列出受影響的子項。Requirements Confirmation 確認大項；Change Scope Inventory 由 scope-scanner 填入 method-level 明細。

- **專案 / 模組**: {TBD}
- **影響 API**: {TBD or N/A}
- **DB Schema**: {TBD or N/A}
- **Feature Flag / 設定**: {TBD or N/A}
- **其他**: {TBD or N/A}

### 異動範圍（詳細）

> Change Scope Inventory 階段由 scope-scanner 盤點並填入，scope-verifier 驗證通過後生效。
> 格式：`ClassName.methodName` 或 `module/file.ext` — 異動原因

{TBD — 待 Change Scope Inventory（scope-scanner）填入}

---

## 實作方向重點

> Implementation Direction 階段：orchestrator 提出 2~3 方案由使用者選定，再填入各變更點的實作方向。

**選定方案**: {方案 X — 待 Implementation Direction 使用者確認}

### 各變更點實作方向

> Implementation Direction 階段由 orchestrator 填入。

{TBD — 待 Implementation Direction 填入}

---

## 影響範圍

> Impact Scope Inventory 階段由 scope-scanner 盤點功能影響範圍，scope-verifier 驗證通過後生效。

### 直接影響

> 修改的方法被哪些功能直接呼叫

{TBD — 待 Impact Scope Inventory（scope-scanner）填入}

### 間接影響（上下游）

> 共用 Model / DTO、事件、API 合約等連鎖影響

{TBD — 待 Impact Scope Inventory（scope-scanner）填入}

---

## 任務清單

> Task Framework Confirmation 確認框架後立即建立各 task 檔案（stub）；Task Detailing 逐項填充；Plan Freeze & Handoff 凍結。
> 每個任務的詳細內容在 `tasks/` 目錄下的獨立檔案中維護；此處為摘要與狀態追蹤。

| # | Task 標題 | 測試旗標 | 狀態 | Task 檔案 |
|---|-----------|---------|------|-----------|
| 1 | {Task 1 Title} | {☑ 需要 / ☐ 不需要} | 待執行 | [01-{task-slug}-task.md](tasks/01-{task-slug}-task.md) |
| 2 | {Task 2 Title} | {☑ 需要 / ☐ 不需要} | 待執行 | [02-{task-slug}-task.md](tasks/02-{task-slug}-task.md) |

---

## 文件狀態

> 更新規則：Requirements Confirmation 建立 → 草稿；Plan Freeze & Handoff 使用者確認後 → 已凍結，進入執行。

**目前狀態**: 草稿（Draft）

---
*此文件由 `get-it-done:blueprint` skill 自動建立與維護。*
