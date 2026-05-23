# Team State

_Schema version 2 — batch-aware. The dispatcher (main session, via `/continue`) owns all writes to this file. Sub-agents MUST NOT edit `team/state.md`._

## State Machine

```yaml
schema_version: 2
phase: IDLE                  # IDLE | PLANNING | ANALYZING | EXECUTING | REPORTING | COMPLETE | AWAITING_HUMAN
status: WAITING              # WAITING | RUNNING
batch_id: null               # e.g. "B0007" when a batch is in flight; null otherwise
batch_started_at: null       # ISO timestamp written before dispatcher spawns the batch
batch_ended_at: null         # ISO timestamp written after dispatcher persists batch results
active_agents: []            # see schema below; populated while batch_id != null
goal_set: false
last_updated: null           # ISO timestamp — set whenever dispatcher rewrites this block
```

### `active_agents` entry schema

```yaml
- role: executor             # executor | validator | analyst | planner | reflector
  mode: null                 # validators: task | milestone (Stage 3+); others: null
  task_id: T-007             # task ID, milestone ID (e.g. M2), or req_id (analyst) — null for planner
  scratch: team/workspace/exec-T-007/    # executor-only; validator/analyst/planner: null
  started_at: 2026-05-23T15:04:11Z
```

Parallelism (Stage 3): `1 <= len(active_agents) <= 5` while `status: RUNNING`. EXECUTING batches are heterogeneous — a single batch may mix per-task validators (`role: validator, mode: task`), milestone validators (`role: validator, mode: milestone`), rework executors, and new-pending executors. Planner and Analyst phases remain N=1; parallel Analyst unlocks in Stage 4.

## Phase Definitions

| Phase | Description |
|-------|-------------|
| `IDLE` | No active goal. Waiting for `/objective`. |
| `PLANNING` | Planner decomposing goal into a task DAG, writing PRD / metrics, optionally requesting research. |
| `ANALYZING` | Dispatcher fans out one or more Analyst sub-agents (one per `research_request`). |
| `EXECUTING` | Dispatcher mixes Executor / Validator / milestone-validator / rework Executors across batches until all tasks reach `done`. |
| `REPORTING` | Dispatcher writes `[GOAL_COMPLETE]` summary and flips to `COMPLETE`. |
| `COMPLETE` | All tasks `done`. Reflector may still be running independently; result does NOT gate completion. |
| `AWAITING_HUMAN` | A blocker was raised (validator escalated to `blocked`, DAG malformed, dependency deadlock, planner explicit). |

Reflector is **not** a phase; it runs once after `REPORTING → COMPLETE` as an independent post-cycle sub-agent.

## Transition Rules

```
IDLE           → PLANNING        (goal_set = true)
PLANNING       → ANALYZING       (planner emitted research_requests)
ANALYZING      → PLANNING        (all analyst batches returned; planner re-runs)
PLANNING       → EXECUTING       (task_queue ready, metrics ready, DAG validates)
EXECUTING      → EXECUTING       (next batch — mix of executors, validators, reworks, milestone validators)
EXECUTING      → REPORTING       (all tasks done AND all milestones validated)
REPORTING      → COMPLETE        (dispatcher writes [GOAL_COMPLETE]; spawns reflector independently)
COMPLETE       → IDLE            (cleared by next /objective)
any            → AWAITING_HUMAN  (validator escalates blocked, DAG check fails, dependency deadlock, executor blocker)
AWAITING_HUMAN → previous-phase  (human resolves block via state.md edit or new /objective)
```

## Batch lifecycle (dispatcher contract)

The dispatcher follows this sequence for every batch:

1. **Plan the batch** — read state.md and task_queue.md; compute the actionable pool (see `skills/continue/SKILL.md`); pick up to N work items (Stage 1: N=1).
2. **Pre-write state (atomic, before spawn)** — set `status: RUNNING`, allocate next `batch_id`, fill `active_agents` (with `started_at`, `task_id`, `scratch` per entry), set `batch_started_at`, clear `batch_ended_at`. For each task being claimed, set `Claimed_by` / `Claimed_at` in task_queue.md. Do NOT increment `Attempts` yet — that happens on result.
3. **Spawn sub-agents** in a single assistant message (parallel Task calls).
4. **Collect results** — every sub-agent return MUST contain a `---agent-return---` … `---end---` fenced YAML block (schema below). Free-form prose outside that block is ignored by the dispatcher.
5. **Persist batch results** — for each returned sub-agent, dispatcher updates task_queue.md (Status, Artifact, Validation Results append, Attempts increment, clear Claimed_by/Claimed_at), appends to validation_log.md / progress_log.md, and finally writes `batch_ended_at` + `status: WAITING` + `active_agents: []` + appends a `## Batch <id>` block to the bottom of state.md.
6. **Decide next phase** — based on updated task_queue, set `phase` (may stay EXECUTING, advance to REPORTING, fall back to PLANNING for rework escalations, or trip AWAITING_HUMAN).

## Crash detection contract

A crash is `status == RUNNING` AND `batch_ended_at == null`. On entry the dispatcher detects this with three sub-cases (Stage 5+):

**Sub-case 0: PLANNING singleton crash (Stage 5+)**
- Condition: `phase == PLANNING` AND `status == RUNNING` AND `batch_ended_at == null`
- Detection: Planner is N=1 (singleton) and never writes `Claimed_by` markers. Presence of RUNNING + PLANNING signals potential crash.
- Recovery: If `batch_started_at` is recent (<5 min old), assume planner is still working; exit and retry `/continue` in ~30s. If stale (≥5 min), assume planner crashed mid-execution; reset phase back to `PLANNING`, set `status=WAITING`, append `[CRASH_DETECTED]` to progress_log, and exit so planner restarts on next tick.

**Sub-case A: Sub-agent batch interrupted (Stage 3+)**
- Condition: `status == RUNNING` AND `batch_ended_at == null` AND `claimed_set` is non-empty (where `claimed_set` = tasks/milestones/RQs with `Claimed_by != null`)
- Recovery: Re-spawn **every item in claimed_set** using the same identifiers (task_id, scratch dir for executors, req_id for analysts). Re-spawn is safe because:
  - Executor scratch dirs are keyed by `task_id` — re-runs overwrite their own files, never another task's.
  - `Attempts` was NOT incremented before spawn, so re-spawn keeps the same attempt number.
  - `validation_log.md` entries are dedup-keyed on `(task_id, attempt_no)` — a re-spawn that completes adds at most one new entry per task.
  - Analyst findings files are per-RQ and overwrite cleanly; RQ stays `Status: open`.
  - The dispatcher resets `batch_started_at` to the recovery time and resets `active_agents` to match the re-spawned set; old `batch_id` is reused.

**Sub-case B: Batch close interrupted (Stage 3+)**
- Condition: `status == RUNNING` AND `batch_ended_at == null` AND `claimed_set` is empty (work was persisted but batch envelope not closed)
- Recovery: Clean up stale `Claimed_by` markers (especially fulfilled RQs with leftover `Claimed_by`), close the batch envelope, and proceed to next tick derivation.

Old (pre-v2) state.md files without `schema_version` or `batch_id` are unmigrated. If `/continue` reads a v1 file, it emits an error pointing the user at `/objective` to reset and exits.

## Agent-return YAML contract

Every sub-agent (executor / validator / analyst — and planner when spawned by dispatcher) MUST end its run by emitting exactly one fenced YAML block of this shape (other prose may surround it but the dispatcher parses only between the two markers):

```yaml
---agent-return---
role: executor                    # executor | validator | analyst | planner
task_id: T-007                    # executor: T-XXX; validator: T-XXX or M-XXX; analyst: omit (use req_id instead); planner: omit
status: completed                 # completed | failed | needs_clarification
artifact: team/workspace/exec-T-007/result.md   # path written by this sub-agent; "" if none
notes: 一句到三句話的人類可讀摘要               # short; long prose belongs in the artifact

# validator-only fields:
mode: task                        # task | milestone (Stage 3+; matches the mode in the spawn prompt)
verdict: pass                     # pass | fail
fail_reasons:                     # required when verdict == fail; each item maps to a metrics criterion id or PRD ref
  - "criterion C2: button missing aria-label"
escalate_to_blocked: false        # validator's signal that further rework is unlikely to converge
# milestone-validator-only field (omit when mode: task):
task_ids_to_rework:               # required when mode: milestone AND verdict: fail; tasks that need to be re-executed
  - T-003                         # one entry per task whose work the milestone reviewer found defective in integration
  - T-005                         # may be empty when the milestone failure is structural (then dispatcher falls back to PLANNING)

# planner-only fields:
next_phase_request: EXECUTING     # EXECUTING (DAG ready) | ANALYZING (research_requests written) | REPORTING (no work needed)
research_request_ids: []          # populated when next_phase_request == ANALYZING

# analyst-only fields (omit task_id for analysts; use req_id instead):
req_id: RQ-1                      # required for analyst; replaces task_id
---end---
```

The dispatcher rejects any return missing this block with `[BAD_RETURN]` in progress_log.md and treats the task as crashed (re-spawn on next tick).

## Batch handoff log (appended to bottom of this file)

Each completed batch appends:

```markdown
## Batch B0007 — 2026-05-23T15:04:11Z → 2026-05-23T15:06:42Z
- executor T-007 → completed, artifact: team/workspace/exec-T-007/result.md
next_phase: EXECUTING
intent: spawn validator T-007 next tick.
```

Sub-agents do NOT append to this log; dispatcher does. Older batches are historical noise and may be trimmed by future reflection cycles; the dispatcher never reads them — it derives the next batch from task_queue.md state alone.

---

_(No active batch — team is IDLE.)_
