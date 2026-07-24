# Plugin 優化調整計劃（SKILL 瘦身、去重複、用語修正）

> 狀態：**待執行**（Phase 1 起依序進行）
> 來源：2026-07-24 plugin 全面評估（運作流程 / 架構 / SKILL 撰寫 / 檔案長度）
> 原則：每個 Phase 一個分支、只 commit 不 push、合併需使用者確認、版本號僅在確認合回 master 時更新（依 CLAUDE.md）。
> **Phase 1–4 為文件／指令內容調整，不得改變任何執行語意**（唯一例外：P0-1 是 bug 修正，語意「修正為原設計意圖」）。執行中若發現必須動到語意，停下來回報，不要自行決定。

---

## 問題清單總表（依嚴重度排序）

| # | 嚴重度 | 問題 | 位置 | 影響 |
|---|--------|------|------|------|
| P0-1 | **高（bug）** | `/adjust` hard 路徑用相對路徑 `cp -f ... .get-it-done/...`、`rm -rf .get-it-done/workspace`，未加 `$GID_BASE` 前綴；多目標模式（cwd=repo root）會把模板重置到 repo root 而非目標 worktree | `skills/adjust/SKILL.md` Step 3b（約 L192–215） | 錯誤位置的狀態重置；污染 repo root |
| P0-2 | **高（過時用語）** | `/plan` 舊名殘留（已改名 `/blueprint`） | `skills/review/SKILL.md` L15 + frontmatter description | 觸發混淆、指向不存在的 skill |
| P0-3 | **高（過時用語）** | 「worktree 的 `.get-it-done/` 是 **repo-root** `.get-it-done/` 的 symlink」— 多目標模式下應為 **goal worktree**（`$GID_BASE`）的 `.get-it-done/` | `agents/executor.md` L76、`agents/validator.md` L48 | agent 定義與實際架構矛盾（目前靠 spawn prompt 蓋過，屬未爆彈） |
| P1-1 | **高（context）** | `continue/SKILL.md` 693 行，每次 `/continue` 全量載入且自我迴圈長駐 context；其中約 200 行 manual fallback 偽代碼與 `gid.py` 邏輯完全重複（雙實作必然漂移） | `skills/continue/SKILL.md` | context 塞爆、後期 batch 指令遵循品質下降、雙實作漂移 |
| P1-2 | **高（重複+漂移）** | 同一規則多處重複：GID_BASE 解析 ×4（continue/objective/adjust/blueprint）、bootstrap 雙平台區塊 ×3、worktree/git 隔離模型 ×4（main-flow / state.md / platform-adapter §9.5 / continue）、goal 重置邏輯 ×2 種寫法（objective 用 `bootstrap.py reset`、adjust 用手寫 cp） | 多檔案 | 維護成本高；P0-1/P0-3 就是已發生的漂移實例 |
| P2-1 | 中 | 修訂史殘留混入指令：`[FIX N2]`、`[FIX #3]`、`(Fix A2)`、`unchanged from v1` 等 changelog 式標記 | `skills/continue/SKILL.md`、`agents/planner.md` 等 | 對執行模型是純噪音，佔 context |
| P2-2 | 中 | 未定義內部術語：「Stage 3 / Stage 4 / Stage 5+」全 plugin 無定義出處；`PR-012`/`PR-013` 等規則編號引用未附出處 | `continue/SKILL.md`、`templates/.get-it-done/state.md`、`agents/*.md` | 冷啟動的 dispatcher / 維護者無從查證，理解成本高 |
| P2-3 | 低 | skill 撰寫語言混用：continue/objective/blueprint/review 英文、adjust 幾乎全中文 | `skills/adjust/SKILL.md` | 維護心智切換（user-facing 訊息用繁中是刻意設計，保留） |
| P3-1 | 中 | `gid.py` 1290 行、含 git 變更操作（merge / reset --soft / worktree 增刪），無任何測試 | `skills/continue/scripts/gid.py` | 承擔「去 LLM 風險」角色的腳本自身是最大未驗證面 |

---

## 分階段執行計劃

### Phase 1 — P0 修正：bug + 過時用語（小、快、先行）

**分支**：`fix/p0-stale-terms-and-adjust-base-paths`

1. **P0-1** `skills/adjust/SKILL.md` Step 3b：將手寫 `cp`/`rm`/`find` 重置區塊改為與 `/objective` Step 4 相同的 `bootstrap.py reset --base "${GID_BASE:-.}"` 呼叫（同時消除 P1-2 的「重置邏輯 ×2 種寫法」）。
   - 前置確認：閱讀 `skills/objective/scripts/bootstrap.py` 的 `reset` 子命令，確認其涵蓋 adjust 現有清單（task_queue / metrics / research_requests / findings RQ-* / workspace / prd / plan_audit）；有缺項則以 `--base` 前綴的顯式指令補齊，不擅自擴充 bootstrap.py 行為。
2. **P0-2** `skills/review/SKILL.md`：`/plan` → `/blueprint`（body L15 與 frontmatter description 兩處）。
3. **P0-3** `agents/executor.md` L76、`agents/validator.md` L48：改為「symlink 指向 **goal worktree**（`$GID_BASE`）的 `.get-it-done/`；back-compat 單目標模式下即 repo root」。
4. **全庫過時用語掃描**（防止還有沒抓到的）：grep 以下字串並逐一判定修正／保留：
   - `/plan`（非 `/blueprint`、非 `docs/plans` 路徑者）
   - `repo-root .get-it-done`、`repo_root/.get-it-done`（逐一確認語境是否該改為 goal worktree）
   - `workspace/current`（v1 遺留路徑，executor.md 有提及，確認說法仍正確）
   - `feature-flow`（舊 plugin 名，若殘留）

**驗收**：上述 grep 全數清零或逐條標記「確認保留」；`/adjust` hard 路徑所有寫入目標都帶 `$GID_BASE`（或經由 `--base`）。

---

### Phase 2 — `/continue` SKILL 瘦身（progressive disclosure）

**分支**：`feature/slim-continue-skill`
**目標**：`skills/continue/SKILL.md` 從 693 行降至 **≤350 行**，語意零變更。

拆出三個 reference（新增 `skills/continue/references/`）：

1. **`references/manual-fallback.md`** — 移入與 `gid.py` 重複的手動程序：
   - Step 3 truncate 手動程序、Step 4 dag-check 手動程序、Step 5 pool 手動選批程序（最大塊，約 130 行）、Step 6 batch-id 手動遞增。
   - SKILL.md 各步驟只留：script 呼叫 + 「script 失敗（exit 2 / error JSON / Python 不可用）時，Read `references/manual-fallback.md` 對應章節並記 `[GID_FALLBACK]`」。
2. **`references/report-and-reflect.md`** — 移入 `report_and_reflect()` 全文（含 degraded sweep、consolidate-final、reflector gate）。SKILL.md 留一段觸發說明：「phase 進入 REPORTING 時 Read 此檔並執行」。
3. **`references/plan-audit-gate.md`** — 移入 plan audit gate 全文。SKILL.md Step 9 planner-return 處留觸發句。
4. **平台備註歸位**：Step 0 / Step 7 的 Copilot 專屬說明（delegation 細節、PowerShell 區塊）縮為一句指向 `references/platform-adapter.md` §4 / §7（該檔已有完整內容，先確認無缺再刪）。

**護欄**：
- 搬移是「剪下貼上 + 加載入指令」，不改寫內容（改寫留給 Phase 4）。
- 搬移後逐段 diff 確認：SKILL.md 刪除的每一行都能在新 reference 找到對應。
- 確認 `objective/SKILL.md`、`adjust/SKILL.md`、`state.md` 模板中指向 `skills/continue/SKILL.md` 的描述仍然成立。

**驗收**：`wc -l` ≤ 350；三個 reference 檔各自完整可獨立閱讀；SKILL.md 每個外移點都有明確的「何時 Read 哪個檔」指令。

---

### Phase 3 — 跨檔案去重：建立單一事實來源（single source of truth）

**分支**：`feature/dedupe-shared-rules`
**原則**：每條規則指定一個 canonical 位置放全文，其他位置只留 ≤5 行摘要 + 明確的 Read 指令（skill 之間不能假設對方已載入，必須顯式指示閱讀）。

| 規則 | Canonical 位置 | 其他位置處理 |
|------|----------------|--------------|
| GID_BASE 解析程序（resolve，continue/adjust 共用） | 新檔 `references/gid-base.md`（含 resolve 與 create 兩節） | continue Step「Resolving GID_BASE」、adjust Step 0a → 摘要 + Read 指令 |
| Goal worktree 建立程序（create，objective/blueprint 共用） | 同上 `references/gid-base.md` | objective Step 0a、blueprint Handoff 第 3 點 → 摘要 + Read 指令 |
| Bootstrap 雙平台指令（bash + PowerShell） | `references/platform-adapter.md` §7（已存在，補上 `bootstrap.py` 呼叫範例） | objective / adjust / continue Step 0 → 只留 macOS/Linux 一行 + 「Windows/Copilot 見 platform-adapter §7」 |
| Worktree / git 隔離模型（完整規格） | `templates/.get-it-done/state.md`「Git isolation」節（agent 與 dispatcher 都會讀的契約檔） | `references/main-flow.md` → ≤10 行摘要 + 指向；`platform-adapter.md` §9.5 → 只留操作面（怎麼呼叫 gid.py、OS 差異），模型描述指向 state.md；continue SKILL → 只留 dispatcher 可執行步驟 |
| Goal 重置邏輯 | `bootstrap.py reset`（Phase 1 已統一） | — |

**護欄**：canonical 全文與被刪處逐段 diff，確保沒有任何一句規則在合併過程中遺失；四處描述若有措辭衝突（很可能有——這正是漂移），以「最新設計」為準並在 PR 描述列出取捨。

**驗收**：grep 各規則的關鍵句（如 symlink 描述、`gid/goal-<slug>`、robocopy 區塊）在全 repo 只出現於 canonical 位置 + 摘要引用。

---

### Phase 4 — 撰寫噪音與用語清理

**分支**：`feature/wording-cleanup`

1. **移除 changelog 式標記**：`[FIX N2]`、`[FIX #3]`、`(Fix A2)`、`unchanged from v1`、其他 v1/v2 歷史對照（保留 `schema_version: 2` 這類有執行語意者）。修訂脈絡屬 git history，不屬 prompt。
2. **「Stage N」處理**：全數改為描述性文字（如「Stage 3: heterogeneous batches」→「heterogeneous batches」；「Stage 5+」的未來式標記直接改為現在式陳述或刪除）。涉及 `continue/SKILL.md`（5 處）、`templates/.get-it-done/state.md`、`agents/executor.md`、`agents/reflector.md`、`agents/validator.md`。
3. **規則編號引用補出處**：`PR-009` / `PR-012` / `PR-013` / `PR-019` / `RR-005` 等引用處：
   - 先驗證每個被引用的編號確實存在於 `templates/team_learnings/agent_rules/*.md`；不存在者為 dangling reference，修正或刪除。
   - 存在者在首次引用處補 `（見 agent_rules/planner.md）` 式括注。
4. **語言統一（決策點）**：建議 skill/agent 本體統一英文（現況多數）、user-facing 訊息維持繁中。`adjust/SKILL.md` 是唯一中文本體 → **翻譯為英文**（保留所有繁中 user-facing 訊息字串原樣）。
   - ⚠️ 此項改動面較大且純風格，執行前再與使用者確認一次是否要做；使用者若認為不值得，跳過此項不影響其他項。

**驗收**：grep `[FIX`、`Fix A`、`unchanged from v1`、`Stage 3`…`Stage 5` 清零；所有規則編號引用可回溯。

---

### Phase 5 — `gid.py` 測試

**分支**：`feature/gid-tests`
**原則**：與 gid.py 相同的 stdlib-only 哲學 → 用 `unittest`，不引入 pytest 等相依。
**⚠️ 順序約束**：Phase 6 會讓 gid.py 成為 `.get-it-done/*.md` 的 writer，因此 **Phase 5 必須在 Phase 6 之前完成**（至少純邏輯測試部分），作為寫入化前的測試安全網。

1. `plugins/get-it-done/skills/continue/scripts/tests/test_gid.py`（或 `tests/` 於 plugin 根，執行時定案）：
   - **純邏輯單元測試（優先）**：`parse_state`、`parse_task_queue`（含 `## Milestones` 節、in_milestones flag 邊界——repo 已有此類 regression 前科，見 commit 16db9d5）、`dag_violations`（self-ref / orphan / cycle / touches overlap）、`milestone_status` 五態推導（含單任務 milestone 自動 validated）、`cmd_pool` 選批（P1→P4 優先序、Touches 碰撞 defer、max_parallel 上限）、batch-id 遞增、truncate 歸檔。
   - **git 整合測試（次優先）**：以 `tempfile` 建臨時 git repo 跑 `goal-worktree-init` → `worktree-add` → `worktree-commit-wip` → `worktree-merge`（含 conflict 路徑）→ `consolidate-milestone` → `goal-reset`；驗證 merge 冲突回報 `{ok:false, reason:"conflict"}`、`worktree-gc` 不誤刪 goal worktree。
2. 提供一行執行方式（`python3 -m unittest discover ...`）寫入測試檔 docstring 與本計劃。

**驗收**：純邏輯測試全綠；git 整合測試在 macOS 全綠（Windows junction 路徑標注為未覆蓋，留待有環境時補）。

---

### Phase 6 — Dispatcher 寫入腳本化 + state.md 拆檔（架構變更，經使用者確認 2026-07-24）

**分支**：`feature/scripted-state-writes`
**性質**：⚠️ 與 Phase 1–4 不同，這是**語意層級的架構變更** — gid.py 從「對 `.get-it-done/*.md` read-only」改為 dispatcher 的持久化執行器。動機：LLM 每 tick 的 Read/Edit 大檔（task_queue.md、state.md）是 context 負擔的大宗；Step 6/9/10 的寫入規則已是完全明文化的決策表，無自由裁量，可確定性化。單一寫者原則不變（寫者從「LLM 的 Edit」變成「dispatcher 序列呼叫的腳本」）。
**前置**：Phase 5 純邏輯測試完成（測試安全網）；Phase 2 完成（SKILL 結構已穩定，本 phase 進一步縮減 Step 6/9/10）。

1. **gid.py 新增寫入子命令**（皆吃 JSON/YAML 參數、回 `{ok:...}` 回執、失敗 exit 2 讓 dispatcher 走 manual fallback）：
   - `claim-batch` — Step 6 全部原子寫入：state.md YAML pre-write（batch_id/active_agents/RUNNING）+ task_queue claims + RQ claims，一次完成。
   - `persist-return` — Step 9 決策表：輸入一份 agent-return YAML（+ role/mode/task_id），執行對應的 task_queue 更新、validation_log append（含 dedup）、progress_log 事件行、worktree git 呼叫的**指示回傳**（git 操作仍由既有子命令執行，persist-return 回傳「接下來該呼叫哪個 git 子命令」清單，由 dispatcher 依序執行——避免單一命令攬太多副作用）。
   - `close-batch` — Step 10：state.md YAML close + `## Batch` history append。
   - `log-append` — 泛用 progress_log/validation_log 追加（含 truncate-logs 既有邏輯整合）。
2. **SKILL.md 讀取面收斂**：明文規定非 fallback 情境**禁止**直接 Read `state.md` / `task_queue.md` / `research_requests.md` — 一律吃 `gid.py state / pool / rqs` 的 JSON。manual fallback reference（Phase 2 產物）保留為 Python 不可用時的退路。
3. **state.md 拆檔**：
   - `state.md` 只留機器狀態：YAML block + 精簡 batch history（或評估直接移除 history — dispatcher 從不讀它；若移除，crash recovery 依據不變，僅少掉人類審計視角，需在 PR 說明取捨）。
   - 狀態機說明、phase 定義、transition rules、agent-return 契約 → 移至 `templates/.get-it-done/STATE_SPEC.md`（或 plugin `references/state-spec.md`，執行時定案——需確認 sub-agent 讀契約的路徑並同步更新 executor/validator/planner 的 Inputs 清單與 spawn prompt 中的引用）。
4. **Hook 機制**：本 phase **不做**（Copilot 無 hooks、脆弱、節省有限）；留作日後可選加速層。
5. 相關 SKILL 段落改寫：Step 6/9/10 縮為命令呼叫 + fallback 指引；`/objective`、`/adjust` 的 state.md YAML 重寫段落同步改用腳本（`adjust` Step 1 的 RUNNING 回滾邏輯也是純機械，納入腳本化範圍）。

**驗收**：一個完整 goal 週期（PLANNING→EXECUTING→REPORTING→COMPLETE，含 rework 與 crash recovery 模擬）中，dispatcher 對 `.get-it-done/*.md` 零直接 Read/Edit（fallback 情境除外）；Phase 5 測試擴充覆蓋新子命令後全綠；`/continue` SKILL 行數進一步下降（目標 ≤250）。

---

## 待辦清單（執行時逐項勾銷）

- [x] **Phase 1**：P0-1 adjust 路徑 bug（統一走 `bootstrap.py reset`）
- [x] **Phase 1**：P0-2 `/plan` → `/blueprint`（review SKILL 兩處）
- [x] **Phase 1**：P0-3 executor/validator symlink 描述修正
- [x] **Phase 1**：全庫過時用語 grep 掃描與清理
- [x] **Phase 2**：manual fallback 外移至 `references/manual-fallback.md`
- [x] **Phase 2**：`report_and_reflect()` 外移
- [x] **Phase 2**：plan audit gate 外移
- [x] **Phase 2**：Copilot 平台備註歸位 platform-adapter
- [x] **Phase 2**：確認 continue SKILL 外移內容零遺失（sub-agent 交叉驗證通過，逐行比對零缺漏）。⚠️ 行數 693→478（-31%），未達 ≤350 目標 — 該數字與計劃本身條列的搬移項目估算（693-228≈465）本就不符，屬計劃原始估計偏樂觀；未在 Phase 2 範圍內額外搬移 Step 2 crash recovery / Step 9 persist 決策表以硬湊行數，因兩者屬 dispatcher 專有邏輯（非與 gid.py 重複的手動程序），移動需等 Phase 6 腳本化後才有語意基礎。已回報使用者。
- [x] **Phase 3**：`references/gid-base.md` 建立 + 四處引用改寫（continue/adjust 走 Resolve，objective/blueprint 走 Create）
- [x] **Phase 3**：bootstrap 雙平台區塊歸位 platform-adapter §7（continue/adjust/objective 三處 + blueprint 的 task-breakdown-guide.md 共四處收斂）。⚠️ **意外發現並修正一個 P0 級 bug**：objective/SKILL.md 與 task-breakdown-guide.md 的 Windows PowerShell 區塊原本寫死 `--base "."`，未讀 `$env:GID_BASE`（adjust 的對應區塊原本是對的）——多目標模式下 Windows Copilot 執行 `/objective` 或 `/blueprint` 交接會把 bootstrap 寫到 repo root 而非目標 worktree，與 Phase 1 的 P0-1 同一類型。已在使用者確認後隨本 phase 一併修正（canonical 版本現在正確讀取 `$env:GID_BASE`）。
- [x] **Phase 3**：worktree 模型 canonical 化（state.md 為準，其餘摘要化；main-flow.md 與 platform-adapter §9.5 均已縮為摘要 + 指向 state.md「Git isolation」）
- [x] **Phase 3**：關鍵句 grep 驗證單一來源（sub-agent 交叉驗證通過；並額外抓到 task-breakdown-guide.md 殘留的第四份 bootstrap 副本，已一併收斂修正）
- [x] **Phase 4**：`[FIX ...]` / v1 對照標記清除（continue/SKILL.md、manual-fallback.md、agents/planner.md）
- [x] **Phase 4**：「Stage N」術語全數改寫（README + 5 個 agents/*.md + 4 個 templates/*.md + 2 個 agent_rules/*.md + continue/SKILL.md 系列，共 ~35 處；blueprint 的 `## Stage: <name>` pipeline 命名法為不同語意，予以保留）
- [x] **Phase 4**：規則編號引用驗證 + 補出處（PR-009/012/013/019、RR-005 全數比對 agent_rules 定義，無 dangling reference）
- [x] **Phase 4**：adjust SKILL 語言統一（使用者確認後翻譯為英文；user-facing 繁中字串逐一比對保留）。sub-agent 交叉驗證：Stage/標記清除為純刪除、無語意變更；adjust 翻譯後決策樹/YAML/bash 完全一致，9 條 user-facing 字串逐字保留。
- [x] **Phase 5**：gid.py 純邏輯單元測試（parse_state、parse_task_queue 含 in_milestones 邊界回歸測試對應 commit 16db9d5、dag_violations 全分支、milestone_status 五態、cmd_pool P1-P4 優先序+Touches 碰撞+max_parallel 上限+batch 上限、batch-id、truncate-logs）
- [x] **Phase 5**：gid.py git 整合測試（tempfile repo：goal-worktree-init→worktree-add→worktree-commit-wip→worktree-merge 含衝突路徑驗證 `{ok:false, reason:"conflict"}`→consolidate-milestone→goal-reset；worktree-gc 不誤刪 goal worktree）。共 47 個測試全綠（macOS，git 2.x），執行方式：`python3 -m unittest discover -s plugins/get-it-done/skills/continue/scripts/tests -p "test_*.py" -v`
- [ ] **Phase 6**：gid.py 寫入子命令（claim-batch / persist-return / close-batch / log-append）
- [ ] **Phase 6**：SKILL 讀取面收斂（禁止直接 Read state 檔，改吃 JSON）
- [ ] **Phase 6**：state.md 拆檔（狀態 vs 說明文件分離）+ 引用同步更新
- [ ] **Phase 6**：objective / adjust 的狀態寫入段落同步腳本化
- [ ] **Phase 6**：Phase 5 測試擴充覆蓋新子命令

## 執行順序與依賴

```
Phase 1（P0，獨立）──┐
                     ├─→ Phase 2（continue 瘦身）─→ Phase 3（去重複）─→ Phase 4（用語清理）
Phase 5（測試）──────┘                    │
        │                                 │
        └────────（5 完成後）──→ Phase 6（寫入腳本化 + state.md 拆檔）
```

- Phase 2 必須在 Phase 3 之前：瘦身時會順手移走 continue 內的重複平台備註，先瘦身可減少 Phase 3 的改動面。
- Phase 4 放最後（就 1–4 而言）：改寫措辭要在內容位置都穩定之後做，避免同一段文字改兩次。
- Phase 5 可隨時插入（不碰 markdown 檔），但**必須在 Phase 6 之前完成純邏輯測試**。
- Phase 6 依賴 Phase 2（SKILL 結構穩定）與 Phase 5（測試安全網）；Phase 3/4 與 Phase 6 若有段落重疊，以先合併者為基準 rebase。
- 每個 Phase 完成後 commit 在該 Phase 分支，**等使用者確認再合併**；合併目標與版本號依 CLAUDE.md 流程。
