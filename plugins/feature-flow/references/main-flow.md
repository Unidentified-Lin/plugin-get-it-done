# Feature Flow — Main Flow Reference

> This document is the authoritative reference for all agents in the `feature-flow` plugin.
> Read this to understand where you are in the overall pipeline and what comes next.

---

## Pipeline Overview

```
A. 需求輸入
   A1. 取得輸入（VSTS Work Item 或對話）
        │
        ▼
B. 規劃文件（漸進式成長）　🤖 planner　👾 scope-scanner　👻 scope-verifier

   B1. 需求確認循環 🤖
        a. 建立規劃文件骨架（從 plan-template.md 產出初始 3-block skeleton）
           ┌──────────────────────────────────────────┐
           │ 1. 需求重點                               │
           │ 2. 異動範圍（專案/模組，子項依需求彈性列）  │
           │ 3. 實作方向重點（列點描述）                │
           └──────────────────────────────────────────┘
        b. 精煉需求、列點描述需求重點
        c. 範圍界定（專案/模組/API/Job 大項）
        d. 總結需求重點請使用者確認 ←────────── 循環① 使用者確認/補充
             ↓
   B2. 異動範圍盤點 👾↔👻 → 🤖 確認
        a. 自動 spawn scope-scanner：盤點異動範圍（method-level）
        b. scope-scanner 完成後自動 spawn scope-verifier 驗證
        c. verifier 不通過 → 交回 scanner 修正 ←── 循環② 上限 3 次
        d. verifier 通過 → planner 向使用者摘要呈現異動範圍
        e. 使用者確認異動範圍 ←──────────────────── 循環③
             ├─ 確認 → 進入 B3
             └─ 質疑/調整 → 討論後必要時重跑 scanner
             ↓
   B3. 實作方向確認 🤖
        a. planner 分析需求與異動範圍，產出討論清單
        b. 逐項討論：每項提出方案/觀點 → 使用者選擇/回覆
           → 更新計畫 md ←────────────────── 循環④ 逐項討論
        c. 討論完畢，使用者可提出新議題 ←──── 循環⑤ 補充議題
        d. planner 整理實作方向，使用者最終確認
             ├─ 確認 → 進入 B4
             └─ 想重新討論某議題 → 回到該議題
             ↓
   B4. 影響範圍盤點 👾↔👻 → 🤖 確認
        a. 自動 spawn scope-scanner：盤點功能影響範圍
        b. scanner 完成後自動 spawn verifier 驗證 ←── 循環⑥ 上限 3 次
        c. verifier 通過 → planner 描述影響範圍，使用者確認
             ├─ 確認無誤 → 進入 C 階段
             ├─ 需微調 → 討論後更新 ←──────── 循環⑦
             ├─ 想換方案 → 退回 B3 重新討論
             └─ 範圍有問題 → 退回 B2 重跑盤點
        │
        ▼
C. 任務細化　🤖 planner　📋 plan-reviewer

   C1. 任務框架確認 🤖
        a. planner 呈現目前任務框架（從 B2~B4 漸進成長的任務清單）
        b. 使用者確認框架方向 ←──────────── 循環⑧ 使用者調整框架
             ├─ 確認 → 進入 C2
             └─ 需調整 → 修改後重新確認
             ↓
   C2. 逐項填充 🤖
        a. 外科手術式 codebase 勘查
        b. 逐項填入：檔案路徑、實作步驟、驗證方式、測試旗標
        c. 建立各 task 獨立檔案
             ↓
   C3. 任務清單確認與審核 🤖 → 📋
        a. planner 呈現完整任務清單，請使用者確認凍結
        b. 使用者確認 ←──────────────────── 循環⑨ 使用者調整細節
        c. 確認後自動 spawn plan-reviewer 審核規劃文件完整性
        d. plan-reviewer 審核結果
             ├─ 通過 → 進入 D ✅
             ├─ 任務缺漏/細節不足 → 退回 C2 補充    ←── 循環⑩
             ├─ 方案方向有誤 → 退回 B3 重新討論      ←── 循環⑩
             └─ 需求理解偏差 → 退回 B1 重新澄清      ←── 循環⑩
        │
        ▼
D. 實作執行　🛠️ task-executor　🔎 task-reviewer

   D1. 執行任務 🛠️
        a. task-executor 執行一個任務的程式碼變更
             ↓
   D2. 任務審查 🔎
        a. task-reviewer 審查（spec 符合性 + 程式碼品質）
        b. 審查結果
             ├─ 通過 → 進入 D3
             ├─ 小問題 → 原地修正（回 D1 重試）  ←── 循環⑪
             └─ 大問題 → 退回 C2 重新規劃        ←── 循環⑫
             ↓
   D3. 單元測試驗證 🛠️（條件性，由 C2 測試旗標控制）
        a. 執行既有測試 + 補強/新增缺少的測試
        b. 測試結果
             ├─ 通過 → 下一個任務（回 D1）
             └─ 失敗 → 退回 D1 修正程式碼        ←── 循環⑬
        │（全部任務完成後）
        ▼
E. 程式碼審查　✅ conventional-reviewer

   E1. 全面審查 ✅
        a. conventional-reviewer 依 checklist 審查所有變更
             ↓
   E2. 問題分級呈現 ✅
        a. 審查結果
             ├─ 無問題 → 完成 🎉
             ├─ 輕微問題 → 原地修正 → 回 E1    ←── 循環⑭
             └─ 重大問題 → 退回 D1 → 重跑 E    ←── 循環⑮
```

---

## Step Positioning Table

| Step | Entry Condition | Output | Agent | Next |
|------|-----------------|--------|-------|------|
| A1 | User triggered | Raw requirement (VSTS or conversation) | planner | B1 |
| B1 | Have requirement input | Draft planning doc + refined requirement highlights + scope boundaries | planner | B2 (user confirm) |
| B2 | B1 user confirmed | Method-level change scope in plan doc | scope-scanner + scope-verifier | B3 (user confirm scope) |
| B3 | B2 user confirmed scope | Discussion list outcomes + implementation direction in plan doc | planner | B4 (user confirm direction) |
| B4 | B3 user confirmed direction | Impact scope inventory in plan doc | scope-scanner + scope-verifier | C1 (user confirm) / B3 / B2 |
| C1 | B4 user confirmed impact scope | User confirms framework direction | planner | C2 |
| C2 | Framework confirmed | Each task filled with: file paths, steps, verification, test flag | planner | C3 |
| C3 | All tasks filled | User confirms freeze → plan-reviewer review: pass / return (with level) | planner + plan-reviewer | D (pass) or return to B1/B3/C2 |
| D1 | Frozen planning doc + pending tasks | One task's code changes | task-executor | D2 |
| D2 | D1 complete | Review result: pass / minor / major | task-reviewer | D3 (pass) or return |
| D3 | D2 pass + test flag enabled | Test execution result | task-executor | Next D1 or E |
| E1 | All tasks complete | Line-by-line review results | conventional-reviewer | E2 |
| E2 | E1 complete | Tiered issue list: minor / major | conventional-reviewer | Complete / return |

---

## Planning Document Progressive Growth

```
初期（骨架）                              後期（具體）
──────────────────────────────────────────────────────────
## 需求重點（1句模糊描述）    →   ## 需求重點（精確、含邊界條件）
## 異動範圍（專案名稱）       →   ## 異動範圍（專案 + method-level 明細）
                              →   ## 異動範圍（詳細）（controller/service/repository 方法級）
## 實作方向重點（TBD）        →   ## 實作方向重點（具體步驟、防禦邏輯）
                              →   ## 影響範圍（直接影響 + 間接影響）
## 任務框架                  →   ## 任務（每項含：檔案、步驟、驗證、測試旗標）
```

## Document Update Checkpoints

| Step | Update Action |
|------|--------------|
| B1 (first round) | Create document; fill initial 3-block skeleton |
| After each B1 round | Update requirement highlights, adjust scope |
| After B2 verification pass | Add method-level 異動範圍（詳細） section |
| After B2 user confirms scope | Finalize 異動範圍 section |
| After each B3 topic decision | Update plan doc with that topic's decision |
| After B3 user confirms direction | Update 選定方案, 實作方向重點, 各變更點實作方向 |
| After B4 verification pass | Add 影響範圍 section (direct + indirect impacts) |
| C1 framework confirmed | Lock task list structure |
| After each C2 task fill | Update that task's file paths, steps, verification, test flag |
| C3 confirmed | Mark document status as "已凍結，進入執行" |

---

## Key Constraints

- **VSTS**: Read Work Item body + Acceptance Criteria only. Never write back.
- **Planning document path**: `{project-root}/docs/feature-flow/{xxx}-plan/{xxx}-plan.md`
- **Task file path**: `{project-root}/docs/feature-flow/{xxx}-plan/tasks/{n:02d}-{task-slug}-task.md`
- **Test enforcement**: Controlled by per-task test flag set in C2. Not mandatory.
- **Plugin independence**: `feature-flow` does not depend on `git-workflow` or `db-operation`.
