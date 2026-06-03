# get-it-done — Main Flow Reference

> This document is the authoritative pipeline map for the `get-it-done` plugin.
> Read this to understand where you are in the overall flow and what comes next.

---

## Two Entry Paths

```
Interactive Path                    Autonomous Path
─────────────────                   ─────────────────
/plan                               /objective <goal>
  │                                   │
  ▼                                   ▼
A–C (planning)                      PLANNING phase
  │                                 (planner agent)
  │ .get-it-done/ initialized                 │
  ▼                                   ▼
/continue ←─────────────────────── EXECUTING phase
  │                                 (dispatcher loop)
  ▼
COMPLETE / AWAITING_HUMAN / PLANNED_PAUSE
```

The **interactive path** (`/plan`) produces a frozen human-reviewed plan before handing off to the autonomous dispatcher. Use it when requirements are ambiguous or implementation decisions need user input.

The **autonomous path** (`/objective`) goes straight to autonomous planning and execution. Use it when the goal is clear and you trust the planner to decompose it correctly.

---

## Interactive Path Pipeline (A → B → C → Dispatcher)

```
A. Input
   A1. Parse requirement (ticket ID or conversation)
        │
        ▼
B. Planning Document (progressively filled)
   🤖 interactive-planner  👾 scope-scanner  👻 scope-verifier

   B1. Requirement confirmation loop 🤖
        a. Create planning document skeleton
        b. Refine requirements, define scope
        c. Confirm with user ←── Loop ①

   B2. Change scope inventory 👾↔👻 → 🤖
        a. Spawn scope-scanner (mode: change-scope)
        b. scope-scanner spawns scope-verifier (max 3 loops)
        c. Planner presents scope → user confirms ←── Loop ②

   B3. Implementation direction 🤖
        a. Generate discussion list
        b. Discuss topics one by one ←── Loop ③ (per topic)
        c. User confirms direction ←── Loop ④

   B4. Impact scope inventory 👾↔👻 → 🤖
        a. Spawn scope-scanner (mode: impact-scope)
        b. scope-scanner spawns scope-verifier (max 3 loops)
        c. Planner presents impact → user confirms ←── Loop ⑤
        │
        ▼
C. Task Breakdown
   C1. User confirms task framework ←── Loop ⑥
   C2. Surgical codebase investigation, fill each task
   C3. User confirms task list → plan-reviewer audits 📋
        ├─ PASS → freeze + initialize .get-it-done/ state → /continue
        ├─ Return to C2 (task details)
        ├─ Return to B3 (solution direction)
        └─ Return to B1 (requirements)
        │
        ▼
   .get-it-done/task_queue.md + .get-it-done/metrics.md + .get-it-done/state.md (EXECUTING)
        │
        ▼
/continue (autonomous dispatcher)
```

---

## Autonomous Path State Machine

```
PLANNING → (ANALYZING — parallel N analysts)? → EXECUTING → REPORTING → COMPLETE

EXECUTING: dispatcher batch per tick
  - pending tasks (deps done) → executor
  - executed tasks → validator
  - needs_rework → re-executor
  - milestone all done → milestone validator
  Batch size ≤ 5, heterogeneous agents per batch.
```

---

## Agent Roster

| Agent | Path | Role |
|-------|------|------|
| `interactive-planner` | `/plan` skill | Interactive A→B→C planning with user |
| `scope-scanner` | Spawned by interactive-planner | Method-level codebase scope inventory |
| `scope-verifier` | Spawned by scope-scanner | Validates scanner output (max 3 loops) |
| `plan-reviewer` | After C3 | Audits frozen plan completeness |
| `planner` | `/objective` → dispatcher | Autonomous DAG decomposition |
| `analyst` | Dispatcher (ANALYZING) | Research per RQ-X |
| `executor` | Dispatcher (EXECUTING) | Implements one task (T-XXX) |
| `validator` | Dispatcher (EXECUTING) | Validates task or milestone |
| `code-reviewer` | `/review` skill | Universal engineering checklist review |
| `reflector` | Post-REPORTING | Cross-project and per-project learning |

---

## Step Positioning Table (Interactive Path)

| Step | Entry Condition | Output | Agent | Next |
|------|-----------------|--------|-------|------|
| A1 | User triggers /plan | Raw requirement | interactive-planner | B1 |
| B1 | Have requirement | Planning doc skeleton + confirmed requirements | interactive-planner | B2 (user confirm) |
| B2 | B1 confirmed | Method-level change scope in plan doc | scope-scanner + scope-verifier | B3 (user confirm) |
| B3 | B2 confirmed | Discussion outcomes + implementation direction | interactive-planner | B4 (user confirm) |
| B4 | B3 confirmed | Impact scope in plan doc | scope-scanner + scope-verifier | C1 (user confirm) |
| C1 | B4 confirmed | User confirms task framework | interactive-planner | C2 |
| C2 | C1 confirmed | Each task filled: file paths, steps, verification, test flag | interactive-planner | C3 |
| C3 | C2 complete | Frozen plan + plan-reviewer audit → PASS / RETURN | interactive-planner + plan-reviewer | /continue (PASS) or return |

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
