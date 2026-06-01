# Plugin `feature-flow` — 開發計畫

> 參考：[obra/superpowers](https://github.com/obra/superpowers)  
> 原則：漸進式展開，由大而小，逐步確認後再細化

---

## 一、背景與目標

建立新的 plugin `feature-flow`，涵蓋 91APP 開發人員的**完整功能開發生命週期**。

**與現有 plugins 關係：完全獨立**（不依賴 `git-workflow` 或 `db-operation`）

---

## 二、主流程

```
A. 需求輸入
   A1. 取得輸入（VSTS Work Item 或對話）
        │
        ▼
B. 規劃文件（漸進式成長）

   B1. 需求確認循環（🤖 planner）
        → 建立規劃文件骨架（需求重點、異動範圍、實作方向重點）
        → 需求不明確時問答澄清  ←────────────── 循環① 問答直到充分理解
        → 填充需求重點 + 限制條件
         ↓
   B2. 異動範圍盤點（👾 scope-scanner ↔ 👻 scope-verifier）
        → scanner 勘查 codebase 列出異動範圍
        → verifier 驗證完整性  ←─────────────── 循環② scanner↔verifier 最多 3 輪
        → 超過 3 輪未收斂 → 上報 planner 決策
        → verifier 通過 → planner 摘要呈現異動範圍
        → 使用者確認異動範圍  ←─────────────── 循環③ 使用者確認/質疑
         ↓
   B3. 實作方向確認（🤖 planner）
        → planner 分析需求+異動範圍，產出討論清單
        → 逐項討論：方案/觀點 → 使用者回覆  ←────── 循環④ 逐項討論
        → 討論完畢，使用者可補充新議題  ←────────── 循環⑤ 補充議題
        → planner 整理實作方向，使用者最終確認
        → 使用者確認後進入 B4
         ↓
   B4. 影響範圍盤點（👾 scope-scanner ↔ 👻 scope-verifier）
        → 基於選定方案，掃描影響範圍  ←───── 循環⑥ scanner↔verifier 最多 3 輪
        → 超過 3 輪未收斂 → 上報 planner 決策
        → planner 描述影響範圍，使用者確認  ←── 循環⑦
             ├─ 確認無誤 → 進入 C 階段
             ├─ 需微調 → 討論後更新
             ├─ 想換方案 → 退回 B3 重新討論
             └─ 範圍有問題 → 退回 B2 重跑盤點

   ↑ 以上過程中，任務框架同步成長（由粗到細，像 Stable Diffusion 成圖）
        │
        ▼
C. 任務細化
   C1. 使用者確認任務框架（方向對了嗎？）←── 循環⑧ 使用者調整框架
   C2. 逐項填充（外科手術式 codebase 勘查 → 填入檔案路徑、步驟、驗證、測試旗標）
   C3. 使用者確認最終任務清單 ←──────────── 循環⑨ 使用者調整細節
        │
        ▼ C3 確認後自動觸發
   [plan-reviewer]：審核規劃文件完整性
        ├─ 無問題 → 進入 D ✅
        ├─ 任務缺漏/細節不足 → 退回 C2 補充        ←── 循環⑩
        ├─ 方案方向有誤 → 退回 B3 重新提案          ←── 循環⑩
        └─ 需求理解偏差 → 退回 B1 重新澄清          ←── 循環⑩
        │（審核通過）
        ▼
D. 實作執行
   ┌──→ D1. sub-agent 執行一個任務
   │    D2. 任務後審查（spec 符合性 + 程式碼品質）
   │         ├─ 通過 → D3
   └─────────┤ 小問題 → 原地修正（回 D1 重試）  ←── 循環⑪ 任務執行微循環
             └─ 大問題 → 退回 C2 重新規劃        ←── 循環⑫ 執行發現設計問題
   D3. 單元測試驗證（條件性，由 C2 測試旗標控制）
        ├─ 執行既有測試 + 補強/新增缺少的測試
        ├─ 失敗 → 退回 D1 修正程式碼            ←── 循環⑬ 測試驅動修正
        └─ 通過 → 下一個任務（回 D1）
        │（全部任務完成後）
        ▼
E. 程式碼審查
   E1. sub-agent 依 checklist 審查
   E2. 問題分級呈現
        ├─ 無問題 → 完成 ✅
        ├─ 輕微問題 → 原地修正 → 回 E1  ←──── 循環⑭ 審查微修正
        └─ 重大問題 → 退回 D1 → 重跑 E  ←──── 循環⑮ 大改重驗
```

**步驟定位表（供 agent 定位自己在流程中的位置）**

| 步驟 | 進入條件 | 輸出 | 執行 Agent | 下一步 |
|------|---------|------|-----------|-------|
| A1 | 使用者觸發 | 需求原文（VSTS 或對話） | planner | B1 |
| B1 | 有需求輸入 | 規劃文件骨架 + 需求重點 + 限制條件 | planner | B2 |
| B2 | 需求充分理解後 | 異動範圍清單（經 scanner↔verifier 驗證 + 使用者確認） | scope-scanner ↔ scope-verifier | B3（使用者確認範圍）|
| B3 | 異動範圍使用者確認後 | 討論清單決議 + 實作方向重點（使用者確認） | planner | B4 |
| B4 | 方案確認後 | 影響範圍清單（經 scanner↔verifier 驗證） | scope-scanner ↔ scope-verifier | C1（使用者確認）/ B3 / B2 |
| C1 | 任務框架初步成形 | 使用者確認框架方向 | planner | C2 |
| C2 | 框架確認 | 每個任務填入：檔案路徑、步驟、驗證方式、測試旗標 | planner | C3 |
| C3 | 所有任務填充完成 | 使用者確認凍結，文件狀態 → 已凍結 | planner | plan-reviewer |
| plan-reviewer | C3 通過 | 審核結果：通過 / 退回（含退回層級）| plan-reviewer | D（通過）或退回 B1/B2/B3/C2 |
| D1 | 有凍結規劃文件 + 任務未完成 | 一個任務的程式碼修改 | task-executor | D2 |
| D2 | D1 完成 | 審查結果：通過 / 小問題 / 大問題 | task-reviewer | D3（通過）或退回 |
| D3 | D2 通過 + 測試旗標啟用 | 測試執行結果 | task-executor | 下一個 D1 或 E |
| E1 | 所有任務完成 | 逐項審查結果 | conventional-reviewer | E2 |
| E2 | E1 完成 | 分級問題清單：輕微 / 重大 | conventional-reviewer | 完成 / 退回 |

```
初期（骨架）                              後期（具體）
──────────────────────────────────────────────────────────
## 需求重點（1句模糊描述）    →   ## 需求重點（精確、含邊界條件）
## 異動範圍（專案名稱）       →   ## 異動範圍（專案 + API + Schema + 設定）
## 實作方向重點（TBD）        →   ## 實作方向重點（具體步驟、防禦邏輯）
## 任務框架                  →   ## 任務（每項含：檔案、步驟、驗證、測試旗標）
  - [ ] 建立判斷邏輯          →     - [ ] 修改 CreateBinding（具體步驟）
  - [ ] 補充測試              →     - [ ] 補充 N 個 unit tests（指定類別）
```

---

## 三、流程定義

> 規劃文件是貫穿 B→C 的**單一漸進式文件**，從骨架逐步成熟為具體實作清單。

### A. 需求輸入

- **A1 取得輸入**：VSTS Work Item ID（讀取本文 + AC，只讀不寫）或自由對話

### B. 規劃文件（漸進式成長）

**B1 需求確認循環**（🤖 planner）：建立規劃文件骨架並確認需求。

規劃文件骨架固定包含三個區塊：

| 區塊 | 說明 |
|------|------|
| **需求重點** | 1~3 句說明「要做什麼、為什麼」 |
| **異動範圍** | 依需求性質彈性列出子項，如：專案、影響 API、DB Schema、開關設定等 |
| **實作方向重點** | 列點描述大方向技術策略，允許 TBD，含防禦性設計與邊界條件考量 |

需求不明確時，一次一問，多選題優先 → 更新需求重點 + 限制條件。循環直到充分理解。

**B2 異動範圍盤點**（👾 scope-scanner ↔ 👻 scope-verifier，最多 3 輪）：

- scope-scanner 勘查 codebase，列出受影響的專案/模組/檔案
- scope-verifier 驗證完整性與正確性
- scanner↔verifier 直接循環，最多 3 輪；超過未收斂 → 上報 planner 決策
- verifier 通過 → planner 向使用者摘要呈現異動範圍
- 使用者確認異動範圍 → 進入 B3；質疑/調整 → 討論後必要時重跑 scanner

**B3 實作方向確認**（🤖 planner）：

- planner 分析需求（B1）+ 異動範圍（B2），產出討論清單
- 逐項討論：每項提出方案/觀點 → 使用者選擇/回覆 → 更新計畫 md
- 討論完畢，使用者可提出新議題（循環）
- planner 整理實作方向重點 + 各變更點實作方向
- 使用者最終確認 → 進入 B4；想重新討論 → 回到該議題

**B4 影響範圍盤點**（👾 scope-scanner ↔ 👻 scope-verifier，最多 3 輪）：

- 基於選定方案，scanner 掃描完整影響範圍（含間接依賴）
- verifier 驗證覆蓋完整性
- scanner↔verifier 直接循環，最多 3 輪；超過未收斂 → 上報 planner 決策
- verifier 通過 → planner 描述影響範圍，使用者確認
  - 確認無誤 → 進入 C 階段
  - 需微調 → 討論後更新
  - 想換方案 → 退回 B3 重新討論
  - 範圍有問題 → 退回 B2 重跑盤點

在 B1~B4 過程中，**任務框架同步成長**：每次理解推進，任務項目從無到有、從模糊到具名。

### C. 任務細化

承接 B 的任務框架，確認方向後填充具體內容：

- **C1 確認任務框架**：使用者確認大方向（項目對嗎？有遺漏嗎？）
- **C2 逐項填充**：針對每個任務進行「外科手術式」codebase 勘查（找到具體檔案路徑、類別名稱、方法簽章），再填入：檔案路徑、實作步驟、驗證方式、測試旗標
- **C3 確認任務清單**：使用者最終確認，可調整後才進入執行

### 規劃文件更新原則

規劃文件是 B→C 全程維護的 **single source of truth**，每個步驟推進後必須即時更新對應區塊，不允許「稍後再補」。

| 步驟 | 更新區塊 |
|------|---------|
| B1 建立骨架 | 建立文件，填入初稿三區塊（需求重點、異動範圍、實作方向重點） |
| B1 每輪澄清後 | 更新需求重點、調整限制條件 |
| B2 範圍盤點後 | 更新異動範圍（經 scanner↔verifier 驗證） |
| B3 方案確認後 | 更新實作方向重點、新增/調整任務框架項目 |
| B4 影響盤點後 | 補充影響範圍（間接依賴、上下游） |
| C1 框架確認後 | 鎖定任務清單結構 |
| C2 每個任務填充後 | 更新該任務的檔案路徑、步驟、驗證方式、測試旗標 |
| C3 確認後 | 標記文件狀態為「已凍結，進入執行」 |

### D. 實作執行

- 逐一取出任務，派發 **task-executor** sub-agent 執行
- 每個任務完成後由 **task-reviewer** sub-agent 審查（spec 符合性 + 程式碼品質）
- 小問題原地修正重試；大問題退回 C2 重新規劃
- **D3 單元測試驗證**（條件性，由 C2 測試旗標控制）：執行既有測試 + 補強/新增缺少的測試 → 失敗退回 D1 修正

### E. 程式碼審查

- C3 確認後自動觸發 **plan-reviewer** 審核規劃文件完整性，依問題嚴重度分級退回：
  - 任務缺漏／細節不足 → 退回 C2 補充
  - 方案方向有誤 → 退回 B3 重新提案
  - 需求理解偏差 → 退回 B1 重新澄清
- 全部任務完成後，由 **conventional-reviewer** sub-agent 依 `references/checklist.md` 逐項審查
- 問題分級：輕微 → 原地修正重審；重大 → 退回 D → 重跑 E

---

## 四、目錄結構

```
plugins/feature-flow/
├── plugin.json
├── README.md
├── references/                         ← plugin 層級共享參照（所有 agent 皆可讀取）
│   └── main-flow.md                    ← 完整主流程圖 + 各步驟定位說明
├── skills/
│   ├── plan/                   ← 使用者入口：規劃
│   │   ├── SKILL.md
│   │   └── references/
│   │       ├── plan-template.md          ← 規劃文件樣板（B1 填入起點）
│   │       ├── planning-guide.md         ← planner 操作手冊（A1, B1）
│   │       ├── scope-scanner-guide.md    ← scope-scanner 操作手冊（B2, B4）
│   │       ├── scope-verifier-guide.md   ← scope-verifier 驗證規則（B2, B4）
│   │       ├── task-breakdown-guide.md   ← 任務拆解規範（C1, C2, C3）
│   │       └── plan-reviewer-guide.md    ← plan-reviewer 審核流程與退回判斷規則
│   ├── execute/                ← 使用者入口：執行
│   │   ├── SKILL.md
│   │   └── references/
│   │       ├── execution-guide.md        ← task-executor 執行規則（D1 + D3）
│   │       └── review-guide.md           ← task-reviewer 審查流程（D2）
│   └── conventional-review/    ← 使用者入口：審查
│       ├── SKILL.md
│       └── references/
│           ├── conventional-review-guide.md      ← conventional-reviewer 審查流程（E1, E2）
│           └── conventional-review-checklist.md  ← 91APP 審查清單（agent 對照用）
└── agents/
    ├── planner.agent.md        ← 需求理解、規劃文件建構、任務細化
    ├── scope-scanner.agent.md  ← 勘查 codebase 異動/影響範圍（B2, B4）
    ├── scope-verifier.agent.md ← 驗證 scope-scanner 產出的完整性（B2, B4）
    ├── plan-reviewer.agent.md  ← C3 後自動觸發：審核規劃文件完整性
    ├── task-executor.agent.md  ← 執行單一任務（程式碼修改 + 測試驗證）
    ├── task-reviewer.agent.md  ← 審查任務成果（spec 符合性 + 程式碼品質）
    └── conventional-reviewer.agent.md  ← 依 checklist 全面審查
```

---

## 四之一、references/ 檔案慣例

`references/` 下的檔案**不會自動載入**，由 agent 或 skill 按需求明確讀取。撰寫 `.agent.md` 或 `SKILL.md` 時，需透過以下方式告知 agent 可用資源及載入時機。

### 檔案類型定義

| 後綴 | 定義 | 用途說明 |
|------|------|---------|
| `-template` | 起始骨架文件 | 提供空白結構讓 agent 填入內容，例如規劃文件的初始框架 |
| `-guide` | 操作流程與判斷規則 | 告訴 agent「怎麼做」：執行步驟、循環條件、決策判斷、更新原則 |
| `-checklist` | 明確對照清單 | 告訴 agent「檢查什麼」：逐項核對的條目，有明確完成/不通過判斷 |

### 各 skill 的 references/ 清單

| 層級 | 檔案 | 類型 | 主要使用 Agent |
|------|------|------|--------------|
| **plugin** | `references/main-flow.md` | guide | 所有 agent（定位用） |
| `plan` | `plan-template.md` | template | planner |
| `plan` | `planning-guide.md` | guide | planner |
| `plan` | `scope-scanner-guide.md` | guide | scope-scanner |
| `plan` | `scope-verifier-guide.md` | guide | scope-verifier |
| `plan` | `task-breakdown-guide.md` | guide | planner |
| `plan` | `plan-reviewer-guide.md` | guide | plan-reviewer |
| `execute` | `execution-guide.md` | guide | task-executor |
| `execute` | `review-guide.md` | guide | task-reviewer |
| `conventional-review` | `conventional-review-guide.md` | guide | conventional-reviewer |
| `conventional-review` | `conventional-review-checklist.md` | checklist | conventional-reviewer |

### 在 `.agent.md` 與 `SKILL.md` 中引用 references 的方式

**核心原則（來自 superpowers 與 plugin-forge 實際做法）：**

| 方式 | 說明 | 建議 |
|------|------|------|
| 在 body 文字中明確提及檔名 | `see references/planning-guide.md` | ✅ 推薦，按需讀取 |
| 明確指令告知 agent 讀取時機 | "進入 B 階段前，先讀取 `references/planning-guide.md`" | ✅ 推薦 |
| `@references/file.md` 前綴 | 強制立即載入到 context | ⚠️ 避免，會耗費不必要的 context |

**路徑定位方式（不硬寫絕對路徑）：**

```
使用 glob 或 `/skills info {skill-name}` 找到 skill 目錄，
再以相對路徑讀取該目錄下的 references/{filename}
```

這與 plugin-forge 現有 skill（如 `branch-setup`）定位 `scripts/` 的做法相同。

**實際寫法範例（`.agent.md` body）：**

```markdown
## 啟動指引

開始前，使用 glob 找到 `plan` skill 的目錄，讀取以下檔案：
- `references/planning-guide.md` — 本 agent 的完整操作手冊
- `references/plan-template.md` — 建立規劃文件時使用的起始骨架

進入 C 階段時，額外讀取：
- `references/task-breakdown-guide.md` — 任務拆解規範
```

**實際寫法範例（`SKILL.md` body）：**

```markdown
agent 啟動後會讀取 `references/planning-guide.md` 作為操作手冊。
如需查看樣板格式，參見 `references/plan-template.md`。
```

---

## 五、Agent 職責定義

| Agent | 觸發方式 | 模型 | background | 職責 |
|-------|---------|------|-----------|------|
| **planner** | skill 主流程呼叫 | sonnet | false | 接收需求輸入、澄清問答、建立與更新規劃文件、提出方案、細化任務。涵蓋流程 A + B1 + B3 + C |
| **scope-scanner** | B2/B4 由 planner 派發 | sonnet | false | 勘查 codebase，列出異動範圍或影響範圍。與 scope-verifier 直接循環（最多 3 輪），超過上報 planner |
| **scope-verifier** | scope-scanner 產出後觸發 | sonnet | true | 驗證 scope-scanner 產出的完整性與正確性。以 background agent 運行，提供獨立視角 |
| **plan-reviewer** | C3 確認後自動觸發 | sonnet | true | 以「新鮮視角」審核凍結後的規劃文件。依嚴重度分級退回：任務缺漏 → C2、方案有誤 → B3、範圍有誤 → B2、需求理解偏差 → B1 |
| **task-executor** | D1 每個任務觸發一次 | sonnet | false | 全新 context，依任務描述（檔案路徑、步驟、驗證方式）實際修改程式碼 |
| **task-reviewer** | D2 任務完成後觸發 | sonnet | true | 審查剛完成的任務：① spec 符合性 ② 程式碼品質。需要新鮮視角，不帶實作偏見 |
| **conventional-reviewer** | E 全部任務完成後觸發 | sonnet | false | 依 `references/checklist.md` 對整個 feature 的所有異動進行全面審查，問題分級呈現 |

---

## 六、Skills 定義

Skills 是對外（使用者）可見的入口點，共三個。細節手冊放在各 skill 的 `references/` 下，僅供 agent 按需載入，使用者不需直接接觸。

### 入口 Skills 總覽

| Skill | 對應流程 | 派發 Agent |
|-------|---------|-----------|
| **plan** | A + B + C | planner（全程）、scope-scanner + scope-verifier（B2/B4）、plan-reviewer（C3 後自動） |
| **execute** | A + B + C（輕量）+ D | planner（輕量規劃）、scope-scanner + scope-verifier、task-executor、task-reviewer |
| **conventional-review** | E | conventional-reviewer |

### 獨立 vs 組合運作

三個 skill **各自獨立可用，也可組合成完整流程**：

```
完整流程：  /feature-flow:plan  →  /feature-flow:execute  →  /feature-flow:conventional-review
部分流程：  /feature-flow:execute   （跳過 plan，直接規劃+執行）
單點使用：  /feature-flow:conventional-review  （僅審查，不執行）
```

| Skill | 獨立使用時行為 | 必要前提 |
|-------|--------------|---------|
| **plan** | 產出規劃文件後停止，不進入執行 | 需求（對話或 VSTS）|
| **execute** | 內建輕量規劃（A+B+C，可精簡），再接 D | 需求（對話或 VSTS）；若完全無說明 → 詢問使用者 |
| **conventional-review** | 直接派發 conventional-reviewer | 明確的異動範圍；範圍不夠清楚 → 詢問使用者再繼續 |

#### `execute` 無規劃文件時的行為

- 有需求輸入（VSTS ID 或自然語言描述）→ 執行輕量規劃（B1~B4 + C，視複雜度可精簡）
- 需求不足（`/feature-flow:execute` 空呼叫）→ 先問：「你想修改什麼？」，等待使用者描述後再繼續
- 有現成規劃文件（狀態為「已凍結」）→ 直接進入 D，跳過規劃流程

#### `conventional-review` 無明確範圍時的行為

- 有 git diff / 指定異動範圍 → 直接審查
- 範圍不明確 → 詢問：「要審查哪些異動？（branch / commit / 指定檔案）」，確認後才執行
- 不在確認前展開審查

---

### `plan`

**Frontmatter 草稿：**

```yaml
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
```

**觸發詞（初稿）：** 「開始新功能」、「分析需求」、「我要開發」、「start feature」、「analyze requirement」、VSTS Work Item ID 出現時

**獨立行為：** 產出規劃文件（含 plan-reviewer 審核）後停止，不進入執行階段。

**職責：**
1. 接收輸入（VSTS 或對話）→ 建立初步規劃骨架（B1）
2. 驅動 planner agent 執行 B1（需求確認循環）
3. 派發 scope-scanner↔scope-verifier 執行 B2（異動範圍盤點）
4. 驅動 planner 提案，使用者選定後直接更新計畫 md（B3）
5. 派發 scope-scanner↔scope-verifier 執行 B4（影響範圍盤點）
6. 驅動 planner agent 執行 C（任務框架確認、逐項細化）
7. C3 確認後自動觸發 plan-reviewer
8. plan-reviewer 通過後，提示使用者可執行 `execute`

**References（agent 手冊）：**

| 檔案 | 用途 | 對應步驟 | 載入時機 |
|------|------|---------|---------|
| `plan-template.md` | 規劃文件起始樣板（三區塊 + 任務框架空格） | B1 | B1 執行時 |
| `planning-guide.md` | planner 完整操作手冊：輸入解析、B1 骨架建立 + 澄清規則、B3 提案格式、文件更新原則 | A1, B1, B3 | planner agent 啟動時 |
| `scope-scanner-guide.md` | scope-scanner 操作手冊：codebase 勘查策略、異動/影響範圍列舉格式、與 verifier 互動協議 | B2, B4 | scope-scanner agent 啟動時 |
| `scope-verifier-guide.md` | scope-verifier 驗證規則：完整性檢查標準、回饋格式、收斂判斷（最多 3 輪）、上報條件 | B2, B4 | scope-verifier agent 啟動時 |
| `task-breakdown-guide.md` | 任務拆解規範：框架確認標準、C2 填充格式、測試旗標定義、凍結條件 | C1, C2, C3 | C 階段進入時 |
| `plan-reviewer-guide.md` | plan-reviewer 審核流程：完整性檢查清單、嚴重度判斷規則、退回路徑決策 | plan-reviewer | plan-reviewer agent 啟動時 |

---

### `execute`

**Frontmatter 草稿：**

```yaml
---
name: execute
description: >-
  Implements code changes task-by-task using sub-agents. If a frozen plan
  document exists, proceeds directly to implementation. If not, asks the user
  whether to plan first (redirects to `plan` skill) or implement immediately
  based on agent's current understanding. If called with no context, asks the
  user what to implement before proceeding.

  Triggers on: "開始執行", "開始實作", "幫我實作", "execute", "implement",
  "run plan", "直接做", direct feature/bug descriptions implying
  implementation intent.

  Do NOT trigger for planning-only requests — use `plan` instead.
  Do NOT trigger for code review requests — use `conventional-review` instead.
---
```

**獨立行為：**
- 有規劃文件（已凍結）→ 直接進入 D
- 有需求但無規劃文件 → 詢問使用者：「是否需要先完整規劃？」
  - 需要 → 終止 execute，提示使用者改用 `plan` skill
  - 不需要 → agent 根據需求說明自身的理解與實作方向，使用者確認後直接實作
- 空呼叫（無任何說明）→ 詢問使用者「你想修改什麼？」後繼續

**職責：**
1. 判斷是否有凍結的規劃文件：有 → 直接執行 D；無 → 先執行輕量規劃
2. 逐一派發 task-executor（D1）→ task-reviewer（D2）→ D3 測試驗證
3. 管理循環：小問題原地修正、大問題退回 C2
4. 全部任務完成後，提示使用者可執行 `conventional-review`

**References（agent 手冊）：**

| 檔案 | 用途 | 對應步驟 | 載入時機 |
|------|------|---------|---------|
| `execution-guide.md` | task-executor 執行規則：任務讀取方式、修改範圍限制、完成定義；**含 D3**：測試旗標判讀、既有測試執行策略、補充測試格式 | D1, D3 | task-executor 啟動時 |
| `review-guide.md` | task-reviewer 審查流程：spec 符合性檢查項目、程式碼品質判斷基準、問題分級定義（輕微/重大） | D2 | task-reviewer 啟動時 |

---

### `conventional-review`

**Frontmatter 草稿：**

```yaml
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
```

**獨立行為：**
- 有明確範圍（git diff、branch、commit、指定檔案）→ 直接審查
- 範圍不明確 → 詢問使用者「要審查哪些異動？」，確認後才執行，不提前展開審查

**職責：**
1. 派發 conventional-reviewer agent，依 checklist 全面審查所有異動
2. 呈現分級審查結果（輕微／重大）
3. 管理循環：輕微原地修正重審、重大退回 execute

**References（agent 手冊）：**

| 檔案 | 用途 | 對應步驟 | 載入時機 |
|------|------|---------|---------|
| `conventional-review-guide.md` | conventional-reviewer 審查流程：如何逐項執行審查、問題呈現格式、循環判斷規則 | E1, E2 | conventional-reviewer 啟動時 |
| `conventional-review-checklist.md` | 91APP code review 審查清單：各項檢查規則、問題分級標準（輕微／重大） | E1 | conventional-reviewer 對照用 |

---

## 七、已確認決策

| 項目 | 決策 |
|------|------|
| Plugin 名稱 | `feature-flow` |
| VSTS 讀取範圍 | Work Item 本文 + Acceptance Criteria |
| VSTS 寫回 | ❌ 只讀，不回寫 |
| Code Review checklist | `skills/conventional-review/references/conventional-review-checklist.md` |
| 與現有 plugins | 完全獨立 |
| 測試強制性 | 由 C2 測試旗標控制，非強制，屬 D3 子步驟 |
| 規劃文件策略 | 單一漸進式文件，B+C 共同維護，由骨架到具體 |
| 規劃文件儲存路徑 | `{專案根目錄}/docs/feature-flow/{xxx}-plan.md`，xxx 由 agent 依需求命名 |
| execute 無規劃文件時 | 詢問是否先規劃：是 → 轉 plan skill；否 → agent 說明理解後直接實作 |
| Skill 清單 | plan / execute / conventional-review |
| Agent 清單 | planner / scope-scanner / scope-verifier / plan-reviewer / task-executor / task-reviewer / conventional-reviewer |

---

## 八、待細化項目（下一步）

- [ ] `execute` 職責欄：更新為新的「詢問再決定」行為（對應七的決策）
- [ ] 各 agent 的 `.agent.md` 內容規格
- [ ] `conventional-review-checklist.md` 內容（91APP 審查規範條目）
- [ ] `main-flow.md` 正式內容（依二、主流程 + 步驟定位表撰寫）
- [ ] `plan-template.md` 規劃文件樣板結構

---

## 九、漸進式展開進度

```
Phase 0: 釐清範疇與核心流程              ✅ 完成
Phase 1: 確認主流程 + 循環點             ✅ 完成
Phase 2: 確認 Agent 職責與命名           ✅ 完成
Phase 3: 確認 Skill 清單與職責           ✅ 完成
Phase 4: references/ 慣例 + 目錄結構     ✅ 完成
Phase 5: 各 skill frontmatter 草稿       ✅ 完成（待最終調整）
Phase 6: 各 skill SKILL.md body 撰寫     ← 下一步
Phase 7: 各 agent .agent.md 撰寫
Phase 8: references/ 檔案內容撰寫
         (main-flow.md, plan-template.md, planning-guide.md,
          scope-scanner-guide.md, scope-verifier-guide.md,
          task-breakdown-guide.md, plan-reviewer-guide.md,
          execution-guide.md, review-guide.md,
          conventional-review-guide.md, conventional-review-checklist.md)
Phase 9: plugin.json + 更新兩個 marketplace.json 並驗證
```
