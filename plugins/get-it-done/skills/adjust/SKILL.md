---
name: adjust
description: 修訂或具體化既有目標 — soft 為附加澄清/約束（保留 task_queue / prd / findings / workspace），hard 為重寫 Goal/Success（清空 planner artifacts）。兩種模式皆保留 progress_log、validation_log、.get-it-done/context 與 A-side learnings。Usage：/adjust <修訂訊息>。階段性開發中發現方向歪掉或需要更具體規格時使用。
---

You are executing **/adjust**. 這是 user 在階段性開發過程中，發現方向需要修正或需求要更具體化時的入口。對比另外兩個入口：

- `/objective` — 設定全新目標、reset **所有** per-goal artifacts。
- `/adjust` — 修訂目前 active goal、選擇性保留現有 planner artifacts。
- `/continue` — dispatcher 主循環。

`/adjust` 自己不會呼叫 `/continue` — 結束時告訴 user 準備好就執行 `/continue`，讓 planner 用新 goal re-plan。

## Parse the message

抽出 user 訊息中 `/adjust` 之後的內容。若為空，請 user 提供修訂訊息後停止。

## Step 0: Bootstrap（防禦性、idempotent）

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — refusing to read templates from / }"
: "${CLAUDE_PLUGIN_DATA:?CLAUDE_PLUGIN_DATA is not set — refusing to write learnings to / }"

mkdir -p "${CLAUDE_PLUGIN_DATA}/team_learnings/agent_rules"
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team_learnings/" "${CLAUDE_PLUGIN_DATA}/team_learnings/"

mkdir -p .get-it-done/context .get-it-done/findings .get-it-done/workspace
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/.get-it-done/" .get-it-done/
```

若 bootstrap 後 `.get-it-done/state.md` 仍不存在，停止並提示 user 先用 `/objective <goal>` 初始化。

## Step 1: 讀 state 並決定是否需要先暫停

讀取 `.get-it-done/state.md` 頂部 YAML block。依據 `phase` / `status` 處理：

```
IF phase == IDLE OR goal_set == false:
    EXIT — "目前沒有 active goal，無從修訂。請改用 /objective <goal> 設定新目標。"

IF phase == COMPLETE:
    詢問 user：「目標已完成。要重新打開並修訂嗎？這會走 hard 流程：清空 planner artifacts、保留 progress/validation log。」
    若否 → EXIT；若是 → 強制走 hard 模式（跳過 Step 2 的 soft 選項）。

IF status == RUNNING (dispatcher 正在跑或上次被中斷):
    # 重要：/adjust 是同步使用者動作。若 status=RUNNING，代表前一輪 /continue 在
    # spawn 階段崩潰 / 被 context 用盡截斷 / 被中斷。那些 sub-agents 的 return
    # 已經無法被回收（他們的 session 結束了）。所以必須在這裡主動清掉 in-flight
    # 標記，否則 task_queue 會留下永遠不會關閉的 Claimed_by — Step 3 之後 state
    # 會切到 PLANNING/WAITING，下一次 /continue 的 Step 2 不會做 crash recovery
    # （條件是 RUNNING），那些 claimed/validating 的 task 就會卡死。
    paused_batch := state.batch_id
    append "<ISO> [ADJUST_PAUSE_REQUESTED] batch=<paused_batch> — user 透過 /adjust 介入；clearing in-flight claims" to progress_log.md

    # 1. 回滾 task_queue.md：所有 in-flight task 都還原成 pre-claim 狀態。
    FOR each task in task_queue.md WHERE Claimed_by != null:
        IF task.Status == claimed:    set task.Status = pending     ; clear Claimed_by / Claimed_at
        IF task.Status == validating: set task.Status = executed    ; clear Claimed_by / Claimed_at
        (保留 Validation Results、Artifact、Attempts 等已持久化欄位)

    # 2. 回滾 milestone：清掉 mval-* claim（無其他 milestone 狀態要動）。
    FOR each milestone in task_queue.md ## Milestones WHERE Claimed_by != null:
        clear Claimed_by / Claimed_at

    # 3. 回滾 research_requests.md：被 claim 但未完成的 RQ 回到可被重新指派。
    FOR each RQ in research_requests.md WHERE Status == open AND Claimed_by != null:
        clear Claimed_by / Claimed_at

    # 4. 寫 state.md（明示完整 YAML，不要只覆寫部分欄位）：
    rewrite state.md YAML block:
        schema_version: 2
        phase: AWAITING_HUMAN
        status: WAITING
        batch_id: null
        batch_started_at: null
        batch_ended_at: <ISO now>
        active_agents: []
        goal_set: <unchanged, usually true>
        last_updated: <ISO now>

    告知 user：「前一輪 batch <paused_batch> 的 in-flight 標記已清理（claimed→pending、validating→executed）；那些 sub-agent 的結果若有崩潰中遺失將由 planner / 下一輪 executor 重新處理。」
    繼續往下走進入 Step 2（之後 Step 3 會把 phase 從 AWAITING_HUMAN 改為 PLANNING）。

OTHERWISE (status == WAITING, phase ∈ {PLANNING, ANALYZING, EXECUTING, REPORTING, AWAITING_HUMAN}):
    直接進入 Step 2。
```

## Step 2: 決定模式（soft / hard）

讀 `.get-it-done/goal.md`，把現有的 `## Goal` / `## Context & Constraints` / `## Success Definition` 顯示給 user 看。

依據 user 訊息語意決定：

- **明確 pivot / 重寫**（關鍵字：「改成」「換方向」「pivot」「重新做」「目標改為」「另一個目標」）→ 走 hard。
- **明確只是補規格 / 加 constraint**（關鍵字：「另外」「加上」「補充」「限制」「要求」「順便」「另外要求」「請確保」）→ 走 soft。
- **模糊** → 用 `AskUserQuestion` 詢問：

  > 「想要 soft 還是 hard 修訂？soft：在現有 goal.md 附加澄清/約束，保留 task_queue/prd/findings/workspace。hard：重寫 Goal/Success、清空 planner artifacts（同 /objective 的 reset，但保留 progress/validation log 與 context）。」
  >
  > 預設 soft（更安全）。

若 Step 1 已強制 hard（COMPLETE 路徑），直接跳到 Step 3b。

## Step 3a: Soft 路徑

1. **修訂 `.get-it-done/goal.md`**（使用 Edit，保留其他內容）：
   - 在 `## Context & Constraints` 區段尾端 append bullet：`- (Refined <ISO>) <修訂內容摘要>`。原本為 `(none)` 或空 → 取代為新 bullet。
   - 若 user 訊息有提到成功條件變更：在 `## Success Definition` 區段尾端 append `- (Refined <ISO>) <新成功條件>`。
   - 若 `## Refinement History` 區段不存在，在檔案尾端新增：

     ```markdown

     ## Refinement History

     - <ISO>: <user 訊息原文>
     ```

     已存在 → append `- <ISO>: <user 訊息原文>` bullet。

2. **保留** 以下檔案不變：`.get-it-done/task_queue.md`、`.get-it-done/prd.md`、`.get-it-done/research_requests.md`、`.get-it-done/findings/*`、`.get-it-done/workspace/*`、`.get-it-done/metrics.md`。

3. **Rewrite `.get-it-done/state.md` YAML block**（保留 block 以下所有文件 + ## Batch 歷史）：
   ```yaml
   schema_version: 2
   phase: PLANNING
   status: WAITING
   batch_id: null
   batch_started_at: null
   batch_ended_at: null
   active_agents: []
   goal_set: true
   last_updated: <ISO now>
   ```

4. **Append 到 `.get-it-done/progress_log.md`**：
   ```
   <ISO> [GOAL_REFINED] soft — <user 訊息前 100 字>
   ```

5. 跳到 Step 4。

## Step 3b: Hard 路徑

向 user 確認：「即將 hard 替換目標。task_queue.md、prd.md、findings、workspace 將被清空（progress_log、validation_log、context 保留）。確認嗎？」若否 → EXIT。

1. **Overwrite `.get-it-done/goal.md`**（先讀舊檔抽出 prior Refinement History 條目以便保留累積）：
   ```markdown
   # Active Goal

   ## Status
   Active — team is working on this goal (refined via /adjust at <ISO>).

   ## Goal
   <user 訊息中的新 goal 內容>

   ## Context & Constraints
   <若 user 訊息有給；否則 "None specified.">

   ## Success Definition
   <若 user 訊息有給；否則從 goal 推導>

   ## Set By
   Human (via /adjust — hard refinement)

   ## Set At
   <ISO now>

   ## Refinement History
   <若舊 goal.md 已有 ## Refinement History 區段，把它底下所有現有 bullet 原樣保留在這裡>
   - <ISO>: hard — <user 訊息原文>
   ```

   注意：先 Read 舊 goal.md 抽出 prior `## Refinement History` 區段的 bullets（若存在），整個 list 接在新區段下、再 append 本次 hard entry。避免每次 hard 覆寫都清空之前的修訂史。

2. **重置 planner artifacts**（同 /objective Step 4 的指令）：
   ```bash
   cp -f "${CLAUDE_PLUGIN_ROOT}/templates/.get-it-done/task_queue.md" .get-it-done/task_queue.md
   cp -f "${CLAUDE_PLUGIN_ROOT}/templates/.get-it-done/metrics.md" .get-it-done/metrics.md
   cp -f "${CLAUDE_PLUGIN_ROOT}/templates/.get-it-done/research_requests.md" .get-it-done/research_requests.md
   cp -f "${CLAUDE_PLUGIN_ROOT}/templates/.get-it-done/findings/_meta.md" .get-it-done/findings/_meta.md

   find .get-it-done/findings -type f -name 'RQ-*.md' -delete

   rm -rf .get-it-done/workspace
   mkdir -p .get-it-done/workspace

   rm -f .get-it-done/prd.md
   rm -f .get-it-done/plan_audit.md

   # hard reset also wipes the _goal main worktree + task worktrees + gid/* branches; the next
   # /continue Step 0.6 re-creates _goal from the (possibly new) HEAD. (soft does NOT reset —
   # it preserves the goal worktree and in-flight work.)
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/continue/scripts/gid.py" worktree-reset-all 2>/dev/null || true
   ```

3. **不動**：`.get-it-done/progress_log.md`、`.get-it-done/validation_log.md`、`.get-it-done/context/*`、`${CLAUDE_PLUGIN_DATA}/team_learnings/*`、`.get-it-done/state.md` 中的 `## Batch` 歷史 block。

   注意：與 `/objective` 在這點上**刻意不同** — `/objective` 會刪除舊的 ## Batch 區塊（因為是全新目標、歷史無關），但 `/adjust` hard 是在同一個目標的脈絡下換方向，保留 batch 歷史以便追溯先前嘗試。

4. **Rewrite `.get-it-done/state.md` YAML block**：
   ```yaml
   schema_version: 2
   phase: PLANNING
   status: WAITING
   batch_id: null
   batch_started_at: null
   batch_ended_at: null
   active_agents: []
   goal_set: true
   last_updated: <ISO now>
   ```

5. **Append 到 `.get-it-done/progress_log.md`**：
   ```
   <ISO> [GOAL_REFINED] hard — <new goal 前 100 字>
   ```

## Step 4: 收尾訊息（繁中）

輸出簡短摘要：

```
目標已修訂（<soft|hard>）。

修訂內容：<user 訊息一句摘要>
goal.md 變更：<soft: 新增 N 條 constraint / hard: 全文重寫>
保留：progress_log、validation_log、.get-it-done/context、A-side learnings
<soft 時：保留 task_queue / prd / findings / workspace>
<hard 時：已清空 task_queue / prd / findings / workspace>

當前階段：PLANNING（status: WAITING）
下一步：執行 /continue 讓 planner 依新 goal 重新規劃。
```

## 設計備註

- 本 skill 是唯一寫者；遵循與 `/objective` 相同的契約 — 只有 dispatcher 與本 skill 可以動 `.get-it-done/state.md`、`.get-it-done/progress_log.md`、`.get-it-done/task_queue.md` 等 shared state。
- Soft 模式刻意不替 planner 決定「哪些 task 要重做」— 那是 planner 的職責（planner.md 的 PR 規則涵蓋 replanning 邏輯）。Skill 只把 phase 切回 PLANNING、把新 constraint 寫進 goal.md，planner 在下次 /continue 自然會讀到。
- RUNNING 路徑採 AWAITING_HUMAN 暫停（而非 ABORT）— 已 spawn 但未持久化的 sub-agent 結果，會在下次 /continue 的 Step 2 crash recovery 中被回收，不會無謂浪費。
