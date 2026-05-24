# get-it-done — 自主 5-Agent 團隊 Plugin

一個 Claude Code plugin，封裝了由 Planner、Analyst、Executor、Validator、Reflector 組成的 agent 團隊，以及一支極簡的 **`/continue`** 派發器來推進它們。

## 狀態機（v2 — batch-aware dispatcher）

**（注：本文所述所有並行化特性均為 v2 架構中的活躍功能；無需再區分 Stage 標籤。）**

```
主流程：
  PLANNING → (ANALYZING — 平行 N analysts)? → PLANNING → EXECUTING → REPORTING → COMPLETE

  EXECUTING 階段由 dispatcher 每個 inner tick 計算可動工項池：
    - executed tasks → 派 validator
    - needs_rework → 重派 executor
    - pending tasks (deps 全 done) → 派 executor
    - 某 milestone 全 done → 派 milestone validator (Stage 3+)
  一個 batch 內可同時包含多個異質 sub-agents（最多 N 個）。

收尾（dispatcher 主導）：
  REPORTING 由 dispatcher 寫 [GOAL_COMPLETE] 摘要、把 phase 設為 COMPLETE，
  並另起獨立 reflector sub-agent 做事後反思（不影響 COMPLETE）。
```

**Stage 5（目前 — A/B Learning Architecture Complete）**：
- **EXECUTING**：每 batch ≤5、**異質**（per-task validators + milestone validators + rework executors + new executors 可同 batch）。優先序：drain per-task validators → 關 milestone validators → reworks → 新 pendings。**Milestone 閘**：`M_k` 的 task 只在每個 `M_1..M_{k-1}` 都 derived `validated` 後才能 claim。
- **ANALYZING**：每 batch ≤5 analysts，每個對應一個獨立的 RQ-X。PR-012 保證 RQ 之間相互獨立，可安全平行；每個 analyst 寫自己的 `team/findings/RQ-X.md`，無寫入衝突。
- **PLANNING**：N=1（planner 是 singleton role）。

Milestone status 由 dispatcher 每 tick 從 per-task statuses + Claimed_by + 最新 Validation Results **推導**，無持久化的 `Status:` 欄位，避免 stale-failed 問題。

派發器是 v2 的 **唯一 shared-state writer**：sub-agents 不直接寫 `state.md` / `task_queue.md` / log 檔，而是透過 `---agent-return---` 結構化 YAML 區塊把結果交回。Dispatcher 解析後 atomic 持久化，並在 batch 結束時 append 一個 `## Batch <id>` 區塊到 `state.md` 底部作為歷史紀錄。Reflector 不在 relay 內、不發 agent-return（其輸出就是學習檔的寫入本身）。

### Crash recovery
`status == RUNNING AND batch_ended_at == null` 即視為崩潰。Dispatcher 在進場時依據 phase 和 claimed set 執行三個 sub-cases：

- **Sub-case 0** (PLANNING singleton): 若 `phase == PLANNING` 且超逾 5 分鐘無回應，視為 planner crash；清空 phase 狀態、刪除半寫產出、重新啟動。
- **Sub-case A** (sub-agent batch interrupted): 若 `Claimed_by != null` 的 task/RQ/milestone 存在，重派所有已 claim 項目（scratch dir 以 task_id 為鍵可安全覆寫、`validation_log` 以 `(task_id, attempt_no)` dedupe、RQ 仍 open 可重覆寫）。
- **Sub-case B** (batch close interrupted): 若 claimed set 為空但 batch_ended_at 未設，代表工作已 persist 但 batch envelope 未閉；清理 stale 標記、關閉 batch、進行下個 tick。

## 元件清單

| 類型 | 名稱 | 用途 |
|---|---|---|
| Command | `/objective <目標>` | 重置每次目標的相關狀態，清空 `team/workspace/`、刪除舊 PRD 與舊 RQ-* findings，初始化 v2 schema，啟動第一個派發器循環 |
| Command | `/adjust <修訂訊息>` | 階段性開發中修訂目標 — **soft** 在 `goal.md` 附加澄清/約束、保留 task_queue/prd/findings/workspace；**hard** 重寫 Goal/Success 並重置 planner artifacts。兩者皆保留 `progress_log.md`、`validation_log.md`、`team/context/`、A-side learnings。若 dispatcher 為 RUNNING 會自動先暫停為 AWAITING_HUMAN |
| Command | `/continue` | 持續推進派發器迴圈直到目標完成或遇到 blocker。在 `/objective` 之後使用（跨 session 接續，或 AWAITING_HUMAN 解除後重啟） |
| Agent | `planner` | 將目標拆解成任務 DAG（含 Dependencies + Milestone）+ 驗收標準；必要時產出 PRD；可一次列出 N 個獨立 research requests |
| Agent | `analyst` | 由 dispatcher 指派單一 `RQ-X`，寫對應 `team/findings/RQ-X.md` |
| Agent | `executor` | 由 dispatcher 指派單一 `T-XXX`，產出寫入 `team/workspace/exec-T-XXX/` |
| Agent | `validator` | 由 dispatcher 指派單一 `T-XXX`（或 milestone `M-X`，Stage 3+），輸出 verdict + `escalate_to_blocked` |
| Agent | `reflector` | **事後反思**（不在主 relay）。Dispatcher 在 REPORTING 完成後另起 sub-agent，將學習分類為 A（跨專案）或 B（單一專案）寫回對應位置 |

## 安裝

```bash
# 從 repo root
claude plugin install ./plugins/get-it-done --scope project

# 或從任何位置
claude plugin install /absolute/path/to/plugins/get-it-done --scope user

# 驗證安裝
claude plugin list
claude plugin details get-it-done
```

## 三個儲存位置（核心心智模型）

| 位置 | 解析路徑 | 範圍 | 可寫嗎 | 存什麼 |
|---|---|---|---|---|
| **Plugin 安裝目錄** `${CLAUDE_PLUGIN_ROOT}` | `~/.claude/plugins/cache/get-it-done@.../` | 單一使用者，所有專案共用 | **唯讀**（只有範本） | Plugin 原始碼：agents、skills、起手範本 |
| **A — 跨專案學習** `${CLAUDE_PLUGIN_DATA}/team_learnings/` | `~/.claude/plugins/data/get-it-done-<scope>/team_learnings/` | 單一使用者，跨專案共用，撐過 plugin 更新 | 可寫 | agent 團隊本身可重複套用到任何專案的自我改善 |
| **B — 單一專案狀態 + 學習** `team/`（= `<project>/team/`） | 該使用者當前專案目錄，跟著 git 走 | 單一專案，可與隊友共享 | 可寫 | 目標 / PRD / 任務 / 日誌 + 專案專屬知識（領域、技術棧、程式碼地圖、決策、利害關係人） |

## A 側 — 跨專案 agent 團隊學習

位於 `${CLAUDE_PLUGIN_DATA}/team_learnings/`，由 `templates/team_learnings/` 初始化：

| 檔案 | 內容 |
|---|---|
| `patterns.md` | 跨循環觀察到的模式。一個檔案同時容納兩種生命週期狀態：**provisional**（1-2 次觀察）與 **promoted**（3+ 次觀察、已穩定）。預設帶 P-001, P-002。 |
| `errors.md` | 反覆出現的失敗模式（ERR-XXX），依 8 種 Category enum 分類。 |
| `handoff_lessons.md` | Agent 之間的交棒契約教訓（HL-XXX）——上一棒該留下什麼下一棒才接得住。 |
| `agent_rules/planner.md` | Planner 的累積規則（PR-XXX）。預設帶 PR-001..016（含 v2 DAG 自查、empty deps 即平行槓桿、research 獨立性、source 衝突保護、milestone criteria 等）。 |
| `agent_rules/{analyst,executor,validator,reflector}.md` | 各 agent 的累積規則（AR/ER/VR/RR-XXX）。預設帶 AR-001..005、ER-001..011、VR-001..006、RR-001..008（v2-aware）。 |
| `proposed_changes.md` | Reflector 對 plugin source 本身提出的修改 diff —— 等人類套用後出新版。 |

## B 側 — 單一專案狀態 + 學習

位於 `<project>/team/`，由 `templates/team/` 初始化：

### 每次目標的執行期狀態

| 檔案 | 擁有者 (寫) | 用途 |
|---|---|---|
| `state.md` | **dispatcher** | v2 YAML 區塊（schema_version=2, batch_id, active_agents...）+ `## Batch <id>` 歷史 |
| `goal.md` | `/objective` | 當前商業目標 |
| `prd.md` | planner | Product Requirements Document（目標需要時） |
| `task_queue.md` | **dispatcher**（更新 Status/Claimed/Attempts/Validation Results）+ planner（建立結構） | 任務 DAG |
| `metrics.md` | planner | 驗收標準（每條 criterion 有穩定 ID 如 C1, C2） |
| `research_requests.md` | planner | 每個 RQ-X 一筆，dispatcher 翻 open→fulfilled |
| `findings/RQ-*.md` | analyst（每個 RQ 一個檔） | 研究結果，每 analyst 寫自己的檔 |
| `workspace/exec-<task_id>/` | executor（每 task 一個 scratch dir） | 執行產物 |
| `progress_log.md` | **dispatcher** | 只增執行日誌（自動截斷 400→200） |
| `validation_log.md` | **dispatcher** | 只增的驗證結論，從 validator agent-return 寫入；以 (task_id, attempt_no) dedupe |

### 專案專屬學習（`team/context/`）

| 檔案 | 誰會讀 | 記錄什麼 |
|---|---|---|
| `_meta.md` | 全體 | 專案識別：工作目錄、首見時間、最近一次 cycle、一行描述 |
| `domain_knowledge.md` | Planner、Analyst、Executor | 領域事實（DK-XXX）：這個專案在解什麼問題、給誰用 |
| `tech_stack.md` | Analyst、Executor、Validator | 技術棧選擇與慣例（TS-XXX） |
| `codebase_map.md` | Executor、Validator | 程式碼地標與地雷（CM-XXX） |
| `decisions.md` | 全體 | 已定案的架構選擇（AD-XXX）—— 不要重新辯論 |
| `stakeholder_notes.md` | Planner、Validator | 利害關係人限制與已決定的取捨（SN-XXX） |

## 學習分類規則

Reflector 對每一條新學習問同一個問題：

> 「如果換成一個新的專案（不同領域、不同程式碼）跑同一個 agent 團隊，這條學習還成立嗎？」
>
> - **是** → A 側（跨專案），寫進 `${CLAUDE_PLUGIN_DATA}/team_learnings/`
> - **否** → B 側（專案專屬），寫進 `<project>/team/context/`
> - **不確定** → 預設 B，之後在另一個無關專案再見到就升 A

完整決策矩陣在 `agents/reflector.md` 中。

## Bootstrap 機制

`/objective` 和 `/continue` 都會跑一個防禦性 bootstrap 步驟，用 `rsync --ignore-existing` 把範本鏡像到兩個可寫位置（**只建立缺檔，永遠不覆寫**）：

```bash
# A —— 跨專案學習（單一使用者，所有專案共用）
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team_learnings/" "${CLAUDE_PLUGIN_DATA}/team_learnings/"

# B —— 單一專案狀態 + 學習（只屬於這個專案）
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team/" team/
```

### `/objective` 會覆寫哪些、保留哪些

| 動作 | 檔案 |
|---|---|
| **覆寫**（每次重新從範本複製） | `team/task_queue.md`, `team/metrics.md`, `team/research_requests.md`, `team/findings/_meta.md` |
| **刪除**（若殘留則移除） | `team/prd.md`, `team/findings/RQ-*.md`（前一個目標的研究結果） |
| **整個目錄清空後重建** | `team/workspace/`（每個 executor 的 scratch dir 不殘留） |
| **只重設 YAML 區塊**（v2 schema） | `team/state.md`（Phase / Transition / batch lifecycle / agent-return contract 文件保留） |
| **完全不動** | `team/progress_log.md`, `team/validation_log.md`, `team/context/*`（B 側），所有 `${CLAUDE_PLUGIN_DATA}/team_learnings/`（A 側） |

## Plugin source 編輯（proposed-changes 流程）

Reflector **不能**編輯 `${CLAUDE_PLUGIN_ROOT}`（唯讀，更新會覆寫）。當它判斷 plugin 內 agent 的字面指令本身有錯，會把 diff 寫進 `${CLAUDE_PLUGIN_DATA}/team_learnings/proposed_changes.md`。再由人類（或 plugin 維護者）把改動 fold 回 plugin source repo、發新版。作為當下的緩衝，Reflector 同時會在對應的 `agent_rules/<name>.md`（A 側）新增一條高優先規則，讓問題在新版 plugin 抵達之前先被擋住。

## 快速上手

```bash
# 1. 安裝（project scope，可透過 git 與隊友共享）
claude plugin install ./plugins/get-it-done --scope project

# 2. 設定一個目標
/objective 製作一個有拖放、儲存/載入與 PNG 匯出功能的簡易流程圖編輯器

# 3. 自動推進（持續迴圈直到 COMPLETE 或 AWAITING_HUMAN）
/continue

# 4. 解除 blocker 後、或新 session 接續
/continue

# 5. 檢視狀態
cat team/state.md                                       # 目前 phase + 最後一個 handoff
cat team/progress_log.md                                # 完整執行歷史
cat team/validation_log.md                              # 驗證歷史
cat team/context/domain_knowledge.md                    # 這個專案教給 Reflector 的事
ls "$CLAUDE_PLUGIN_DATA/team_learnings/agent_rules/"    # 跨專案規則
```

## Agent 共通約定 (v2)

- 所有對使用者的 CLI 輸出必須使用繁體中文。
- Agent 可以呼叫 Claude for Chrome 擴充套件處理 web 認證與驗證任務。
- **Sub-agent 不寫 shared state**：state.md / task_queue.md / progress_log.md / validation_log.md 全部由 dispatcher 寫入。Sub-agent 透過 `---agent-return---` YAML 區塊把結果交回，dispatcher 解析後 atomic 持久化。
- **Crash-detection 契約**：dispatcher 在 spawn 前 atomic 寫入 `status: RUNNING`、新 `batch_id`、`active_agents`、`batch_started_at`，並 set 對應 task 的 `Claimed_by`/`Claimed_at`；sub-agents 全回來後寫入 `batch_ended_at`、`status: WAITING`、清 `active_agents`。下次進場若 `status: RUNNING AND batch_ended_at == null` 即偵測為崩潰，重派所有 `Claimed_by != null` 的 task（idempotent）。
- Reflector 不在 relay 中、不發 agent-return；它在 dispatcher 完成 REPORTING 之後被獨立 spawn，輸出就是學習檔本身。
- Reflector RR-005：任何會調整 Validator 行為的規則必須引用 ≥2 個不同的 VAL-XXX 作為證據。

## 目錄結構

```
plugins/get-it-done/
├── .claude-plugin/plugin.json
├── agents/{planner,analyst,executor,validator,reflector}.md
├── skills/
│   ├── objective/SKILL.md
│   ├── adjust/SKILL.md
│   └── continue/SKILL.md
├── templates/
│   ├── README.md                        ← 解釋兩棵 seed tree 的目的地
│   ├── team_learnings/                  ← 種入 ${CLAUDE_PLUGIN_DATA}/team_learnings/（A）
│   │   ├── patterns.md                  (provisional + promoted，預設帶 P-001, P-002)
│   │   ├── errors.md, handoff_lessons.md
│   │   ├── proposed_changes.md
│   │   └── agent_rules/{planner,analyst,executor,validator,reflector}.md
│   └── team/                            ← 種入 <project>/team/（B；不含 prd.md，由 Planner 視需要產生）
│       ├── state.md                     ← v2 schema + Phase/Transition 文件
│       ├── goal.md, task_queue.md, metrics.md
│       ├── research_requests.md         ← planner 寫；analyst 讀
│       ├── findings/_meta.md            ← directory；每 RQ 一個 RQ-X.md（analyst 寫）
│       ├── progress_log.md, validation_log.md
│       └── context/                     ← B 側專案專屬知識
│           ├── _meta.md
│           ├── domain_knowledge.md, tech_stack.md
│           └── codebase_map.md, decisions.md, stakeholder_notes.md
└── README.md
```

注意：`team/workspace/` 不在 plugin templates 內 —— 由 bootstrap 在專案 `team/` 下建立，每個 executor 寫自己的 `team/workspace/exec-<task_id>/` scratch dir。`/objective` 會清空整個 `team/workspace/`。
