# CLAUDE.md — plugin-get-it-done

## 開發工作流程（必須遵守）

每次有新的程式碼／檔案修改時：

1. **先建立新分支**再開始改（不要直接改 `master`）。分支名稱用描述性命名，例如 `feature/<簡述>`。
2. **把修改 commit 在該新分支上**，不要 commit 到 `master`。
3. **不要自行合回 `master`、也不要自行 push**。等使用者明確確認「可以合回 master」後才合併。
4. **版本號只在確定要合回 master 時才更新**（`plugins/get-it-done/.claude-plugin/plugin.json` 的 `version`）—— 在使用者確認前不要動版本號。

> 預設只 commit、不 push（push 僅在使用者明確要求時）。
