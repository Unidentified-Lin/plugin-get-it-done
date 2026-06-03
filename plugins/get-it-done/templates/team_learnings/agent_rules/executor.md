# Executor Dynamic Rules

_Learned behavioral rules specific to the Executor agent._
_Updated by Reflector. Read by Executor at the start of every run._

## Rules

### ER-001 | Priority: high
**Rule**: You do NOT pick your task or re-check its dependencies — the dispatcher (v2 `/continue`) selected your `task_id` for you and has already verified every dep has `Status: done`. Read ONLY your assigned task entry, plus any rows you need to look up its deps' artifacts (e.g. when you need file paths from an upstream task). Do NOT loop over `task_queue.md` "looking for the next pending task" — that was v1 behavior and now causes ownership-semantics breakage when parallel executors are running in the same batch. If a dep's artifact looks corrupted or absent, terminate with `status: failed` and notes describing the inconsistency rather than silently substituting another task.
**Reason**: v1 had every executor scan and pick; v2 has the dispatcher own scheduling. Re-picking inside an executor under v2 can collide with peer executors that the dispatcher is concurrently assigning, corrupting task_queue claim semantics.

### ER-002 | Priority: high
**Rule**: For analysis/audit/research deliverables, every claim must cite a specific file path AND line number (e.g., `validator.md:18`), not just a file name. Treat line-level evidence as a hard requirement, not a bonus. When citing a line range, verify BOTH endpoints (start and end line) against the actual file before writing.
**Reason**: Path+line citations are the dominant quality signal. End-line precision has been a recurring near-miss; verifying both endpoints forecloses it.

### ER-003 | Priority: high
**Rule**: For multi-category research tasks, actively cross-reference 3+ files looking for contradictions (field written by A, ignored by B, absent from C's schema). Single-file observations are baseline; cross-file findings differentiate 5/5 from 3/5.
**Reason**: Cross-file triangulation is the 5/5-defining content on audit/analysis tasks.

### ER-004 | Priority: medium
**Rule**: If a task's output will feed a follow-on task, give each discrete output unit a stable, ALL_CAPS_NAME (e.g., a fix tag, a finding ID). Reference these names in the summary table.
**Reason**: Names reduce handoff ambiguity and make the deliverable directly actionable downstream.

### ER-005 | Priority: high
**Rule**: For design/policy/scaffold tasks, the deliverable MUST be implementable by a fresh agent without further clarification. Ship at least one of: pseudocode algorithm, single-unit column-aligned table, worked example with collision rule, or grep-friendly log-line format. Prose-only design notes score 3/5; machine-readable specs score 5/5.
**Reason**: Implementable specs are the difference between "describes the system" and "is the contract".

### ER-006 | Priority: medium
**Rule**: When the task's scope is narrower than the surrounding goal, explicitly enumerate OUT-OF-SCOPE items by their stable named tags. One-line rationale per excluded item.
**Reason**: Out-of-scope discipline proves full-landscape awareness and pre-empts scope-creep questions.

### ER-007 | Priority: high
**Rule**: For any design or scaffold deliverable whose downstream consumers are ≥2 separate code tasks, append an "Implementation Targeting Summary" table at the end of the artifact: one row per named unit with columns (named-unit, target-file path, action verb, downstream-task-ID). Place it AFTER the body, BEFORE any OUT-OF-SCOPE section.
**Reason**: Converts the spec into a direct work-list for the next Executor.

### ER-008 | Priority: medium
**Rule**: When the artifact introduces a new schema (state.md format, message schema, file-naming convention), include one worked example that takes a pre-existing instance of the old schema and shows it parsing/converting cleanly under the new schema. Make absent-field defaults explicit. Place this in a "Backward Compatibility" subsection.
**Reason**: A worked round-trip example forecloses the entire "does this still parse?" review question class.

### ER-009 | Priority: high
**Rule**: (Detailed artifact storage rules are documented in `agents/executor.md` § "Artifact storage".) The core principle for v2: when two code executors run in the same batch, each operates on its own scratch dir (`.get-it-done/workspace/exec-<task_id>/`), but both may touch the same project source files if their `Touches:` lists overlap. Dispatcher collision detection uses `Touches` to prevent file-level conflicts; do not assume file locks or merge tooling will recover your edits if another executor in the same batch touches the same project path.
**Reason**: Parallel executors in v2 have no inter-batch synchronization; collision avoidance is entirely planning-time (via planner's DAG and dispatcher's collision detection). Write discipline is the only safety guarantee.

### ER-010 | Priority: high
**Rule**: When your task modifies real project source files (not artifact-style deliverables under your scratch dir), ALSO write a `.get-it-done/workspace/exec-<task_id>/CHANGES.md` listing every project file you touched with a one-line rationale. Cite the source paths in your agent-return `notes` so Validator knows to read CHANGES.md to find your work. Do this every time you write outside the scratch dir, even for a single-line edit.
**Reason**: Validators reading only the agent-return `artifact` path won't discover work that lives in project source; a missed CHANGES.md is how parallel executors' real-source edits get silently overlooked at validation time.

### ER-011 | Priority: medium
**Rule**: Do NOT read peer executors' scratch dirs (`.get-it-done/workspace/exec-T-OTHER/`), peer analysts' findings (`.get-it-done/findings/RQ-OTHER.md` other than your assigned RQ), or peer validators' verdicts that haven't been promoted to `.get-it-done/validation_log.md` yet, even if the files are accessible. Your inputs are explicitly declared in `agents/executor.md`; reading sibling state introduces nondeterministic dependence on intra-batch ordering, which Claude Code does not guarantee.
**Reason**: Parallel sub-agents in the same batch may complete in any order; cross-reading peer in-flight state would make your output depend on something the framework does not provide.

## Format

```
### ER-XXX | Priority: high | medium | low
**Rule**: Specific behavioral instruction.
**Reason**: Why this rule exists (what failure it prevents).
```
