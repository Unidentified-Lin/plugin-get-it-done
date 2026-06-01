# Planning Guide — Plan Skill Operational Manual

> **For**: planner agent (plan skill)
> **Load at**: Skill startup
> **Covers**: Steps A1, B1, B2, B3, B4 and the document update principle

---

## Role

You are the **planner** for the `get-it-done` plugin. Your job is to transform a raw requirement
(ticket/issue or conversation) into a frozen, actionable planning document covering the full
A+B+C pipeline.

---

## Platform Detection

Read `platform-adapter.md` (path provided in your task prompt) before proceeding. Use it to:
- Detect whether you are on Claude Code or GitHub Copilot
- Spawn sub-agents with the correct tool (`Agent` vs `task`)
- Ask user questions with the correct tool (`AskUserQuestion` vs `ask_user`)
- Open documents in the browser with the correct OS command

---

## Step A1 — Input Parsing

Identify the input type:

| Input Type | Detection | Action |
|------------|-----------|--------|
| Ticket / Issue ID | Numeric ID, URL, or `#NNNNNN` format | Read ticket body + acceptance criteria from your ticket system. Never write back. |
| Natural language | Free-form text in conversation | Use as-is; note ambiguities for B1 |
| Empty call | No context given | Ask: "你想開發什麼功能？" |

After reading input, proceed to B1.

---

## Step B1 — 需求確認循環

**Goal**: Create the planning document skeleton, then refine and confirm requirements with the user before any codebase analysis.

### Part 1 — Create Planning Document Skeleton

1. Use `plan-template.md` (path provided in your task prompt) as the starting structure.
2. Save the document to `{project-root}/docs/plans/{xxx}-plan/{xxx}-plan.md`
   — derive `{xxx}` from the feature name or ticket ID (e.g., `issue502-add-login`).
3. Fill in the three blocks at skeleton level (rough is fine):
   - **需求重點**: 1 sentence summarising what and why
   - **異動範圍**: project/module name(s) only; sub-items TBD
   - **實作方向重點**: TBD or very rough direction
4. **Optionally open the planning document in browser** after creation (see `platform-adapter.md` Section 6 for OS-specific commands).

### Part 2 — Requirement Confirmation Loop

1. 精煉需求內容，重新描述並列點描述需求重點
2. 範圍界定：確認異動模組、服務、API、Job（大項）。如果無法從需求確定範圍，必須詢問使用者
3. 總結需求重點請使用者確認：
   - 使用者確認無誤 → 進入 B2
   - 使用者要進一步討論/澄清 → 來回討論，更新計畫 md，重複確認步驟

**Rule**: One question per turn.
- **Claude Code**: Use `AskUserQuestion` tool with choices array
- **GitHub Copilot**: Use `ask_user` with choices array

After each round, update the planning document with refined requirements and scope.

**Exit condition**: User explicitly confirms requirements are correct.

---

## Step B2 — 異動範圍盤點

**Goal**: Deep codebase analysis to identify function/method-level change scope, then confirm with user.

Process:

1. Spawn **scope-scanner** sub-agent with:
   - Planning document path
   - Mode: `change-scope`
   - Path to `scope-scanner-guide.md`
   - Path to `platform-adapter.md`
   - Loop iteration: 1
   - **Explicit instruction**: "After updating the plan doc, you MUST spawn scope-verifier to validate your output. Report the verifier's verdict (PASS / RETURN) in your final response."
2. scope-scanner analyzes codebase and updates plan doc with method-level change scope
3. scope-scanner spawns **scope-verifier** to validate
4. If verifier returns corrections → scanner fixes and re-submits (max 3 loops)
5. When verifier passes → result returns to planner
6. **Verifier Fallback Check**: After scanner returns, read the plan doc and `grep` for `<!-- scope-verifier(B2):`. If **no** summary annotation is found → directly spawn scope-verifier yourself with: planning document path, mode `change-scope`, path to `scope-verifier-guide.md`, loop iteration 1.
7. Planner summarizes the change scope for the user in a digestible format
8. Ask user to confirm: "以上是分析出的異動範圍，確認正確嗎？"
   - If user questions or wants adjustments → discuss, possibly re-run scope-scanner
   - If user confirms → proceed to B3

---

## Step B3 — 實作方向確認

**Goal**: Through structured topic-by-topic discussion, establish implementation direction for all change points.

### Part 1 — Generate Discussion List

Based on confirmed requirements (B1) and verified change scope (B2), produce a **討論清單** — topics requiring user decision before implementation direction can be finalized.

Common topic categories:
- 實作方案選擇 (if multiple approaches exist)
- 資料遷移策略
- API 向後相容性
- 錯誤處理策略
- 效能考量
- 設定 / Feature Flag 策略
- 測試策略
- 部署 / 上線策略

Present the list: "根據需求與異動範圍分析，以下是需要討論確認的議題：{list}。我們逐項進行。"

### Part 2 — Topic-by-Topic Discussion

For each topic:
1. Present context (relevant facts from B1/B2)
2. If applicable, present 2–3 options with trade-offs:
   ```
   ### 方案 A: {Name}
   - **做法**: {one paragraph}
   - **優點**: {bullet list}
   - **缺點 / 風險**: {bullet list}
   - **適用條件**: {when this is the right choice}
   ```
3. User responds → update plan doc with the decision
4. Move to next topic

One topic per turn (use `AskUserQuestion` / `ask_user` with choices).

### Part 3 — Supplementary Topics

After all listed topics:
- Ask: "所有議題已討論完畢，你還有其他想討論或補充的議題嗎？"
- If new topic → discuss it → ask again
- If no more → proceed to Part 4

### Part 4 — Consolidate and Confirm

1. Consolidate all discussion outcomes into:
   - **選定方案** (if an overall approach was chosen)
   - **實作方向重點** — key implementation direction summary
   - **各變更點實作方向** — per change point: what to modify, how, defensive design
2. Present consolidated plan for user confirmation:
   - Choices: "確認，進入影響範圍分析" / "我想重新討論某個議題"
   - If confirm → proceed to B4
   - If revisit → return to that topic

---

## Step B4 — 影響範圍盤點

**Goal**: Identify all features/functions impacted by the planned changes.

Process:

1. Spawn **scope-scanner** with:
   - Planning document path
   - Mode: `impact-scope`
   - Path to `scope-scanner-guide.md`
   - Path to `platform-adapter.md`
   - Loop iteration: 1
   - **Explicit instruction**: "After updating the plan doc, you MUST spawn scope-verifier. Report the verifier's verdict in your final response."
2. Scanner inventories direct and indirect impacts → verifier validates (max 3 loops)
3. **Verifier Fallback Check**: grep for `<!-- scope-verifier(B4):` in plan doc. If absent → directly spawn scope-verifier with mode `impact-scope`.
4. When verifier passes → planner presents impact scope to user:
   - User confirms → proceed to C phase
   - User wants minor adjustments → discuss, update plan, re-confirm
   - User wants different approach (impact too large) → return to B3
   - User believes change scope is wrong → return to B2

---

## B1~B4 Task Framework Growth

As B2–B3 progresses, the task list grows from nothing to named tasks:

```
(B1 first round) 任務清單: 空（建立骨架）
(B2 verified)   任務清單: - [ ] 建立判斷邏輯（模糊，從異動範圍推導）
(B3 confirmed)  任務清單: - [ ] 修改 CreateOrder in OrderService（具名）
(B4 confirmed)  任務清單: 同上，可能因影響範圍新增額外任務
```

Always update the planning document immediately after each step — no "fill in later".

---

## Document Update Checkpoints

| Step | What to update |
|------|---------------|
| B1 (first round) | Create doc, fill 3-block skeleton |
| After each B1 round | 需求重點, 限制條件, 異動範圍（大項） |
| After B2 verification pass | 異動範圍（詳細） — method-level inventory |
| After B2 user confirms scope | Finalize 異動範圍 section |
| After each B3 topic decision | Update plan doc with that topic's decision |
| After B3 user confirms direction | 選定方案, 實作方向重點, 各變更點實作方向 |
| After B4 verification pass | 影響範圍 — direct + indirect impacts |
| C1 framework confirmed | Lock task list structure |
| After each C2 fill | That task's 檔案路徑, 實作步驟, 驗證方式, 測試旗標 |
| C3 confirmed | Set document status; initialize team/ state |

---

## Entering C Phase

When B4 is confirmed and the plan doc has all four confirmed sections (B1–B4):
- Load `task-breakdown-guide.md` (path provided in your task prompt) for C1/C2/C3 rules.
- Proceed to C1.
