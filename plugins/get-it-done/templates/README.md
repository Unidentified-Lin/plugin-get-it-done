# Templates —— 兩棵種子樹，兩個目的地

這個目錄下的檔案是 plugin 隨附的起手內容。`/objective` 和 `/continue` 會把這些檔案 bootstrap 複製到**兩個不同的可寫位置**，依照資料的範圍決定要去哪邊。

兩條複製都用 `rsync --ignore-existing` —— 缺檔才建立，既有檔案永不覆寫。

## `templates/team_learnings/` —— 跨專案（A 側）

| → 目的地 | `${CLAUDE_PLUGIN_DATA}/team_learnings/` |
|---|---|
| 解析路徑 | `~/.claude/plugins/data/get-it-done-<scope>/team_learnings/` |
| 範圍 | 單一使用者、**所有專案共用** |
| 撐過 plugin 更新嗎？ | ✅ 會（這就是為何用 `${CLAUDE_PLUGIN_DATA}` 而非 `${CLAUDE_PLUGIN_ROOT}`） |
| 進 git 嗎？ | ❌ 不會（住在使用者的 home 目錄） |
| 內容 | Agent 團隊累積的自我改善：跨專案模式、錯誤目錄、各 agent 規則、交棒教訓、提案修改 plugin source 的 diff |

## `templates/team/` —— 單一專案（B 側）

| → 目的地 | `<project>/team/` |
|---|---|
| 解析路徑 | 使用者當前工作目錄（呼叫 `/objective` 的位置） |
| 範圍 | **單一專案**，可透過 git 與隊友共享 |
| 撐過 plugin 更新嗎？ | ✅ 會（住在使用者的 repo 裡） |
| 進 git 嗎？ | ✅ 通常會（使用者也可以 `.gitignore` 掉） |
| 內容 | 每次目標的執行期狀態（state、goal、tasks、metrics、findings、日誌），以及 `team/context/` —— 專案專屬知識（領域、技術棧、程式碼、決策、利害關係人）。PRD 不在 templates 內 —— Planner 視需要才寫 `team/prd.md`，`/objective` 會在每個新目標前刪除舊的。 |

## 為什麼是兩棵樹、不是一棵

兩者都是「範本」，因為都是 plugin 隨附的起手內容。但儲存的是兩類根本不同的資料：

- **A** = agent 團隊本身怎麼運作得更好，與專案無關。寫進這裡的學習，當使用者之後開一個完全不同領域的新專案，仍然會自動套用。
- **B** = 團隊對於*這個專案*的發現。寫進這裡的事實不可遷移 —— 它綁定在這份 codebase、這個領域、這群利害關係人身上。

Reflector 寫入前一律先把學習分類成 A 或 B。完整決策矩陣參見 `agents/reflector.md`。

## Bootstrap 機制

```bash
# 環境變數防呆 —— 任一未設定就中止，避免空字串展開成 / 而誤寫到檔案系統根
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set}"
: "${CLAUDE_PLUGIN_DATA:?CLAUDE_PLUGIN_DATA is not set}"

# A —— 跨專案（單一使用者，所有專案共用）
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team_learnings/" "${CLAUDE_PLUGIN_DATA}/team_learnings/"

# B —— 單一專案（只屬於這個專案）
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team/" team/

# 另外建立 team/workspace/（v2：每個 executor 在底下開自己的 exec-<task_id>/）
mkdir -p team/workspace
```

兩條 sync 都會在每次 `/objective` 與 `/continue` 啟動時執行。具備冪等性 —— 全部都存在時，下一次執行複製 0 個檔案。

## 不要把執行期資料寫進這裡

`templates/` 隨 plugin 安裝目錄發布、且是唯讀的。任何在執行期寫進這裡的東西，都會在下一次 plugin 更新時被覆寫。**所有執行期寫入都應該寫到上面兩個目的地之一**，絕對不可寫回 `templates/`。
