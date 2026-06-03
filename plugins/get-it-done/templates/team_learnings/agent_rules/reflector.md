# Reflector Dynamic Rules

_Learned behavioral rules specific to the Reflector agent._
_Updated by Reflector (self-application). Read by Reflector at the start of every run._

## Rules

### RR-001 | Priority: high
**Rule**: Every reflection cycle MUST touch at least one of: `${CLAUDE_PLUGIN_DATA}/team_learnings/patterns.md`, `${CLAUDE_PLUGIN_DATA}/team_learnings/agent_rules/<name>.md`, `${CLAUDE_PLUGIN_DATA}/team_learnings/errors.md`, `${CLAUDE_PLUGIN_DATA}/team_learnings/handoff_lessons.md`, `${CLAUDE_PLUGIN_DATA}/team_learnings/proposed_changes.md`, or any B-side file under `.get-it-done/context/`. If no actionable finding, append a one-line footer `<!-- cycle <ISO>: no new entries -->` to `${CLAUDE_PLUGIN_DATA}/team_learnings/patterns.md` so silence is explicit, not absent.
**Reason**: A skipped output channel is otherwise indistinguishable from a healthy "considered, decided no" outcome. The path list reflects the v2 A-side layout (`${CLAUDE_PLUGIN_DATA}/team_learnings/`) — there is no `current.md` in v2; v1's single-cycle learning file was replaced by the patterns / errors / agent_rules / handoff_lessons fan-out.

### RR-002 | Priority: high
**Rule**: Decision matrix for fixes:
  - **Proposed plugin-source edit** (`${CLAUDE_PLUGIN_DATA}/team_learnings/proposed_changes.md`) — the agent's literal instruction text inside the plugin (`agents/<name>.md` or `skills/**/SKILL.md`) is wrong, contradictory, or missing. Record the proposed diff; DO NOT attempt to edit the installed plugin files (they live in the read-only plugin cache under `${CLAUDE_PLUGIN_ROOT}`).
  - **Behavioural rule** (`${CLAUDE_PLUGIN_DATA}/team_learnings/agent_rules/<name>.md`) — instruction is correct; agent just needs to remember a nuance. Read live every cycle and persists across plugin updates because it lives in `${CLAUDE_PLUGIN_DATA}`, not `${CLAUDE_PLUGIN_ROOT}`.
  - **Error learning** (`${CLAUDE_PLUGIN_DATA}/team_learnings/errors.md`) — a recurring failure category that future agents must avoid.
  - **Per-project fact** (`.get-it-done/context/{domain_knowledge,tech_stack,codebase_map,decisions,stakeholder_notes}.md`) — a learning that applies only to *this* project. See the classification matrix in `agents/reflector.md`.
  Always classify before writing. Mis-classification leaks structural bugs into permanent behavioural workarounds.
**Reason**: Without a decision matrix, structural bugs get patched as long-term rules and the underlying plugin instructions stay wrong forever.

### RR-003 | Priority: medium
**Rule**: When you propose a plugin-source edit, the entry in `${CLAUDE_PLUGIN_DATA}/team_learnings/proposed_changes.md` must include: target file in plugin source, one-line motivation, the VAL-XXX (or MVAL-XXX, [BLOCKER], [BAD_DAG], [BAD_MILESTONE]) reference that motivates it, and an explicit `Proposed diff` block. Status starts at `awaiting human application to plugin source`.
**Reason**: A proposed change without a concrete diff is just a complaint. The diff is what makes the proposal actionable for the plugin maintainer.

### RR-004 | Priority: medium
**Rule**: When promoting a learning to `patterns.md` (3+ cycles observed), record the source learning IDs explicitly (L-XXX, L-XXX, L-XXX) in the pattern's `Observed in` field.
**Reason**: Promotion provenance must be reconstructable; otherwise patterns become assertions without evidence.

### RR-005 | Priority: high
**Rule**: When editing `${CLAUDE_PLUGIN_DATA}/team_learnings/agent_rules/validator.md`, or proposing a plugin-source edit to `agents/validator.md`, or any rule/instruction that steers Validator behavior, cite **at least two distinct VAL-XXX entries** as evidence. A single contentious validation outcome MUST NOT be enough to mutate Validator's behavior.
**Reason**: Reflector reads `validation_log.md` and writes learnings that worker agents (including Executor) consume — Validator does not read most learnings, but its own rules can be edited by Reflector. A 2-entry evidence threshold prevents one disputed VAL from biasing future judgment through the learnings channel.

### RR-006 | Priority: medium
**Rule**: When analysing parallelization quality, read the historical `## Batch <id>` blocks at the bottom of `.get-it-done/state.md` alongside `validation_log.md`. Patterns to surface as Planner rules: (a) Tasks Planner marked with empty `Dependencies` whose downstream evidence showed silent serial dependence — visible as repeated rework loops where two "independent" tasks keep failing on consistent cross-task contract mismatches. (b) Tasks Planner over-coupled — visible as long stretches of single-task EXECUTING batches when other pending tasks were also eligible (you can confirm by comparing the batch's `active_agents` count to the pool size you can reconstruct from task_queue.md snapshots). (c) Milestones whose Acceptance Criteria were rubber-stamped (validator passed instantly with no real checks) or whose criteria caused fail loops not addressable by any single task — both are PR-014 violations.
**Reason**: v2's value over v1 is parallelism; misshapen DAGs and weak milestone criteria silently regress throughput back to v1 levels without ever surfacing as task-level failures. Batch-block analysis is the only signal that catches these.

### RR-007 | Priority: medium
**Rule**: When a `[CRASH_DETECTED]` or `[CRASH_CLOSE_ONLY]` entry appears in `progress_log.md`, look at WHAT was in the claimed set at the crash point and the state of the next-tick recovery. Recurring crash points (same task type, same role, same phase) suggest dispatcher-side or sub-agent termination bugs — record those as `proposed_changes.md` entries against `skills/continue/SKILL.md` or the relevant agent.md. One-off crashes are tooling noise; >2 in a single goal's progress_log is a signal.
**Reason**: Crash recovery is designed to be invisible when it works. If it's recurring, that's structural — surface it before it becomes accepted background noise.

### RR-008 | Priority: medium
**Rule**: When a milestone validator returned `verdict: fail` with non-empty `task_ids_to_rework`, AND the rework cycle ultimately converged (milestone eventually validated), record the integration defect pattern in `patterns.md` — these are the most valuable learnings because they show v2's milestone layer doing what per-task validation cannot. Common categories: schema mismatch across task boundaries, missing glue code between producer/consumer tasks, contradictory error-handling decisions across tasks. Cite the original milestone's `Validation Results` entry that caught it.
**Reason**: Milestone validators justify their token cost only when they catch defects that per-task validators provably can't. Recording successful catches makes the v2 milestone layer's contribution measurable; conversely, milestones that never catch anything across multiple cycles are PR-014 candidates for criteria sharpening or removal.

## Format

```
### RR-XXX | Priority: high | medium | low
**Rule**: Specific behavioral instruction.
**Reason**: Why this rule exists (what failure it prevents).
```
