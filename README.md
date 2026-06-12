# plugin-get-it-done

Autonomous 5-agent team (Planner, Analyst, Executor, Validator, Reflector) with batch-aware dispatcher for goal-driven development. v2 architecture with heterogeneous parallel execution, milestone-level integration validation, and dual-tier learning system (cross-project A-side + per-project B-side).

## 🚀 Add this Marketplace

```shell
claude plugin marketplace add Unidentified-Lin/plugin-get-it-done
```

> Marketplace name: `get-it-done`

## 📦 Available Plugins

| Plugin | Skills | Description |
|--------|--------|-------------|
| `get-it-done` | `/blueprint` | Interactive planning pipeline (Intake → Requirements Confirmation → Change/Impact Scope Inventory → Implementation Direction → Task Detailing → Plan Freeze & Handoff) — initializes `.get-it-done/` execution state for `/continue` |
| | `/objective` | Set business goal and initialize agent team, v2 state schema, bootstrap workspace |
| | `/adjust` | Refine the active goal mid-flight — soft (append constraints, preserve task_queue/prd/findings) or hard (rewrite goal, reset planner artifacts). Both preserve progress_log, validation_log, and .get-it-done/context |
| | `/continue` | Batch-aware dispatcher: autopilots from goal to COMPLETE; only stops at terminal phase, planner-declared PauseAfter milestones, or crash recovery. Schedules executors/validators/analysts in parallel (N≤5), enforces DAG & collision detection |
| | `/review` | Code review against universal engineering checklist (correctness, error handling, security, data integrity, performance, style) |

## 🔧 Install a Plugin

```shell
# Install from this marketplace (first add the marketplace)
claude plugin install get-it-done@get-it-done

# Or install directly from the repo
claude plugin install Unidentified-Lin/plugin-get-it-done:plugins/get-it-done
```

## 📁 Repository Structure

```
.claude-plugin/
  marketplace.json              # Marketplace registry

plugins/get-it-done/
  .claude-plugin/
    plugin.json                 # Plugin manifest (Stage 5+)
  README.md                     # Full architecture & usage guide
  
  agents/
    planner.md                  # Decompose goal → DAG + PRD (rules PR-001..019)
    analyst.md                  # Research single RQ-X independently (5 rules AR-001..005)
    executor.md                 # Implement task T-XXX (11 rules ER-001..011)
    validator.md                # Per-task & milestone validation (6 rules VR-001..006)
    reflector.md                # Post-cycle learning analysis (8 rules RR-001..008)
  
  skills/
    blueprint/SKILL.md          # Interactive planning pipeline (Intake → … → Plan Freeze & Handoff) → hands off to /continue
    objective/SKILL.md          # Goal bootstrap: state.md schema, workspace init
    adjust/SKILL.md             # Mid-flight goal refinement (soft/hard); auto-pauses RUNNING dispatcher via AWAITING_HUMAN
    continue/SKILL.md           # Dispatcher: Step 0-11 inner loop (crash recovery, DAG check, batch pool, atomic pre-write, spawn, parse, persist, close, loop)
    review/SKILL.md             # Code review against universal engineering checklist
  
  templates/
    .get-it-done/                       # Per-goal runtime state (state.md, task_queue.md, prd.md, findings/, workspace/)
    team_learnings/
      agent_rules/              # Dynamic rules (A-side, cross-project): planner/analyst/executor/validator/reflector
      patterns.md               # Recurring patterns (provisional + promoted)
      errors.md, handoff_lessons.md, proposed_changes.md
    .get-it-done/context/               # Per-project learnings (B-side): domain_knowledge, tech_stack, codebase_map, decisions, stakeholder_notes
```

## 🎯 Core Design (v2 Architecture)

- **Dispatcher-only state writes**: Sub-agents emit structured `---agent-return---` YAML; dispatcher alone persists to `state.md`, `task_queue.md`, logs
- **Heterogeneous parallel batches**: Up to 5 in-flight agents (executor + validator + analyst + milestone-validator) in one batch
- **DAG-aware scheduling**: Tasks form explicit dependency graph; no task starts until deps are done
- **Milestone-level validation**: Integration-level acceptance criteria on top of per-task validation
- **Crash recovery**: Three sub-cases (PLANNING timeout, sub-agent interrupted, batch close interrupted) with idempotency guarantees
- **Collision detection**: Source-path overlaps prevented via `Touches` field + dispatcher pool check
- **Autopilot with planned pauses**: Dispatcher runs to COMPLETE without context-budget yields; planner decides pause checkpoints at planning time via `PauseAfter: true` on milestones (e.g. UX review, real-world testing). Soft pause — next /continue resumes naturally
- **Dual-tier learning**: A-side rules survive plugin updates (cross-project); B-side rules live in `.get-it-done/context/` (project-specific)
- **Full 繁體中文 compliance**: All CLI output in Traditional Chinese

## 📖 Quick Start

```bash
# Set a goal and launch the first cycle
/objective 製作一個簡易流程圖編輯器，支援拖放、儲存/載入與 PNG 匯出

# Continue (repeatable across sessions)
/continue

# Refine mid-flight when testing reveals direction is off or specs need more detail
/adjust 另外要求：節點刪除前需確認對話框，且匯出 PNG 要含浮水印

# Check status
cat .get-it-done/state.md                          # Current phase, batch history
cat .get-it-done/progress_log.md                   # Execution timeline
cat .get-it-done/validation_log.md                 # Validation verdicts
cat .get-it-done/context/domain_knowledge.md       # Project learnings
```

## 🔗 Reference

- **Full architecture guide**: `plugins/get-it-done/README.md`
- **Agent rules matrix**: `plugins/get-it-done/templates/team_learnings/agent_rules/*.md`
- **Schema & contracts**: `plugins/get-it-done/templates/.get-it-done/state.md`

---

**Version**: 1.1.1 | **Stage**: 5 (A/B Learning Architecture Complete) | **Author**: Unidentified-Lin
