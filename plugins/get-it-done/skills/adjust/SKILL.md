---
name: adjust
description: 修訂或具體化既有目標 — soft 為附加澄清/約束（保留 task_queue / prd / findings / workspace），hard 為重寫 Goal/Success（清空 planner artifacts）。兩種模式皆保留 progress_log、validation_log、team/context 與 A-side learnings。Usage：/adjust <修訂訊息>。階段性開發中發現方向歪掉或需要更具體規格時使用。
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

mkdir -p team/context team/findings team/workspace
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team/" team/
```

若 bootstrap 後 `team/state.md` 仍不存在，停止並提示 user 先用 `/objective <goal>` 初始化。

## Step 1: 讀 state 並決定是否需要先暫停

讀取 `team/state.md` 頂部 YAML block。依據 `phase` / `status` 處理：

```
IF phase == IDLE OR goal_set == false:
    EXIT — "目前沒有 active goal，無從修訂。請改用 /objective <goal> 設定新目標。"

IF phase == COMPLETE:
    詢問 user：「目標已完成。要重新打開並修訂嗎？這會走 hard 流程：清空 planner artifacts、保留 progress/validation log。」
    若否 → EXIT；若是 → 強制走 hard 模式（跳過 Step 2 的 soft 選項）。

IF status == RUNNING (dispatcher 正在跑或上次被中斷):
    # 自動暫停 — 不取消已 spawn 的 sub-agents 結果；下一次 /continue 的 Step 2
    # crash recovery 會把他們回收。
    paused_batch := state.batch_id
    append "<ISO> [ADJUST_PAUSE_REQUESTED] batch=<paused_batch> — user 透過 /adjust 介入" to progress_log.md
    rewrite state.md YAML（保留所有其他欄位）：
        phase: AWAITING_HUMAN
        status: WAITING
        batch_ended_at: <ISO now>
        active_agents: []
        last_updated: <ISO now>
        # batch_id 保留（讓下次 /continue 的 Step 2 認得這個未關閉的 batch）
    告知 user：「目前 batch <paused_batch> 已標記暫停；其 sub-agent 結果會在下次 /continue 的 crash recovery 中被回收。」
    繼續往下走（注意：之後 Step 3 會把 phase 從 AWAITING_HUMAN 改為 PLANNING）。

OTHERWISE (status == WAITING, phase ∈ {PLANNING, ANALYZING, EXECUTING, REPORTING, AWAITING_HUMAN}):
    直接進入 Step 2。
```

## Step 2: 決定模式（soft / hard）

讀 `team/goal.md`，把現有的 `## Goal` / `## Context & Constraints` / `## Success Definition` 顯示給 user 看。

依據 user 訊息語意決定：

- **明確 pivot / 重寫**（關鍵字：「改成」「換方向」「pivot」「重新做」「目標改為」「另一個目標」）→ 走 hard。
- **明確只是補規格 / 加 constraint**（關鍵字：「另外」「加上」「補充」「限制」「要求」「順便」「另外要求」「請確保」）→ 走 soft。
- **模糊** → 用 `AskUserQuestion` 詢問：

  > 「想要 soft 還是 hard 修訂？soft：在現有 goal.md 附加澄清/約束，保留 task_queue/prd/findings/workspace。hard：重寫 Goal/Success、清空 planner artifacts（同 /objective 的 reset，但保留 progress/validation log 與 context）。」
  >
  > 預設 soft（更安全）。

若 Step 1 已強制 hard（COMPLETE 路徑），直接跳到 Step 3b。

## Step 3a: Soft 路徑

1. **修訂 `team/goal.md`**（使用 Edit，保留其他內容）：
   - 在 `## Context & Constraints` 區段尾端 append bullet：`- (Refined <ISO>) <修訂內容摘要>`。原本為 `(none)` 或空 → 取代為新 bullet。
   - 若 user 訊息有提到成功條件變更：在 `## Success Definition` 區段尾端 append `- (Refined <ISO>) <新成功條件>`。
   - 若 `## Refinement History` 區段不存在，在檔案尾端新增：

     ```markdown

     ## Refinement History

     - <ISO>: <user 訊息原文>
     ```

     已存在 → append `- <ISO>: <user 訊息原文>` bullet。

2. **保留** 以下檔案不變：`team/task_queue.md`、`team/prd.md`、`team/research_requests.md`、`team/findings/*`、`team/workspace/*`、`team/metrics.md`。

3. **Rewrite `team/state.md` YAML block**（保留 block 以下所有文件 + ## Batch 歷史）：
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

4. **Append 到 `team/progress_log.md`**：
   ```
   <ISO> [GOAL_REFINED] soft — <user 訊息前 100 字>
   ```

5. 跳到 Step 4。

## Step 3b: Hard 路徑

向 user 確認：「即將 hard 替換目標。task_queue.md、prd.md、findings、workspace 將被清空（progress_log、validation_log、context 保留）。確認嗎？」若否 → EXIT。

1. **Overwrite `team/goal.md`**：
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
   - <ISO>: hard — <user 訊息原文>
   ```

   注意：hard 模式也記錄 Refinement History（後續若再次 /adjust 可累積）。

2. **重置 planner artifacts**（同 /objective Step 4 的指令）：
   ```bash
   cp -f "${CLAUDE_PLUGIN_ROOT}/templates/team/task_queue.md" team/task_queue.md
   cp -f "${CLAUDE_PLUGIN_ROOT}/templates/team/metrics.md" team/metrics.md
   cp -f "${CLAUDE_PLUGIN_ROOT}/templates/team/research_requests.md" team/research_requests.md
   cp -f "${CLAUDE_PLUGIN_ROOT}/templates/team/findings/_meta.md" team/findings/_meta.md

   find team/findings -type f -name 'RQ-*.md' -delete

   rm -rf team/workspace
   mkdir -p team/workspace

   rm -f team/prd.md
   ```

3. **不動**：`team/progress_log.md`、`team/validation_log.md`、`team/context/*`、`${CLAUDE_PLUGIN_DATA}/team_learnings/*`、`team/state.md` 中的 `## Batch` 歷史 block（與 /objective 一致 — 歷史保留以供追溯）。

4. **Rewrite `team/state.md` YAML block**：
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

5. **Append 到 `team/progress_log.md`**：
   ```
   <ISO> [GOAL_REFINED] hard — <new goal 前 100 字>
   ```

## Step 4: 收尾訊息（繁中）

輸出簡短摘要：

```
目標已修訂（<soft|hard>）。

修訂內容：<user 訊息一句摘要>
goal.md 變更：<soft: 新增 N 條 constraint / hard: 全文重寫>
保留：progress_log、validation_log、team/context、A-side learnings
<soft 時：保留 task_queue / prd / findings / workspace>
<hard 時：已清空 task_queue / prd / findings / workspace>

當前階段：PLANNING（status: WAITING）
下一步：執行 /continue 讓 planner 依新 goal 重新規劃。
```

## 設計備註

- 本 skill 是唯一寫者；遵循與 `/objective` 相同的契約 — 只有 dispatcher 與本 skill 可以動 `team/state.md`、`team/progress_log.md`、`team/task_queue.md` 等 shared state。
- Soft 模式刻意不替 planner 決定「哪些 task 要重做」— 那是 planner 的職責（planner.md 的 PR 規則涵蓋 replanning 邏輯）。Skill 只把 phase 切回 PLANNING、把新 constraint 寫進 goal.md，planner 在下次 /continue 自然會讀到。
- RUNNING 路徑採 AWAITING_HUMAN 暫停（而非 ABORT）— 已 spawn 但未持久化的 sub-agent 結果，會在下次 /continue 的 Step 2 crash recovery 中被回收，不會無謂浪費。
