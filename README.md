# plugin-get-done

Autonomous 5-agent team (Planner, Analyst, Executor, Validator, Reflector) with batch-aware dispatcher for goal-driven development. v2 architecture with heterogeneous parallel execution, milestone-level integration validation, and dual-tier learning system (cross-project A-side + per-project B-side).

## 🚀 Add this Marketplace

```shell
claude plugin marketplace add Unidentified-Lin/plugin-get-done
```

> Marketplace name: `get-it-done`

## 📦 Available Plugins

| Plugin | Skills | Description |
|--------|--------|-------------|
| `get-it-done` | `/objective` | Set business goal and initialize agent team, v2 state schema, bootstrap workspace |
| | `/continue` | Batch-aware dispatcher: schedules executors/validators/analysts in parallel (N≤5), manages crash recovery, enforces DAG & collision detection, context budgets |

## 🔧 Install a Plugin

```shell
# Install from this marketplace (first add the marketplace)
claude plugin install get-it-done@get-it-done

# Or install directly from the repo
claude plugin install Unidentified-Lin/plugin-get-done:plugins/get-it-done
```

## 📁 Repository Structure

```
.claude-plugin/
  marketplace.json              # Marketplace registry

plugins/get-it-done/
  .claude-plugin/
    plugin.json                 # Plugin manifest (v0.6.0, Stage 5)
  README.md                     # Full architecture & usage guide
  
  agents/
    planner.md                  # Decompose goal → DAG + PRD (16 rules PR-001..018)
    analyst.md                  # Research single RQ-X independently (5 rules AR-001..005)
    executor.md                 # Implement task T-XXX (11 rules ER-001..011)
    validator.md                # Per-task & milestone validation (6 rules VR-001..006)
    reflector.md                # Post-cycle learning analysis (8 rules RR-001..008)
  
  skills/
    objective/SKILL.md          # Goal bootstrap: state.md schema, workspace init
    continue/SKILL.md           # Dispatcher: Step 0-11 inner loop (crash recovery, DAG check, batch pool, atomic pre-write, spawn, parse, persist, close, loop)
  
  templates/
    team/                       # Per-goal runtime state (state.md, task_queue.md, prd.md, findings/, workspace/)
    team_learnings/
      agent_rules/              # Dynamic rules (A-side, cross-project): planner/analyst/executor/validator/reflector
      patterns.md               # Recurring patterns (provisional + promoted)
      errors.md, handoff_lessons.md, proposed_changes.md
    team/context/               # Per-project learnings (B-side): domain_knowledge, tech_stack, codebase_map, decisions, stakeholder_notes
```

## 🎯 Core Design (v2 Architecture)

- **Dispatcher-only state writes**: Sub-agents emit structured `---agent-return---` YAML; dispatcher alone persists to `state.md`, `task_queue.md`, logs
- **Heterogeneous parallel batches**: Up to 5 in-flight agents (executor + validator + analyst + milestone-validator) in one batch
- **DAG-aware scheduling**: Tasks form explicit dependency graph; no task starts until deps are done
- **Milestone-level validation**: Integration-level acceptance criteria on top of per-task validation
- **Crash recovery**: Three sub-cases (PLANNING timeout, sub-agent interrupted, batch close interrupted) with idempotency guarantees
- **Collision detection**: Source-path overlaps prevented via `Touches` field + dispatcher pool check
- **Context budget guards**: Yield when session context exceeds 80% or 3 batches completed
- **Dual-tier learning**: A-side rules survive plugin updates (cross-project); B-side rules live in `team/context/` (project-specific)
- **Full 繁體中文 compliance**: All CLI output in Traditional Chinese

## 📖 Quick Start

```bash
# Set a goal and launch the first cycle
/objective 製作一個簡易流程圖編輯器，支援拖放、儲存/載入與 PNG 匯出

# Continue (repeatable across sessions)
/continue

# Check status
cat team/state.md                          # Current phase, batch history
cat team/progress_log.md                   # Execution timeline
cat team/validation_log.md                 # Validation verdicts
cat team/context/domain_knowledge.md       # Project learnings
```

## 🔗 Reference

- **Full architecture guide**: `plugins/get-it-done/README.md`
- **Agent rules matrix**: `plugins/get-it-done/templates/team_learnings/agent_rules/*.md`
- **Schema & contracts**: `plugins/get-it-done/templates/team/state.md`

---

**Version**: 0.6.0 | **Stage**: 5 (A/B Learning Architecture Complete) | **Author**: Unidentified-Lin
