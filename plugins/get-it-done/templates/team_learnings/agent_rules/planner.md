# Planner Dynamic Rules

_Learned behavioral rules specific to the Planner agent._
_Updated by Reflector. Read by Planner at the start of every run._

## Rules

### PR-001 | Priority: high
**Rule**: When a task's deliverable will be consumed by a follow-on task, write metrics that demand named, discrete output units (e.g., "each gap must have a named fix tag"). Reference the consumer task explicitly in the acceptance criteria.
**Reason**: Named outputs are directly actionable downstream. Emergent naming is unreliable; lock it into criteria.

### PR-002 | Priority: high
**Rule**: For audit/research/inventory tasks, set the metric "every claim cites file path AND line number" as a hard pass criterion at the 4/5 threshold (not a bonus at 5/5).
**Reason**: Line-level evidence is replicable and should be the floor, not the ceiling, for evidence-based deliverables.

### PR-003 | Priority: medium
**Rule**: When defining the task schema or referencing task statuses, explicitly enumerate the legal vocabulary (`pending | in_progress | completed` for Status; `pending | pass | fail` for Validation Result). Do not assume readers infer it.
**Reason**: Fragmented status vocabulary is a latent silent-break risk.

### PR-004 | Priority: medium
**Rule**: Every task entry must include a `Dependencies:` field — empty list when the task has no upstream prerequisites, otherwise list every task_id whose `done` Status is genuinely required before this task can produce a correct artifact. The dispatcher enforces this gate (a task is only claimed when every listed dep has `Status: done`), so Executor never sees an unmet-dep situation at runtime; Planner's job here is to declare the real dependencies accurately, neither defensively over-coupling (see PR-011) nor omitting genuine prerequisites.
**Reason**: In v2 the dispatcher owns dep-gating, so dep accuracy is purely a planning-time concern. Over-coupling silently serializes parallelizable work; under-coupling lets parallel executors race on artifacts that genuinely need ordering.

### PR-005 | Priority: medium
**Rule**: For design/policy/scaffold tasks, write acceptance criteria that demand machine-readable artifacts (pseudocode, single-unit tables, worked examples with collision rules, grep-friendly log formats). Make "a fresh agent could implement from this alone" an explicit 5/5 bar.
**Reason**: Implementable specs convert "design" into a deployable contract.

### PR-006 | Priority: high
**Rule**: For design/spec plan tasks whose output feeds ≥2 downstream code tasks (especially across milestones), acceptance criteria MUST require an "Implementation Targeting Summary" table at the end of the artifact, mapping each named unit to (target-file, action, downstream-task-ID).
**Reason**: Converts the spec from "describes the system" into a direct work-list for the next Executor.

### PR-007 | Priority: medium
**Rule**: When the task introduces a new schema that pre-existing files conform to, criteria MUST include "ship one worked old-format → new-format conversion example showing a pre-existing instance parses cleanly under the new schema, with absent-field defaults made explicit."
**Reason**: Schema changes are high-risk for silent breakage of legacy data; a worked round-trip example forecloses the entire "does this still parse?" review question class.

### PR-008 | Priority: high
**Rule**: When the goal describes a deliverable product / system / tool / platform / service / application whose feature boundary is NOT exhaustively enumerated by the user, Planner MUST first produce `team/prd.md` containing all 13 sections specified in planner.md ("PRD generation (when needed)"), pass the `## Self-Audit` checklist, and only then write `task_queue.md` and `metrics.md`. Every task must populate `PRD-Ref:` pointing back to the PRD section(s) it implements.
**Reason**: Abstract product goals decomposed directly into tasks consistently cover only the few features the user named and miss the industry-standard Must-Have set — the result is a POC, not a complete tool. The PRD step forces an exhaustive feature inventory before task creation.

### PR-009 | Priority: medium
**Rule**: When the PRD covers a domain with well-known benchmark products (flowchart editors, kanban boards, code editors, dashboards, CRMs, etc.) AND Planner is not confident about the industry-standard Must-Have feature set, Planner MUST first request a `Feature Landscape Research` from Analyst (≥3 comparable products, ≥10 features each, with cited URLs) before writing the PRD's Feature Inventory.
**Reason**: A Planner without domain knowledge produces a subjectively short Must-Have list — the root cause of POC-level planning. Empirical grounding from comparable products closes this gap.

### PR-010 | Priority: high
**Rule**: Before emitting the agent-return, self-check the DAG in `team/task_queue.md`: every `Dependencies:` ID must exist as a `### T-XXX:` heading in the same file; no task may reference itself; the dependency graph must be acyclic (mentally topo-sort it — if you can't order tasks, there is a cycle). Fix violations before terminating. The dispatcher runs the same check defensively; failing it costs a tick and falls phase back to PLANNING.
**Reason**: v2 dispatch is dependency-driven; orphan or cyclic deps stall the entire goal until human intervention.

### PR-011 | Priority: high
**Rule**: An empty `Dependencies: []` is the parallelism lever. Only add a dependency when there is a real "must-finish-first" relationship — artifact reuse, shared data shape, irreversible setup. Do NOT add defensive dependencies "just in case", and do NOT serialize tasks merely because they share a milestone. Re-read each `Dependencies:` list before terminating and ask: does the upstream task's *artifact* genuinely feed the downstream? If no, drop it.
**Reason**: Defensive dependencies silently serialize parallelizable work; in Stage 2+ this is the dominant cause of throughput regression.

### PR-012 | Priority: medium
**Rule**: When requesting research, each `RQ-X` entry in `team/research_requests.md` must be independent of every other open `RQ-`. Interdependent questions (RQ-2 needs RQ-1's answer to even be answerable) MUST be sequenced across two planner→analyst rounds, not batched. Independence is the precondition for parallel Analyst spawn in Stage 4+.
**Reason**: Parallel Analyst spawn assumes per-request independence; coupling them re-creates the serial bottleneck and forces a re-plan after each Analyst returns.

### PR-013 | Priority: high
**Rule**: When two `Type: code` tasks **in the same milestone** would edit overlapping project source paths (same file, or files that depend on each other's symbol-level changes in a way that would cause merge conflicts if applied independently), Planner MUST declare them as dependent in the DAG — pick one as the upstream task and put its ID in the other's `Dependencies:` list. This serializes the two through the DAG and prevents two parallel executors (Stage 2+) from racing on the same file within a single batch. Tasks in **different milestones** are already serialized by the milestone gate (a task in M2 cannot start until M1 is `validated`), so no explicit DAG dependency is needed there. The Task `Description:` should state which files the task is expected to touch so this rule can be applied at planning time, not discovered at validation time.
**Reason**: Parallel executors write to project source independently with no merge step; concurrent edits to the same file within a batch produce silent overwrites or corrupt diffs. Cross-milestone collisions don't have the same risk because the milestone gate enforces serial ordering between milestones.

### PR-014 | Priority: high
**Rule**: For every milestone in `## Milestones`, write `Acceptance Criteria` that name **integration properties** — things that emerge when the milestone's tasks meet, not restatements of per-task criteria. Concrete patterns: end-to-end user journeys spanning ≥2 tasks; cross-task schema / contract agreement (same field name + type at producer and consumer); presence of glue code that wires task A's output into task B's input; absence of dangling references between tasks' artifacts. If no integration property is meaningful for a milestone (truly independent tasks), write `(none — per-task validation is sufficient for this milestone)` explicitly — the milestone validator treats that as a documented pass-through. Do NOT copy per-task criteria into milestone criteria; the milestone validator skips anything already covered per-task.
**Reason**: Milestone validators add value only when they catch what per-task validators cannot. Vague or redundant milestone criteria produce either rubber-stamp passes (wasting a validator spawn) or fail loops that re-litigate already-resolved per-task issues.

### PR-015 | Priority: high
**Rule**: When you are re-spawned after a milestone validator returned `verdict: fail` with empty `task_ids_to_rework` (structural failure; logged as `[BAD_MILESTONE]` in progress_log), this is a **human escalation point** — the dispatcher has already flipped `phase: AWAITING_HUMAN` and preserved all validator evidence in the milestone's `Validation Results` for diagnostic review. You are NOT automatically re-spawned after a structural milestone fail. The human must review the validator's notes in `validation_log.md`, then either: (a) edit `task_queue.md` to reshape the milestone (add/remove tasks, rewrite Acceptance Criteria, clarify acceptance targets), and **explicitly clear the milestone's `Validation Results` array** before saving so the next dispatcher tick does not replay the old fail verdict; or (b) escalate the goal (document in `progress_log.md` why this milestone cannot be satisfied). If human edits task_queue, planner will re-enter on next `/continue` to revalidate the reshape.
**Reason**: Structural failures require human judgment about whether the goal's decomposition is fundamentally flawed or just needs reshaping. Dispatcher escalates immediately to preserve diagnostic evidence; human makes the call rather than relying on planner rules.

### PR-016 | Priority: high
**Rule**: When you re-run after ANALYZING and any incoming `team/findings/RQ-X.md` carries `Confidence: low` on a finding that would be **load-bearing** for the PRD or task decomposition (i.e. you would build Must-Have features, NFRs, or task acceptance criteria on top of that finding), do NOT proceed to EXECUTING by treating the weak finding as fact. Either: (a) open a follow-up `RQ-` in `team/research_requests.md` with a sharper question that targets the gap, then emit `next_phase_request: ANALYZING` to re-run Analyst; or (b) explicitly scope the PRD / task list down so the weak finding is no longer load-bearing (e.g. mark the affected feature as Should-Have or Out-of-Scope) and document the deferment in PRD §12. Confidence-low findings on incidental context (color choices, naming preferences, etc.) are fine to use as-is.
**Reason**: AR-005 makes analysts mark gaps explicitly; this rule closes the loop by ensuring Planner notices. Without it, the AR-005 signal is wasted — Planner builds tasks on phantom findings, executors implement them, validators pass them per criteria, and the gap surfaces only at milestone validation or after goal completion as integration failures.

### PR-017 | Priority: high
**Rule**: For every **code-type task** (`Type: code`), populate the optional `Touches:` field in `task_queue.md` with a list of file paths or directory paths the task is expected to modify. Examples: `["src/auth/*", "tests/auth/*"]`, `["package.json", "tsconfig.json"]`, or `["README.md"]` for doc-only changes. Use this field to help the dispatcher detect file-level collisions at the task-scheduling stage (Stage 5+); two parallel executors in the same heterogeneous batch will be blocked from co-occurring if their `Touches:` lists overlap. For non-code tasks or code tasks that do not modify project source, leave `Touches: []` (empty). This unblocks maximum parallelism within a batch.
**Reason**: (Stage 5+) Parallel executors write independently with no merge step; source-path collisions within a batch cause silent overwrites. Dispatcher-side collision detection (via `Touches`) prevents the conflict at scheduling time rather than discovering it post-hoc as merge conflicts in validation.

### PR-018 | Priority: high
**Rule**: When you are spawned, immediately check the pre-existing files: if `prd.md` exists but lacks the `## Self-Audit` section, OR if `task_queue.md` contains task headings (`### T-XXX:`) but any entry is missing required fields (Status, Milestone, Dependencies, Acceptance Criteria), assume a prior crash left half-written output. In either case: **delete `prd.md`, `task_queue.md`, `metrics.md`, and `research_requests.md`** and restart your planning from scratch using only `goal.md` as input. This ensures crash recovery does not propagate stale partial state forward.
**Reason**: Dispatcher cannot atomically backup/restore planner output in v2 (planner writes to multiple files asynchronously). Planner crash detection is the responsibility of the planner itself — if you see incomplete output, it's unsafe to build on; always rebuild from scratch.

### PR-019 | Priority: high
**Rule**: Default `PauseAfter: false` on every milestone — the dispatcher autopilots through milestones to COMPLETE without stopping. Set `PauseAfter: true` (with a one-line `PauseReason`) ONLY at a milestone whose acceptance genuinely requires human-only judgment that no validator agent (including milestone validator + Claude-for-Chrome browser validation) can substitute: UX feel ("does the animation feel right?"), real-world device testing, stakeholder sign-off, production data correctness review, or irreversible side-effect gates (live deploy, send-money-to-users). For a typical goal, expect 0–1 PauseAfter marks total; >2 is almost certainly over-pausing. Per-task pauses are not supported — if a task needs human review, lift it into its own milestone.
**Reason**: User wants autopilot by default; manual pauses are a planning-time decision, not a runtime convenience. Each PauseAfter forces a human round-trip that breaks momentum, so the bar is "the validator agents literally cannot judge this," not "I'd feel safer if a human looked." Marking too many points defeats the autopilot intent.

## Format

```
### PR-XXX | Priority: high | medium | low
**Rule**: Specific behavioral instruction.
**Reason**: Why this rule exists (what failure it prevents).
```
