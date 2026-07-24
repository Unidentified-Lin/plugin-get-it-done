# Manual Fallback Procedures — `/continue` dispatcher

> **Load when**: `gid.py` is unavailable (Python missing) or a subcommand exits 2 / prints `{"error": ...}` for the step named below. Perform the matching procedure by hand instead, and log `<ISO> [GID_FALLBACK] <reason>` once to progress_log.md (per Step 0.5 in `SKILL.md`).

Each section below corresponds to a step in `SKILL.md` that has a script fast-path. Read only the section you need.

## Step 3 fallback — Truncate-check

- `wc -l .get-it-done/progress_log.md > 400` → append all but the last 200 lines to `.get-it-done/archive/progress_log.md`, keep last 200 lines; append `<ISO> [TRUNCATE] progress_log.md from N to 200 (archived)`.
- `wc -l .get-it-done/validation_log.md > 500` → same with `.get-it-done/archive/validation_log.md`, keep last 250 lines.
- A-side patterns.md > 200 lines: defer to Reflector — do NOT auto-truncate.

The archive preserves the append-only audit trail *within this goal worktree* (`/objective` keeps progress_log / validation_log across a goal reset/replace and across `/adjust` — they are per-goal-worktree, not merged across distinct goals) while keeping the live files small. Idempotent — no edits if under the caps.

## Step 4 fallback — DAG pre-check

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

## Step 5 fallback — Pick the actionable batch

```
N_MAX := 5                              # hard cap; do not raise

PHASE_BRANCH_PLANNING:
    IF phase == IDLE:
        EXIT with "沒有活躍目標 — 使用 /objective <goal> 設定目標"
    IF phase == AWAITING_HUMAN:
        EXIT with the most recent [BLOCKER] / [BAD_DAG] / [BAD_MILESTONE] / blocked-task summary from progress_log.md.
        Append the hint: "若要修訂目標或補充需求，使用 /adjust <修訂訊息>。"
    IF phase == COMPLETE:
        EXIT cleanly
    IF phase == REPORTING:
        run report_and_reflect(); EXIT

    IF phase == PLANNING:
        batch := [{ role: planner, task_id: null, scratch: null }]      # singleton
        GOTO step 6

    IF phase == ANALYZING:
        # Parallel analysts, one per open RQ, up to N_MAX.
        # PR-012 guarantees the open RQs are independent of each other (planner enforces).
        open_rqs := every entry in .get-it-done/research_requests.md with Status: open AND Claimed_by == null,
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
    #   tasks_done  — MULTI-task milestone: all tasks done, no validator in flight, AND
    #                 either no VR entries yet OR latest VR was fail without escalate_to_blocked
    #   validated   — latest VR verdict == pass, OR SINGLE-task milestone whose lone task is
    #                 done (auto-validated — no milestone validator spawned; per-task validation
    #                 already covered it and there is no cross-task integration to check)
    #   blocked     — latest VR escalate_to_blocked == true
    #
    # Milestone gate (downstream blocking):
    #   active_ms := lowest M_k where milestone_status(M_k) != validated
    #               ("lowest" = numeric compare on the integer after M: M2 < M10)
    #   A task whose Milestone > active_ms cannot start until active_ms reaches `validated`.

    pool := []                          # heterogeneous — order = priority

    # P1: per-task validators — drain `executed` (frees downstream pending tasks fastest)
    FOR t IN task_queue WHERE t.Status == executed, ordered by t.Created asc:
        pool.append({ role: validator, mode: task, task_id: t.id, scratch: null })

    # P2: milestone validators — any milestone whose tasks are all done but not yet validated.
    # Single-task milestones never reach `tasks_done` (they derive straight to `validated`),
    # so they are skipped here automatically — no milestone-validator spawn for a milestone
    # that has no cross-task integration to check.
    FOR M IN milestones WHERE milestone_status(M) == tasks_done,
                              ordered by M.id ascending:
        pool.append({ role: validator, mode: milestone, task_id: M.id, scratch: null })

    # P3 & P4: Executors (rework and new) — collision-aware (unified collision detection)
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
                      scratch: ".get-it-done/workspace/exec-" + t.id + "/" })
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
                      scratch: ".get-it-done/workspace/exec-" + t.id + "/" })
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

## Step 6 fallback — atomic pre-write + claims

Replaces `claim-batch` when the script is down. Do all of the following before spawning (Step 7); the state.md rewrite and every task_queue.md claim may be several Edit calls in one turn but MUST all complete first.

**batch-id**: read the highest existing `## Batch` block in state.md (and the current `batch_id:`) and increment; if none, start at `B0001`.

**Rewrite state.md YAML block** (preserving everything below it):

```yaml
schema_version: 2
phase: <unchanged>
status: RUNNING
batch_id: <next>
batch_started_at: <ISO now>
batch_ended_at: null
active_agents:                          # one entry per work item in `batch`
  - role: <item.role>
    mode: <task|milestone>              # validators only; omit for others
    task_id: <item.task_id>
    scratch: <item.scratch>             # null for non-executor
    started_at: <ISO now>
goal_set: <unchanged>
last_updated: <ISO now>
```

**Then claim every item** (do NOT touch `Attempts` yet):

- `executor`: task `Claimed_by: exec-<task_id>`, `Claimed_at: <ISO now>`, `Status: claimed`; ensure `.get-it-done/workspace/exec-<task_id>/` exists. **Worktree assignment** (worktree git_mode, source-touching task): **sequential** (`max_parallel<=1` OR only 1 source executor this batch) → the task's worktree IS the goal worktree (do NOT call `worktree-add`); **parallel** (`max_parallel>1` AND ≥2 source executors) → `python3 "$GID_PY" worktree-add <task_id> --base "$GID_BASE"`, note the returned `path` (idempotent).
- `validator mode:task`: task `Claimed_by: val-<task_id>`, `Claimed_at: <ISO now>`, `Status: validating`.
- `validator mode:milestone`: milestone `Claimed_by: mval-<milestone_id>`, `Claimed_at: <ISO now>`; per-task `Status: done` untouched (Step 9 flips only on `task_ids_to_rework`). No persisted milestone `Status:` field.
- `analyst`: RQ `Claimed_by: analyst-<RQ-id>`, `Claimed_at: <ISO now>`; `Status: open` (flips to `fulfilled` on persist).
- `planner`: no task_queue change.

## Step 9 fallback — persist every return by hand

Replaces `persist-return`. Initialise `planned_pause_list := []`. BAD_RETURN items skip persistence (just clear `Claimed_by`/`Claimed_at`, revert `Status` to pre-claim).

**Executor return:**
- Set `Artifact: <return.artifact>` (or null if `return.status != completed`); increment `Attempts` by 1; clear `Claimed_by`, `Claimed_at`.
- `Status: executed` if `return.status == completed` (artifact may be null for `code`/`config` tasks — their deliverable is the changed source in `Touches`). Note: this fires on **any** completed return — a deliberate change from the pre-Phase-6 rule (which advanced only when an artifact was present OR the type was `code`/`config`, leaving other completed-but-empty returns stuck at `claimed`); the per-task validator now judges an empty result instead.
- `Status: blocked` if `return.status == failed` — append `[BLOCKER] T-XXX: <notes>` to progress_log.md; worktree mode → `python3 "$GID_PY" worktree-drop T-XXX --keep-branch`.
- Append `<ISO> [EXEC_DONE] T-XXX attempt=N artifact=<path> status=<status>` to progress_log.md.
- **Git (worktree mode), Status became `executed`:** sequential source task (goal worktree) → no git call now (committed on validator PASS); parallel source task → `python3 "$GID_PY" worktree-commit-wip T-XXX --attempt <Attempts>`; no-`Touches` task → run the stray-edit guard `python3 "$GID_PY" check-stray-edits T-XXX --revert`; if `dirty_source` non-empty, append those paths to `Touches`, append `[TOUCHES_UNDERDECLARED] T-XXX <paths>`, set `Status: needs_rework` (clear `Artifact`).

**Validator return (`mode: task`):**
- Append a `Validation Results` entry `{ attempt_no: <Attempts>, verdict, fail_reasons, escalate_to_blocked, notes, at }`.
- Append `VAL-XXX` to validation_log.md (next monotonic VAL; dedup-key `(task_id, attempt_no)` — skip if present).
- Clear `Claimed_by`, `Claimed_at`.
- `verdict == pass` → `Status: done`; worktree source task: sequential → `python3 "$GID_PY" goal-commit-task T-XXX`; parallel → `python3 "$GID_PY" worktree-merge T-XXX` (on `{ok:false,reason:"conflict",files}` → `Status: needs_rework`, clear `Artifact`, `[MERGE_CONFLICT] T-XXX <files>`, carry files into next rework; worktree kept).
- `verdict == fail` AND not escalate → `Status: needs_rework`, clear `Artifact` (keep worktree).
- `verdict == fail` AND escalate → `Status: blocked`; `[BLOCKER] T-XXX escalated by validator after N attempts`; worktree → `worktree-drop T-XXX --keep-branch`.

**Validator return (`mode: milestone`):** milestone status is derived — do NOT write a milestone `Status:` field.
- Increment milestone `ValidatorAttempts` by 1, then append `Validation Results` `{ attempt_no: <ValidatorAttempts>, verdict, fail_reasons, task_ids_to_rework, escalate_to_blocked, notes, at }`; clear `Claimed_by`, `Claimed_at`.
- Append `MVAL-XXX` to validation_log.md (dedup-key `(milestone_id, attempt_no)`).
- `verdict == pass` → no per-task change; worktree → `python3 "$GID_PY" consolidate-milestone <M>`. If the milestone has `PauseAfter: true`, append `{ milestone_id, reason: <PauseReason> }` to `planned_pause_list`.
- `verdict == fail`, not escalate, `task_ids_to_rework` non-empty → set each listed task `Status: needs_rework`, clear `Artifact`.
- `verdict == fail`, not escalate, `task_ids_to_rework` empty (structural failure) → leave VR intact, flip `phase = AWAITING_HUMAN`, append `[BAD_MILESTONE] <milestone_id> structural fail (no rework path); awaiting human decision`.
- `verdict == fail` AND escalate → `phase = AWAITING_HUMAN`; `[BLOCKER] <milestone_id> escalated by milestone validator`.

**Analyst return:** flip RQ `Status: fulfilled`, clear `Claimed_by`/`Claimed_at`; confirm `.get-it-done/findings/<req_id>.md` exists (else BAD_RETURN — leave `Status: open`, `Claimed_by: null`). Append `[ANALYST_DONE] <req_id>`.

**Planner return:** read `next_phase_request` — `ANALYZING` (confirm RQ IDs `open` → `phase = ANALYZING`), `EXECUTING` (confirm task_queue + metrics populated, run the **plan audit gate** `references/plan-audit-gate.md` before flipping), `REPORTING` (rare). Append `[PLAN_DONE] next=<next_phase_request>`.
