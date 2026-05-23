---
name: continue
description: Continue the autonomous agent team's work on the active goal. Runs the batch-aware dispatcher inner loop — picks up to N actionable work items (executors, validators, analysts, milestone validators, rework), spawns them in parallel via the Agent tool, persists results, and repeats until phase ∈ {COMPLETE, AWAITING_HUMAN, IDLE}. Usage:/continue (no arguments).
---

You are executing **/continue** — the **batch-aware dispatcher** for the autonomous agent team. You are the only writer of shared state files (`team/state.md`, `team/task_queue.md`, `team/research_requests.md`, `team/progress_log.md`, `team/validation_log.md`). Sub-agents emit a structured `---agent-return---` YAML block; you parse it and persist the changes.

**Parallelism**: fan-out cap is **N = 5** per batch.
- **EXECUTING** batches are heterogeneous — may mix per-task validators, milestone validators, reworks, and new executors.
- **ANALYZING** batches are homogeneous (all analysts) — one analyst per open RQ, up to N. Planner's `research_requests.md` is the source of truth; each analyst writes its own `team/findings/RQ-X.md`, so per-analyst writes are disjoint by design.
- **PLANNING** remains N=1 (planner is a singleton role).
Milestone validators gate downstream milestones: a task in milestone `M_k` cannot start until every `M_1..M_{k-1}` has been milestone-validated.

All state lives under `team/` in the **project's working directory** (the user's repo, NOT the plugin install directory). Spawnable sub-agents: `planner`, `analyst`, `executor`, `validator`, `reflector`. Fall back to `get-it-done:<name>` only on a bare-name collision.

## Step 0: Bootstrap (defensive, idempotent)

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — refusing to read templates from / }"
: "${CLAUDE_PLUGIN_DATA:?CLAUDE_PLUGIN_DATA is not set — refusing to write learnings to / }"

# A — cross-project agent-team learnings
mkdir -p "${CLAUDE_PLUGIN_DATA}/team_learnings/agent_rules"
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team_learnings/" "${CLAUDE_PLUGIN_DATA}/team_learnings/"

# B — per-project state + scratch workspace
mkdir -p team/context team/findings team/workspace
rsync -a --ignore-existing "${CLAUDE_PLUGIN_ROOT}/templates/team/" team/
```

`team/workspace/` (per-sub-agent scratch) and `team/findings/` (per-research-request findings) are sub-agent-owned write surfaces; the dispatcher creates the directories but never writes inside them.

If `team/state.md` is missing after bootstrap, abort with an error.

## Step 1: Schema version check

Read the YAML block at the top of `team/state.md`. If `schema_version` is missing or `< 2`, this is a pre-v2 file from an older plugin version:

> "team/state.md 使用舊 schema。執行 `/objective <goal>` 來重設為 v2（這會保留 progress_log、validation_log、context/ 和 A-side learnings）。"

Then exit.

## Step 2: Crash recovery

`status == RUNNING AND batch_ended_at == null` means the previous batch was interrupted. Three sub-cases — distinguish carefully.

```
IF state.status == RUNNING AND state.batch_ended_at == null:
    
    # Sub-case 0 (NEW): PLANNING singleton crash detection
    # PLANNING phase has no Claimed_by markers (planner is N=1, never spawned via Claimed pattern).
    # If status=RUNNING and phase=PLANNING, we have a PLANNING crash.
    IF state.phase == PLANNING:
        IF state.batch_started_at and (now - state.batch_started_at) < 5min:
            # Recent crash; assume planner is still working — we need real wall-clock
            # time to elapse before re-checking, so stop and let the user re-issue /continue.
            append "<ISO> [CRASH_WAIT] PLANNING singleton still working; user should retry /continue shortly" to progress_log.md
            EXIT (real-time wait — dispatcher cannot make progress by looping immediately)
        ELSE:
            # Stale PLANNING batch (>5min old); assume planner crashed mid-execution
            # Restore safety: clear any partial task_queue or research_requests state
            # and restart PLANNING from scratch
            append "<ISO> [CRASH_DETECTED] PLANNING singleton timeout; restarting PLANNING phase" to progress_log.md
            atomically rewrite state.md: status=WAITING, phase=PLANNING, batch_ended_at=<now>, 
                                        batch_id=null, active_agents=[], last_updated=<now>
            # DO NOT modify task_queue.md or research_requests.md yet — let planner re-read on next tick
            GOTO step 3 (continue this same invocation with clean PLANNING state)
    
    claimed_tasks := every task in task_queue.md with Claimed_by != null
    claimed_milestones := every milestone in task_queue.md ## Milestones with Claimed_by != null
    claimed_rqs := every RQ in research_requests.md with Claimed_by != null AND Status: open
                   (Note: Status: fulfilled RQs with stale Claimed_by are handled separately in sub-case B)
    claimed := claimed_tasks ∪ claimed_milestones ∪ claimed_rqs

    IF claimed is non-empty:
        # Sub-case A: sub-agents were spawned but their results were not persisted.
        # Their work (if any) is lost from the dispatcher's perspective — Attempts was
        # not yet incremented (for executors), no VR entry was appended (for validators),
        # no Status flip (for analysts), so a fresh attempt re-runs cleanly.
        # Per-item Claimed_by / Claimed_at fields are STILL set on the persisted records
        # (that's how we detect this case), so we do NOT re-run Step 6's claim writes.
        append "<ISO> [CRASH_DETECTED] batch=<state.batch_id> claimed=[<ids>]" to progress_log.md
        rewrite state.md YAML atomically: status=RUNNING, keep batch_id,
                                          set batch_started_at=<now>, batch_ended_at=null,
                                          active_agents derived from claimed items (role + mode inferred
                                          from Claimed_by prefix:
                                            "exec-"     → executor (any task)
                                            "val-"      → validator, mode: task
                                            "mval-"     → validator, mode: milestone
                                            "analyst-"  → analyst)
        batch := items reconstructed from `claimed` (with scratch path derived for executors)
        JUMP DIRECTLY to step 7 — skip steps 5 (selection) and 6 (claim pre-write).
        Step 7 spawns; Step 8/9 persist; Step 10 closes; recovery completes the original batch.

    ELSE:
        # Sub-case B: per-item persistence in Step 9 already ran (Claimed_by cleared on
        # every item, Status/Attempts/Validation Results updated, VAL/MVAL entries appended,
        # RQ status flipped to fulfilled) but the batch close in Step 10 did not. Work is
        # durably persisted; only the batch envelope is unclosed.
        append "<ISO> [CRASH_CLOSE_ONLY] batch=<state.batch_id> — persisted but not closed; reconstructing close." to progress_log.md
        
        # Clean up stale Claimed_by on fulfilled RQs (Fix A2)
        # If an RQ is marked fulfilled but still has Claimed_by set, it means Step 9 flipped Status
        # but Step 10's close didn't run, so the claim marker wasn't cleared. Clear it now.
        FOR each RQ in research_requests.md:
            IF RQ.Status == fulfilled AND RQ.Claimed_by != null:
                set RQ.Claimed_by = null
                set RQ.Claimed_at = null
        rewrite research_requests.md with cleaned RQ entries
        
        atomically rewrite state.md: status=WAITING, batch_ended_at=<now>, active_agents=[], last_updated=<now>
        append a placeholder Batch block to state.md:
            ## Batch <state.batch_id> — <state.batch_started_at> → <now> (closed after crash recovery)
            (per-item results already persisted; see progress_log + validation_log for detail)
            next_phase: <state.phase>
            intent: re-derive on this tick from task_queue.md + research_requests.md state.
        proceed to step 3 (clean tick)
ELSE:
    proceed to step 3
```

This split closes the validator-rerun edge case automatically — sub-case B never re-spawns a validator whose verdict already landed in `validation_log.md`, so the `(task_id, attempt_no)` dedup never has to arbitrate two different verdicts on the same attempt. Re-spawn (sub-case A) is safe by the idempotency rules in `team/state.md` (executor scratch dir keyed by task_id; Attempts not yet incremented; validation_log dedup on `(task_id, attempt_no)` / `(milestone_id, attempt_no)`; analyst writes to a per-RQ file `team/findings/RQ-X.md` that overwrites cleanly on re-run because `Status: open` still holds — a fulfilled RQ is never re-spawned).

## Step 3: Truncate-check (no archive folder — direct truncation)

- `wc -l team/progress_log.md > 400` → keep last 200 lines; append `<ISO> [TRUNCATE] progress_log.md from N to 200`.
- `wc -l team/validation_log.md > 500` → keep last 250 lines; append `<ISO> [TRUNCATE] validation_log.md from N to 250`.
- A-side patterns.md > 200 lines: defer to Reflector — do NOT auto-truncate.

Idempotent — no edits if under the caps.

## Step 4: DAG pre-check

If `phase ∈ {EXECUTING, REPORTING}` AND `team/task_queue.md` has any task entries, run:

```
all_ids := every "### <ID>:" heading in task_queue.md
FOR EACH task t:
    FOR EACH dep IN t.Dependencies:
        IF dep == t.id → DAG_VIOLATION (self-ref)
        IF dep NOT IN all_ids → DAG_VIOLATION (orphan)
# Cycle check: classic DFS / topo-sort over (task → its deps).
IF any cycle → DAG_VIOLATION

IF any violation:
    append to progress_log.md: "<ISO> [BAD_DAG] <one-line description>"
    set state.phase = PLANNING; status = WAITING
    EXIT — planner will re-run on next /continue
```

This is defensive; planner self-audit should catch this first, but the dispatcher is the last gate.

## Step 5: Pick the actionable batch (Stage 3: heterogeneous, up to N work items)

```
N_MAX := 5                              # hard cap; do not raise

PHASE_BRANCH_PLANNING:
    IF phase == IDLE:
        EXIT with "沒有活躍目標 — 使用 /objective <goal> 設定目標"
    IF phase == AWAITING_HUMAN:
        EXIT with the most recent [BLOCKER] / [BAD_DAG] / [BAD_MILESTONE] / blocked-task summary from progress_log.md
    IF phase == COMPLETE:
        EXIT cleanly
    IF phase == REPORTING:
        run report_and_reflect(); EXIT

    IF phase == PLANNING:
        batch := [{ role: planner, task_id: null, scratch: null }]      # singleton
        GOTO step 6

    IF phase == ANALYZING:
        # Stage 4: parallel analysts, one per open RQ, up to N_MAX.
        # PR-012 guarantees the open RQs are independent of each other (planner enforces).
        open_rqs := every entry in team/research_requests.md with Status: open AND Claimed_by == null,
                    ordered by RQ-id ascending
        IF open_rqs is empty:
            # Two sub-cases:
            #   (a) some RQs are open AND Claimed_by != null → in flight, not picked here;
            #       should have been caught by Step 2 crash check. If we get here with
            #       claimed-but-not-in-flight RQs, treat as crash.
            #   (b) every RQ has Status: fulfilled → research round complete; back to PLANNING.
            stale_claimed := every RQ with Status: open AND Claimed_by != null
            IF stale_claimed non-empty:
                re-enter step 2 logic
            set phase = PLANNING; GOTO step 2 (continue this invocation — next tick spawns planner)
        batch := []
        FOR rq IN open_rqs[: N_MAX]:
            batch.append({ role: analyst, task_id: rq.RQ-id, scratch: null })
        GOTO step 6

PHASE_BRANCH_EXECUTING:
    # Milestone status is DERIVED on every tick (no persisted Status: field on milestones).
    # See task_queue.md "Derivation rule":
    #   validating  — M.Claimed_by != null
    #   pending     — any task in M.Tasks has Status != done
    #   tasks_done  — all tasks done, no validator in flight, AND
    #                 either no VR entries yet OR latest VR was fail without escalate_to_blocked
    #   validated   — latest VR verdict == pass
    #   blocked     — latest VR escalate_to_blocked == true
    #
    # Milestone gate (downstream blocking):
    #   active_ms := lowest M_k where milestone_status(M_k) != validated
    #   A task whose Milestone > active_ms cannot start until active_ms reaches `validated`.

    pool := []                          # heterogeneous — order = priority

    # P1: per-task validators — drain `executed` (frees downstream pending tasks fastest)
    FOR t IN task_queue WHERE t.Status == executed, ordered by t.Created asc:
        pool.append({ role: validator, mode: task, task_id: t.id, scratch: null })

    # P2: milestone validators — any milestone whose tasks are all done but not yet validated
    FOR M IN milestones WHERE milestone_status(M) == tasks_done,
                              ordered by M.id ascending:
        pool.append({ role: validator, mode: milestone, task_id: M.id, scratch: null })

    # P3 & P4: Executors (rework and new) — collision-aware [FIX N2: unified collision detection]
    # Pre-declare collision-tracking set (includes validators but only source-touching executors need check)
    source_touching_executors := []     # {task_id, Touches} of all executors already in pool
    
    # P3: rework executors — oldest first (converge stalled loops)
    FOR t IN task_queue WHERE t.Status == needs_rework, ordered by t.Created asc:
        # Collision check: rework executors must also respect Touches
        IF t.Touches exists AND non-empty:
            collides_with := null
            FOR already IN source_touching_executors:
                IF t.Touches ∩ already.Touches is non-empty:
                    collides_with = already.task_id
                    break
            IF collides_with != null:
                # Defer to next batch
                append "<ISO> [DEFER] T-<t.id> rework deferred (touches conflict with T-<collides_with>)" to progress_log.md
                continue (skip)
        
        pool.append({ role: executor, task_id: t.id,
                      scratch: "team/workspace/exec-" + t.id + "/" })
        IF t.Touches exists AND non-empty:
            source_touching_executors.append({ task_id: t.id, Touches: t.Touches })

    # P4: new executors — pending tasks whose deps are all `done` AND whose milestone == active_ms
    FOR t IN task_queue WHERE t.Status == pending
                          AND every dep in t.Dependencies has Status: done
                          AND t.Milestone == active_ms,
                          ordered by (Priority desc, Created asc):
        # Collision check: verify t.Touches doesn't overlap with any already-claimed executor
        IF t.Touches exists AND non-empty:
            collides_with := null
            FOR already IN source_touching_executors:
                IF t.Touches ∩ already.Touches is non-empty:
                    collides_with = already.task_id
                    break
            IF collides_with != null:
                # Defer to next batch
                append "<ISO> [DEFER] T-<t.id> deferred (touches conflict with T-<collides_with>)" to progress_log.md
                continue (skip)
        
        pool.append({ role: executor, task_id: t.id,
                      scratch: "team/workspace/exec-" + t.id + "/" })
        IF t.Touches exists AND non-empty:
            source_touching_executors.append({ task_id: t.id, Touches: t.Touches })

    IF pool is empty:
        # No work left — terminal checks.
        IF every task has Status: done AND every milestone has milestone_status == validated:
            set phase = REPORTING; run report_and_reflect(); EXIT
        IF any task has Status: blocked:
            set phase = AWAITING_HUMAN; EXIT with the blocked-task summary
        IF any task has Status: claimed OR validating:
            re-enter step 2 logic                       # stale claim — treat as crash
        # Otherwise: deps / milestone gate unsatisfied with nothing in flight = deadlock
        set phase = AWAITING_HUMAN; append "<ISO> [BLOCKER] dependency_or_milestone_deadlock" to progress_log.md; EXIT

    # Heterogeneous slice: take first min(N_MAX, len(pool)) entries.
    # A single batch can now mix per-task validators, milestone validators, reworks, and new executors.
    batch := first min(N_MAX, len(pool)) entries of pool
    GOTO step 6
```

### Heterogeneous batch — what's safe and what isn't

The batch is allowed to mix roles because every work item writes to a **disjoint write surface**:

| Role | Write surface | Conflict risk |
|---|---|---|
| Per-task validator | none (verdict in agent-return only) | none |
| Milestone validator | none (verdict in agent-return only) | none |
| Executor (any task) | `team/workspace/exec-<task_id>/` — task-id-keyed | none vs peers in the same batch |
| Project-source-touching executor | project source paths declared in the task description | guarded by **PR-013** in planner rules: tasks with overlapping source paths MUST be made DAG-dependent so they never co-occur in the same batch. Validators don't write to project source. |

Order within the pool is **priority**, not arbitrary — validators come first so executed tasks unblock downstream pendings ASAP, then milestone validators (closing milestones unblocks the next milestone's pool), then reworks (converge stalled loops), then new pendings. Stage 3 still cannot peek ahead to see what would maximize total throughput across multiple ticks; this is a greedy, single-tick scheduler.

## Step 6: Atomic pre-write (state + claim every task in the batch)

Generate the next `batch_id` (monotonic — read the highest existing `## Batch` block in state.md and increment; if none, start at `B0001`).

```
Rewrite state.md YAML block (preserving everything below the block):
    schema_version: 2
    phase: <unchanged>
    status: RUNNING
    batch_id: <next>
    batch_started_at: <ISO now>
    batch_ended_at: null
    active_agents:                          # one entry per work item in `batch`
      - role: <item.role>
        task_id: <item.task_id>
        scratch: <item.scratch>             # null for non-executor
        started_at: <ISO now>
      - ...                                 # repeat for every item in batch (length 1..N_MAX)
    goal_set: <unchanged>
    last_updated: <ISO now>
```

Then for **every** item in `batch` (do all claims atomically inside one task_queue.md rewrite — multiple Edit calls in the same assistant turn before the spawn message is fine, but they MUST all complete before Step 7):

- `executor` item: set the task's `Claimed_by: exec-<task_id>`, `Claimed_at: <ISO now>`, `Status: claimed`. Do NOT touch `Attempts` yet. Ensure `team/workspace/exec-<task_id>/` exists.
- `validator` item with `mode: task`: set the task's `Claimed_by: val-<task_id>`, `Claimed_at: <ISO now>`, `Status: validating`.
- `validator` item with `mode: milestone`: in the `## Milestones` section of task_queue.md, set the milestone's `Claimed_by: mval-<milestone_id>`, `Claimed_at: <ISO now>`. The tasks inside the milestone keep their `Status: done` — milestone-mode validation does NOT touch per-task status fields directly (Step 9 may flip them to needs_rework based on `task_ids_to_rework` in the agent-return). The milestone has no persisted `Status:` field; derivation in Step 5 will see `Claimed_by != null` and return `"validating"`.
- `analyst` item: in `team/research_requests.md`, set the matching RQ entry's `Claimed_by: analyst-<RQ-id>`, `Claimed_at: <ISO now>`. Leave `Status: open` (it flips to `fulfilled` on persist in Step 9). Do all RQ claims in the same rewrite as the state.md atomic pre-write.
- `planner` item: no task_queue change.

Heterogeneous batches are normal in Stage 3 — mixed roles in `batch` are expected.

## Step 7: Spawn the batch (parallel Agent calls in ONE assistant message)

For every item in `batch`, issue an Agent tool call. **All calls MUST be in the same assistant message** so they execute in parallel — splitting them across messages serializes them and defeats the fan-out.

Per-item prompt template:

```
You are <role>. Read your role definition under agents/<role>.md (in this plugin).

Inputs for this run:
  task_id: <item.task_id>                 (planner: null; analyst: RQ-X; executor/validator: T-XXX or M-X)
  scratch: <item.scratch>                 (executor only — your write surface)
  batch_id: <batch_id>

Read your declared inputs, perform your work, write your artifacts to the paths listed in your
role definition (executor → scratch dir; analyst → team/findings/<req_id>.md; planner →
team/prd.md / team/task_queue.md / team/metrics.md / team/research_requests.md as appropriate;
validator → no artifact).

Terminate by emitting exactly one fenced `---agent-return---` YAML block at the end of your
output, conforming to the contract in team/state.md ("Agent-return YAML contract").

DO NOT edit team/state.md, team/progress_log.md, or team/validation_log.md.
DO NOT read other sub-agents' scratch dirs or findings files even if you can see them in your
filesystem — they belong to peers running concurrently in this same batch.
The dispatcher persists shared state based on your agent-return.
```

Use `subagent_type: get-it-done:<role>` (namespaced form to avoid any bare-name collision with other plugins or user-registered roles).

The dispatcher waits for ALL items to return before proceeding to Step 8. There is no per-item early collection — Claude Code returns all parallel Task results together when the slowest one finishes.

## Step 8: Parse every agent-return in the batch

Iterate over every sub-agent result returned in this batch. For each, extract exactly one fenced block between `---agent-return---` and `---end---` using robust pattern matching.

```
Pattern (multiline + case-sensitive):
    /^---agent-return---\s*\n(.*?)\n---end---\s*$/ms

FOR EACH sub-agent result in batch:
    IF pattern matches:
        → Extract captured block (line 1)
        → Parse as YAML
        IF YAML parse succeeds:
            Return is valid; proceed to Step 9 for persistence
        ELSE:
            Malformed YAML inside block; log and treat as BAD_RETURN (below)
    ELSE IF result contains BOTH "---agent-return---" AND "---end---" (markers present but pattern didn't match):
        → Warn in progress_log: "<ISO> [BAD_RETURN] role=<role> task=<task_id> reason=malformed_block_format (markers present but pattern mismatch)"
        → Treat as BAD_RETURN
    ELSE:
        Agent likely crashed or didn't output markers at all; log and treat as BAD_RETURN

BAD_RETURN handling:
    append "<ISO> [BAD_RETURN] role=<role> task=<task_id> reason=<why>" to progress_log.md
    Mark this item as BAD_RETURN — Step 9 will skip its per-task persistence
    (DO NOT increment Attempts; DO NOT change task Status) and clear Claimed_by/Claimed_at
    so the task is re-picked on the next tick.
```

A BAD_RETURN from one item does NOT abort the rest of the batch — every well-formed return is still persisted in Step 9. The bad item's task simply reverts to its pre-claim Status (`pending`, `needs_rework`, or `executed`) and the next tick will re-spawn it.

**Agent contract note**: Agents MUST output the `---agent-return---` block at the **end** of their response, exactly as documented in `team/state.md`. This is the ONLY field the dispatcher reads; all analysis and reasoning must be written to artifact files, not to stdout.

## Step 9: Persist the batch results

For each well-formed return (BAD_RETURN items skip this and just have Claimed_by/Claimed_at cleared + Status reverted to pre-claim):

**Executor return:**
- Set task `Artifact: <return.artifact>` (or null if return.status != completed).
- Increment `Attempts` by 1.
- Clear `Claimed_by`, `Claimed_at`.
- Set `Status: executed` if return.status == completed and return.artifact present.
- Set `Status: blocked` if return.status == failed (executor cannot complete) — also append `[BLOCKER] T-XXX: <notes>` to progress_log.md.
- Append `<ISO> [EXEC_DONE] T-XXX attempt=N artifact=<path> status=<status>` to progress_log.md.

**Validator return (`mode: task`):**
- Append a new entry to the task's `Validation Results` array with `{ attempt_no: <Attempts at time of this run>, verdict, fail_reasons, escalate_to_blocked, notes, at }`.
- Append a `VAL-XXX` entry to `team/validation_log.md` (next monotonic VAL number; dedup-key is `(task_id, attempt_no)` — if an entry with that key exists, skip the append).
- Clear `Claimed_by`, `Claimed_at`.
- If `verdict == pass`: set `Status: done`.
- If `verdict == fail` AND `escalate_to_blocked == false`: set `Status: needs_rework`, clear `Artifact`.
- If `verdict == fail` AND `escalate_to_blocked == true`: set `Status: blocked`. Append `[BLOCKER] T-XXX escalated by validator after N attempts` to progress_log.md.

**Validator return (`mode: milestone`):**

Milestone status is derived (see task_queue.md "Derivation rule") — the dispatcher does NOT write a `Status:` field for milestones. Instead it persists the validator's verdict in the milestone's `Validation Results` array and (where applicable) flips per-task statuses; the next read of milestone_status() will reflect those changes naturally.

- In `## Milestones` section, **first increment** milestone `ValidatorAttempts` by 1, then append to the milestone's `Validation Results` array with `{ attempt_no: <milestone.ValidatorAttempts after increment>, verdict, fail_reasons, task_ids_to_rework, escalate_to_blocked, notes, at }`. Clear `Claimed_by`, `Claimed_at`.
- Append `MVAL-XXX` entry to `team/validation_log.md` (next monotonic MVAL number; dedup-key is `(milestone_id, attempt_no)`).
- If `verdict == pass`: no per-task changes; milestone_status() will derive `validated` from the latest VR entry. Downstream-milestone tasks become eligible on the next tick.
- If `verdict == fail` AND `escalate_to_blocked == false`:
  - If `task_ids_to_rework` is non-empty: for each `task_id` in the list, set that task's `Status: needs_rework`, clear `Artifact`. The next tick's Step 5 will re-pick them as P3 (rework) items. Milestone_status() now derives `pending` (because tasks are no longer all done); once they all re-reach done, derivation flows to `tasks_done` and Step 5 P2 will spawn another milestone validator that reads the appended VR entry as context.
  - If `task_ids_to_rework` is empty (structural failure — validator couldn't name specific tasks to blame):
    **[FIX #3: Preserve diagnostic evidence, escalate to human]** Do NOT clear VR; instead flip to AWAITING_HUMAN so human can review the validator's evidence and decide the next step:
    - Leave the milestone's `Validation Results` intact (evidence is preserved for human review).
    - Flip phase to `AWAITING_HUMAN` (not PLANNING, because this requires human judgment).
    - Append `<ISO> [BAD_MILESTONE] <milestone_id> structural fail (no rework path); awaiting human decision` to progress_log.md.
    - Per-task statuses remain unchanged (`done`); human will read validator verdict in validation_log and either (a) edit task_queue to reshape the milestone, or (b) escalate the goal. Planner will only re-enter when human gives explicit approval (next `/continue` after state.md phase is changed back).
- If `verdict == fail` AND `escalate_to_blocked == true`: flip phase to `AWAITING_HUMAN`. Append `[BLOCKER] <milestone_id> escalated by milestone validator` to progress_log.md. Per-task statuses unchanged; milestone_status() will derive `blocked` from the latest VR entry.

**Analyst return:**
- In `team/research_requests.md`, flip the matching `RQ-X` entry to `Status: fulfilled` and clear `Claimed_by`, `Claimed_at`. Confirm `team/findings/<req_id>.md` exists; if not, treat as `[BAD_RETURN]` (above) — leave the RQ as `Status: open` with `Claimed_by: null` so the next tick re-spawns it.
- Append `<ISO> [ANALYST_DONE] <req_id>` to progress_log.md.

**Planner return:**
- Read `next_phase_request`:
  - `ANALYZING`: confirm `research_requests.md` now has the requested `RQ-` IDs with `Status: open`; set `phase = ANALYZING`.
  - `EXECUTING`: confirm `task_queue.md` and `team/metrics.md` are populated; (Step 4 already DAG-checked, but step 10 will re-run it after we write); set `phase = EXECUTING`.
  - `REPORTING`: rare — only when planner determines the goal is already satisfied; set `phase = REPORTING`.
- Append `<ISO> [PLAN_DONE] next=<next_phase_request>` to progress_log.md.

## Step 10: Close the batch

```
Rewrite state.md YAML block:
    status: WAITING
    batch_ended_at: <ISO now>
    active_agents: []
    last_updated: <ISO now>
    phase: <decided above>

Append to bottom of state.md:
    ## Batch <batch_id> — <batch_started_at> → <batch_ended_at>
    - <role> <task_id> → <return.status / verdict>, artifact: <path or "(none)">     # one line per item
    - <role> <task_id> → ...                                                            # repeat for every batch item
    next_phase: <decided>
    intent: <one-line plan for what the next tick will do (e.g. "validate T-003, T-005, T-007; queue T-009 once deps clear")>

Leave `batch_id` and `batch_started_at` populated as history; the next pre-write (Step 6) overwrites them atomically with `status: RUNNING` and a fresh `batch_id` so the crash check stays sound.
```

Re-run Step 4 (DAG check) if planner just wrote a new task_queue.

## Step 11: Loop or yield

```
Decision tree (checked in order):

1. Terminal phase states: EXIT
   IF phase ∈ {COMPLETE, AWAITING_HUMAN, IDLE}: EXIT

2. Reporting phase: finalize and EXIT
   IF phase == REPORTING: run report_and_reflect(); EXIT
   (report_and_reflect transitions phase to COMPLETE before returning.)

3. Context budget guard — real stopping criterion, not a counter
   IF accumulated sub-agent results exceed 80% of session context budget:
     → Append "[CONTEXT_PAUSE] pausing for recovery; next /continue resumes" to progress_log.md
     → Write state.md with status: WAITING (remain in current phase; the next /continue
       picks up via Step 2 crash recovery)
     → Append context_utilization metric to progress_log.md
     → EXIT (user will manually re-issue /continue when ready, OR a fresh session
       restart is anyway required to clear context)

4. Otherwise — keep going. The dispatcher self-coordinates:
   GOTO step 2 (next inner tick in the SAME /continue invocation)
   This covers both phase transitions (PLANNING→ANALYZING→EXECUTING→REPORTING) and
   consecutive batches within the same phase. There is no artificial batch ceiling —
   the dispatcher runs as long as it can make progress.
```

**Design intent**: `/continue` is the dispatcher; once it starts it owns coordination until it cannot proceed (terminal phase or genuine context exhaustion). It does not yield mid-progress to ask the user to press a button. The only legitimate reasons to stop are: the goal is done, the team is blocked on a human decision, or the session's context budget is genuinely full.

## `report_and_reflect()` — runs once when the goal closes

Reflector is NOT part of the relay. It runs once per goal, after every task reaches `Status: done`.

```
1. Read team/goal.md, team/task_queue.md, last ~20 entries of team/validation_log.md.
2. Append to team/progress_log.md:
     "<ISO> [GOAL_COMPLETE] <goal one-liner>. <N> tasks completed across <M> milestones; first-pass rate <X>/<Y>. Key deliverables: <bullet list of team/workspace/exec-*/ artifact paths>."
3. Rewrite state.md YAML: phase=COMPLETE, status=WAITING, batch_id=null, batch_started_at=null, batch_ended_at=null, active_agents=[], last_updated=<ISO>. Remove the most recent `## Batch` block IFF its `next_phase == REPORTING` (it's now stale).
4. Emit the [GOAL_COMPLETE] paragraph to the user.
5. Spawn reflector via Agent tool. Prompt: "Execute your reflector role per agents/reflector.md. The goal just COMPLETE'd. Analyse validation_log + progress_log + the most recent batch handoffs. Update A-side and B-side learnings per your classification matrix. Do NOT change team/state.md phase. Do NOT emit an agent-return block — your output is the file writes themselves."
6. Reflector returns; EXIT. Reflection failures are logged ([REFLECT_FAIL]) but do NOT roll back COMPLETE.
```

## Dispatcher self-loop principle

**The dispatcher keeps ticking inside a single `/continue` invocation until it cannot proceed.** It does NOT yield back to the user just because some batch counter elapsed. Inner-loop termination is decided by **real conditions**, not arbitrary ceilings:

1. **Terminal phase** — `phase ∈ {COMPLETE, AWAITING_HUMAN, IDLE}` → stop. The work is done, blocked on a human, or absent.
2. **Context exhaustion** — accumulated sub-agent results would overflow the session's context budget → stop. A new `/continue` from the user starts a fresh session that can resume via Step 2 crash-recovery.
3. **Crash-retry wait** — a singleton planner is in flight and the dispatcher needs real wall-clock time to elapse before checking again (Step 2 sub-case 0, recent-crash branch) → stop and let the user re-issue `/continue` when ready.

In every other situation — phase transitions, batch completions, even many batches in a row — the dispatcher loops back to Step 2 and picks the next batch within the same invocation. No `ScheduleWakeup`, no artificial batch cap.

## Exit conditions

- `phase: COMPLETE` — goal achieved.
- `phase: AWAITING_HUMAN` — blocker (DAG, dependency deadlock, validator escalation, planner-flagged).
- `phase: IDLE` — no active goal.
- `[CONTEXT_PAUSE]` — context budget guard tripped. State is preserved (`status: WAITING` in current phase); a fresh `/continue` resumes via crash recovery.
- `[CRASH_WAIT]` — planner singleton recently crashed and we need real time to elapse before retrying. Fresh `/continue` from the user re-checks.

## What the dispatcher does NOT do

- No mid-flight communication with sub-agents (they cannot be interrupted; their result arrives whole).
- No direct edits to executor artifacts, analyst findings, or PRD content — those are sub-agent property.
- No silent retry of a task whose validator returned `escalate_to_blocked: true` — that goes straight to AWAITING_HUMAN.
- Stage 3: heterogeneous batches (mixed per-task validators, milestone validators, reworks, new executors), N≤5. Source-path collisions between parallel executors must be ruled out at planning time by PR-013 in `agent_rules/planner.md` (declare overlapping tasks as DAG-dependent).
- No reflector invocation outside `report_and_reflect()`.

Keep this skill thin in spirit — but recognize that the dispatcher legitimately owns more logic now than in v1, because sub-agents no longer touch shared state. If something feels like it belongs in an agent .md, ask whether moving it would re-introduce concurrent writes to shared files. If yes, it stays here.
