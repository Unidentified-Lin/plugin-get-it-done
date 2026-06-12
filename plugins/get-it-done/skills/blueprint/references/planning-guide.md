# Planning Guide — Blueprint Skill Operational Manual

> **For**: the /blueprint orchestrator (runs in the **main conversation** — NOT a sub-agent,
> because the user-confirmation loops require direct user interaction)
> **Load at**: Skill startup
> **Covers**: Intake, Requirements Confirmation, Change Scope Inventory, Implementation
> Direction, Impact Scope Inventory, and the document update principle

---

## Pipeline stages (canonical names)

```
Intake → Requirements Confirmation → Change Scope Inventory → Implementation Direction
       → Impact Scope Inventory → Task Framework Confirmation → Task Detailing
       → Plan Freeze & Handoff
```

This guide covers the first five stages; `task-breakdown-guide.md` covers the last three.

---

## Role

You are the **blueprint orchestrator** for the `get-it-done` plugin. Your job is to transform a raw requirement
(ticket/issue or conversation) into a frozen, actionable planning document through the full
pipeline above. You drive every stage yourself and spawn only the non-interactive sub-agents
(scope-scanner, scope-verifier, plan-reviewer).

---

## Platform Detection

Read `platform-adapter.md` (path provided in your task prompt) before proceeding. Use it to:
- Detect whether you are on Claude Code or GitHub Copilot
- Spawn sub-agents with the correct tool (`Agent` vs `task`)
- Ask user questions with the correct tool (`AskUserQuestion` vs `ask_user`)
- Open documents in the browser with the correct OS command

---

## Stage: Intake

Identify the input type:

| Input Type | Detection | Action |
|------------|-----------|--------|
| Ticket / Issue ID | Numeric ID, URL, or `#NNNNNN` format | Read ticket body + acceptance criteria from your ticket system. Never write back. |
| Natural language | Free-form text in conversation | Use as-is; note ambiguities for Requirements Confirmation |
| Empty call | No context given | Ask: "你想開發什麼功能？" |

After reading input, proceed to Requirements Confirmation.

---

## Stage: Requirements Confirmation（需求確認循環）

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
   - 使用者確認無誤 → 進入 Change Scope Inventory
   - 使用者要進一步討論/澄清 → 來回討論，更新計畫 md，重複確認步驟

**Rule**: One question per turn.
- **Claude Code**: Use `AskUserQuestion` tool with choices array
- **GitHub Copilot**: Use `ask_user` with choices array

After each round, update the planning document with refined requirements and scope.

**Exit condition**: User explicitly confirms requirements are correct.

---

## Stage: Change Scope Inventory（異動範圍盤點）

**Goal**: Deep codebase analysis to identify function/method-level change scope, then confirm with user.

Process (the scanner↔verifier loop is **orchestrator-driven** — scope-scanner has no agent-spawning tool):

1. FOR iteration k = 1..3:
   a. Spawn **scope-scanner** sub-agent with:
      - Planning document path
      - Mode: `change-scope`
      - Path to `scope-scanner-guide.md`
      - Loop iteration: k
      - (k ≥ 2) the verifier's issue list from the previous iteration — the corrections to address
   b. After the scanner returns, spawn **scope-verifier** with: planning document path, mode `change-scope`, path to `scope-verifier-guide.md`, loop iteration k.
   c. Read the verifier's report:
      - PASS → exit the loop
      - issues found AND k < 3 → next iteration
      - issues found AND k == 3 → escalate: present the unresolved issue list to the user and let them decide (accept as-is / adjust requirements / abort)
2. Confirm the `<!-- scope-verifier(change-scope):` summary annotation exists in the plan doc; if the verifier forgot it, record the verdict in the doc yourself.
3. Summarize the change scope for the user in a digestible format
4. Ask user to confirm: "以上是分析出的異動範圍，確認正確嗎？"
   - If user questions or wants adjustments → discuss, possibly re-run the loop
   - If user confirms → proceed to Implementation Direction

---

## Stage: Implementation Direction（實作方向確認）

**Goal**: Through structured topic-by-topic discussion, establish implementation direction for all change points.

### Part 1 — Generate Discussion List

Based on confirmed requirements and the verified change scope, produce a **討論清單** — topics requiring user decision before implementation direction can be finalized.

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
1. Present context (relevant facts from the confirmed requirements and change scope)
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
   - If confirm → proceed to Impact Scope Inventory
   - If revisit → return to that topic

---

## Stage: Impact Scope Inventory（影響範圍盤點）

**Goal**: Identify all features/functions impacted by the planned changes.

Process (same orchestrator-driven loop as Change Scope Inventory):

1. FOR iteration k = 1..3:
   a. Spawn **scope-scanner** with: planning document path, mode `impact-scope`, path to `scope-scanner-guide.md`, loop iteration k, and (k ≥ 2) the verifier's issue list to address.
   b. Spawn **scope-verifier** with: planning document path, mode `impact-scope`, path to `scope-verifier-guide.md`, loop iteration k.
   c. PASS → exit loop; issues at k == 3 → escalate to the user.
2. Confirm the `<!-- scope-verifier(impact-scope):` summary annotation exists; record the verdict yourself if missing.
3. Present impact scope to user:
   - User confirms → proceed to the Task Breakdown stages
   - User wants minor adjustments → discuss, update plan, re-confirm
   - User wants different approach (impact too large) → return to Implementation Direction
   - User believes change scope is wrong → return to Change Scope Inventory

---

## Task Framework Growth Across Stages

As the planning stages progress, the task list grows from nothing to named tasks:

```
(Requirements, first round)      任務清單: 空（建立骨架）
(Change Scope verified)          任務清單: - [ ] 建立判斷邏輯（模糊，從異動範圍推導）
(Direction confirmed)            任務清單: - [ ] 修改 CreateOrder in OrderService（具名）
(Impact Scope confirmed)         任務清單: 同上，可能因影響範圍新增額外任務
```

Always update the planning document immediately after each stage — no "fill in later".

---

## Document Update Checkpoints

| Stage | What to update |
|-------|----------------|
| Requirements Confirmation (first round) | Create doc, fill 3-block skeleton |
| After each Requirements round | 需求重點, 限制條件, 異動範圍（大項） |
| After Change Scope verification pass | 異動範圍（詳細） — method-level inventory |
| After user confirms change scope | Finalize 異動範圍 section |
| After each Direction topic decision | Update plan doc with that topic's decision |
| After user confirms direction | 選定方案, 實作方向重點, 各變更點實作方向 |
| After Impact Scope verification pass | 影響範圍 — direct + indirect impacts |
| Task Framework confirmed | Lock task list structure |
| After each Task Detailing fill | That task's 檔案路徑, 實作步驟, 驗證方式, 測試旗標 |
| Plan Freeze & Handoff confirmed | Set document status; initialize .get-it-done/ state |

---

## Entering the Task Breakdown Stages

When Impact Scope is confirmed and the plan doc has all four confirmed planning sections
(requirements / change scope / direction / impact scope):
- Load `task-breakdown-guide.md` (path provided in your task prompt) for the Task Framework Confirmation, Task Detailing, and Plan Freeze & Handoff rules.
- Proceed to Task Framework Confirmation.
