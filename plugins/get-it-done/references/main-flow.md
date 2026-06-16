# get-it-done — Main Flow Reference

> This document is the authoritative pipeline map for the `get-it-done` plugin.
> Read this to understand where you are in the overall flow and what comes next.

---

## Two Entry Paths

```
Interactive Path                    Autonomous Path
─────────────────                   ─────────────────
/blueprint                          /objective <goal>
  │                                   │
  ▼                                   ▼
Planning stages                     PLANNING phase
(Intake → … → Freeze & Handoff)     (planner agent)
  │                                   │
  │ .get-it-done/ initialized         │
  ▼                                   ▼
/continue ←─────────────────────── EXECUTING phase
  │                                 (dispatcher loop)
  ▼
COMPLETE / AWAITING_HUMAN / PLANNED_PAUSE
```

The **interactive path** (`/blueprint`) produces a frozen human-reviewed plan before handing off to the autonomous dispatcher. Use it when you want to be in the loop — review and confirm scope and implementation decisions round by round before any execution starts.

The **autonomous path** (`/objective`) is full autopilot: even from an abstract, high-level goal it decomposes → researches → progressively plans → executes all the way to completion, with the dispatcher self-looping and no step-by-step human intervention required. The two paths differ by whether you want to review the plan first, not by how clear the goal is.

---

## Interactive Path Pipeline (/blueprint → Dispatcher)

```
Intake
   Parse requirement (ticket ID or conversation)
        │
        ▼
Planning stages (planning document progressively filled)
   🤖 /blueprint orchestrator (MAIN conversation — user loops need AskUserQuestion)
   👾 scope-scanner  👻 scope-verifier (non-interactive sub-agents)

   Requirements Confirmation 🤖
        a. Create planning document skeleton
        b. Refine requirements, define scope
        c. Confirm with user ←── Loop ①

   Change Scope Inventory 🤖→👾→👻 (orchestrator-driven, max 3 iterations)
        a. Orchestrator spawns scope-scanner (mode: change-scope, iteration k)
        b. Orchestrator spawns scope-verifier on the result
        c. Issues → re-spawn scanner with issue list; PASS → present scope
        d. User confirms ←── Loop ②

   Implementation Direction 🤖
        a. Generate discussion list
        b. Discuss topics one by one ←── Loop ③ (per topic)
        c. User confirms direction ←── Loop ④

   Impact Scope Inventory 🤖→👾→👻 (same orchestrator-driven loop)
        a. Orchestrator spawns scope-scanner (mode: impact-scope, iteration k)
        b. Orchestrator spawns scope-verifier on the result
        c. Issues → re-spawn scanner; PASS → present impact
        d. User confirms ←── Loop ⑤
        │
        ▼
Task Breakdown stages
   Task Framework Confirmation — user confirms task framework ←── Loop ⑥
   Task Detailing — surgical codebase investigation, fill each task
   Plan Freeze & Handoff — user confirms task list → plan-reviewer audits 📋
        ├─ PASS → freeze + initialize .get-it-done/ state → /continue
        ├─ Return to Task Detailing (task details)
        ├─ Return to Implementation Direction (solution direction)
        └─ Return to Requirements Confirmation (requirements)
        │
        ▼
   .get-it-done/task_queue.md + .get-it-done/metrics.md + .get-it-done/state.md (EXECUTING)
        │
        ▼
/continue (autonomous dispatcher)
```

### Legacy stage codes

Older diagrams and documents used letter codes for these stages. Mapping:

| Legacy code | Stage name |
|-------------|------------|
| A1 | Intake |
| B1 | Requirements Confirmation |
| B2 | Change Scope Inventory |
| B3 | Implementation Direction |
| B4 | Impact Scope Inventory |
| C1 | Task Framework Confirmation |
| C2 | Task Detailing |
| C3 | Plan Freeze & Handoff |

---

## Autonomous Path State Machine

```
PLANNING → (ANALYZING — parallel N analysts)? → [plan audit gate 📋] → EXECUTING → REPORTING → COMPLETE

Plan audit gate: before PLANNING→EXECUTING the dispatcher spawns plan-reviewer
(queue-audit mode) on task_queue.md + metrics.md; fail → back to PLANNING with
.get-it-done/plan_audit.md (max 2 rounds, then waved through with a warning).

EXECUTING: dispatcher batch per tick
  - pending tasks (deps done) → executor
  - executed tasks → validator
  - needs_rework → re-executor
  - milestone all done → milestone validator
  Batch size ≤ 5, heterogeneous agents per batch.

Git isolation (git projects, goal-worktree model): at goal start the dispatcher
creates ONE _goal worktree on branch gid/goal-<slug> (from the user's HEAD); ALL
goal source accumulates there, so the user's own branch/working tree stay clean
and concurrent goals can share a repo. Parallel by default, plan-driven: independent
tasks (deps satisfied, non-overlapping Touches) run concurrently, each in a per-task
worktree branched from the goal branch, merged back on validator pass — up to
max_parallel (default 5) / max_worktrees. Dependent or same-file tasks serialize
automatically; a lone eligible task runs in _goal. Executor + its validator share a
task's worktree; validator PASS commits one commit on the goal branch. Each validated
milestone consolidates to ONE commit on the goal branch (no intermediate commits
kept). Every worktree shares one symlinked .get-it-done/. At completion the goal
branch is left for the user to review/merge (never auto-merged). Non-git projects
fall back to direct edits + a scheduling guard. All git work is done by gid.py;
bookkeeping in .get-it-done/git_state.json.
```

---

## Agent Roster

| Agent | Path | Role |
|-------|------|------|
| *(no agent — main conversation)* | `/blueprint` skill | The skill itself orchestrates all planning stages with the user (sub-agents cannot ask the user questions) |
| `scope-scanner` | Spawned by /blueprint orchestrator (both scope inventory stages) | Method-level codebase scope inventory |
| `scope-verifier` | Spawned by /blueprint orchestrator after each scanner pass | Validates scanner output (max 3 loops) |
| `plan-reviewer` | At Plan Freeze & Handoff (document mode); dispatcher plan audit gate (queue-audit mode) | Audits plan completeness / criteria verifiability |
| `planner` | `/objective` → dispatcher | Autonomous DAG decomposition |
| `analyst` | Dispatcher (ANALYZING) | Research per RQ-X |
| `executor` | Dispatcher (EXECUTING) | Implements one task (T-XXX) |
| `validator` | Dispatcher (EXECUTING) | Validates task or milestone |
| `code-reviewer` | `/review` skill | Universal engineering checklist review |
| `reflector` | Post-REPORTING | Cross-project and per-project learning |

---

## Step Positioning Table (Interactive Path)

| Stage | Entry Condition | Output | Driven by | Next |
|-------|-----------------|--------|-----------|------|
| Intake | User triggers /blueprint | Raw requirement | orchestrator (main conversation) | Requirements Confirmation |
| Requirements Confirmation | Have requirement | Planning doc skeleton + confirmed requirements | orchestrator | Change Scope Inventory (user confirm) |
| Change Scope Inventory | Requirements confirmed | Method-level change scope in plan doc | orchestrator → scope-scanner + scope-verifier | Implementation Direction (user confirm) |
| Implementation Direction | Change scope confirmed | Discussion outcomes + implementation direction | orchestrator | Impact Scope Inventory (user confirm) |
| Impact Scope Inventory | Direction confirmed | Impact scope in plan doc | orchestrator → scope-scanner + scope-verifier | Task Framework Confirmation (user confirm) |
| Task Framework Confirmation | Impact scope confirmed | User confirms task framework | orchestrator | Task Detailing |
| Task Detailing | Framework confirmed | Each task filled: file paths, steps, verification, test flag | orchestrator | Plan Freeze & Handoff |
| Plan Freeze & Handoff | Task Detailing complete | Frozen plan + plan-reviewer audit → PASS / RETURN | orchestrator → plan-reviewer | /continue (PASS) or return |

---

## Planning Document Path Conventions

- **Plan document**: `{project-root}/docs/plans/{xxx}-plan/{xxx}-plan.md`
- **Task files**: `{project-root}/docs/plans/{xxx}-plan/tasks/{n:02d}-{task-slug}-task.md`
- **Derive `{xxx}`** from feature name or ticket ID (e.g., `issue502-add-login`)

---

## Key Constraints

- **Ticket systems**: Read work item body + acceptance criteria only. Never write back.
- **Scope-scanner**: Always verify file paths with `glob`/`grep` before writing into plan doc.
- **Plugin independence**: `get-it-done` does not depend on external git workflow or DB migration plugins.
