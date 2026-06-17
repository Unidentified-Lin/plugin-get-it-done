---
name: continue
description: Continue the autonomous agent team's work on the active goal. Runs the batch-aware dispatcher inner loop — picks up to N actionable work items (executors, validators, analysts, milestone validators, rework), spawns them in parallel via the Agent tool, persists results, and repeats until phase ∈ {COMPLETE, AWAITING_HUMAN, IDLE}. Usage:/continue (no arguments).
---

You are executing **/continue** — the **batch-aware dispatcher** for the autonomous agent team. You are the only writer of shared state files (`.get-it-done/state.md`, `.get-it-done/task_queue.md`, `.get-it-done/research_requests.md`, `.get-it-done/progress_log.md`, `.get-it-done/validation_log.md`). Sub-agents emit a structured `---agent-return---` YAML block; you parse it and persist the changes.

**Parallelism**: fan-out cap is **N = 5** per batch.
- **EXECUTING** batches are heterogeneous — may mix per-task validators, milestone validators, reworks, and new executors.
- **ANALYZING** batches are homogeneous (all analysts) — one analyst per open RQ, up to N. Planner's `research_requests.md` is the source of truth; each analyst writes its own `.get-it-done/findings/RQ-X.md`, so per-analyst writes are disjoint by design.
- **PLANNING** remains N=1 (planner is a singleton role).
Milestone validators gate downstream milestones: a task in milestone `M_k` cannot start until every `M_1..M_{k-1}` has been milestone-validated.

Spawnable sub-agents: `planner`, `analyst`, `executor`, `validator`, `reflector`. Fall back to `get-it-done:<name>` only on a bare-name collision.

## GID_BASE — the active goal's worktree (multi-goal)

Every goal runs in its **own git worktree** under `<repo>.gid-goals/<slug>/` (branch `gid/goal-<slug>`), which contains that goal's `.get-it-done/`. **`GID_BASE` = that worktree's absolute path.** This is how one repo-root window drives a chosen goal, and how multiple windows drive different goals at once.

- **Every `.get-it-done/...` path in this skill is under `$GID_BASE/`** — read/write `"$GID_BASE/.get-it-done/..."`.
- **Pass `--base "$GID_BASE"` to every `python3 "$GID_PY" <cmd>`** EXCEPT `git-preflight`, `goals`, and `goal-worktree-init` (those run at the repo root).
- **Spawn sub-agents with `repo_root = $GID_BASE`** (their cwd / state home).
- **Back-compat:** if `GID_BASE` is unset, base = repo root (legacy single-goal `.get-it-done/`). Everything still works.
- **Terminology:** where steps below say "`_goal`" / "the goal worktree", that means **`$GID_BASE` itself** in multi-goal mode (the goal worktree IS the base; `gid.py` operates there via `--base`), or the legacy `.get-it-done/worktrees/_goal` in back-compat mode. Task worktrees are grouped siblings `<repo>.gid-goals/<slug>-<T>` whose `.get-it-done/` symlinks to `$GID_BASE/.get-it-done/`.

**Resolving GID_BASE (do this first, before Step 0):**
1. If this window already established `GID_BASE` (you set it earlier this session via `/objective` or a prior `/continue`) → reuse it. Validate it still appears in `python3 "$GID_PY" goals`; if gone, re-resolve.
2. Else run `python3 "$GID_PY" goals`:
   - **0 goals** → no isolated goals exist; if a legacy repo-root `.get-it-done/state.md` exists, run in single-goal back-compat (`GID_BASE` unset = repo root). Otherwise tell the user to run `/objective <goal>` and stop.
   - **1 goal** → set `GID_BASE` = its `path`.
   - **≥2 goals** → ask the user which goal (list the slugs) and set `GID_BASE` to the chosen `path`.
3. `export GID_BASE="<path>"` so every command below inherits it.

## Step 0: Bootstrap (defensive, idempotent)

```bash
# Resolve paths (Claude Code: env vars set by harness; Copilot: discover from filesystem)
BOOTSTRAP="${CLAUDE_PLUGIN_ROOT}/skills/objective/scripts/bootstrap.py"   # Copilot: {plugin-root}/skills/objective/scripts/bootstrap.py
PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.copilot/data/get-it-done}"

python3 "$BOOTSTRAP" init --base "${GID_BASE:-.}" --plugin-data "$PLUGIN_DATA"
```

`.get-it-done/workspace/` (per-sub-agent scratch) and `.get-it-done/findings/` (per-research-request findings) are sub-agent-owned write surfaces; the dispatcher creates the directories but never writes inside them.

If `.get-it-done/state.md` is missing after bootstrap, abort with an error.

## Step 0.5: Locate the helper script (deterministic fast-path)

The deterministic computations below (state parse, DAG check, batch selection, log truncation, batch-id allocation) are implemented in a stdlib-only Python script. **Prefer the script over manual derivation** — it removes the highest-risk bookkeeping from the loop.

```bash
GID_PY="${CLAUDE_PLUGIN_ROOT}/skills/continue/scripts/gid.py"   # Copilot: {plugin-root}/skills/continue/scripts/gid.py
python3 "$GID_PY" state    # smoke test; on Windows try `python` if `python3` is absent
```

- Prints JSON → script is usable. Use it in Steps 3, 4, 5, 6, and 9 as documented there. All subcommands run **from the project root** (they read `.get-it-done/` relatively).
- Python unavailable, or the script exits 2 / prints `{"error": ...}` → fall back to the manual procedure kept in each step. Log `<ISO> [GID_FALLBACK] <reason>` once to progress_log.md.
- The script also owns all **git operations** (worktree isolation + commit consolidation, see Steps 0.6/6/9): `git-preflight`, `worktree-add|-commit-wip|-merge|-drop|-gc|-reset-all`, `check-stray-edits`, `consolidate-milestone|-final`. These mutate the repo and `git_state.json`; you call them, the script does the deterministic git work and returns `{ok: ...}`.
- The script is read-only for `.get-it-done/*.md` state — every write to `state.md` / `task_queue.md` / `research_requests.md` remains yours. (`git_state.json` is the script's own; never hand-edit it.)

## Step 0.6: Git mode + goal worktree + reaper

```
preflight := python3 "$GID_PY" git-preflight        # at repo root (no --base)
IF preflight.is_git AND preflight.worktree_supported:
    git_mode := worktree
    # Re-assert the goal worktree (idempotent). Multi-goal: it already exists (created by /objective)
    # — this confirms it + re-hides its .get-it-done after a crash. slug = basename($GID_BASE).
    IF GID_BASE set:  python3 "$GID_PY" goal-worktree-init --slug "$(basename "$GID_BASE")"
    ELSE:             python3 "$GID_PY" goal-worktree-init        # back-compat legacy _goal
ELSE:
    git_mode := fallback
    append once-per-goal "<ISO> [GIT_FALLBACK] non-git/unusable; source executors write the main tree directly (no rollback)" to "$GID_BASE/.get-it-done/progress_log.md"
max_parallel := "$GID_BASE/.get-it-done/git_state.json" `max_parallel` (default 5 — parallel by default)
python3 "$GID_PY" worktree-gc --base "$GID_BASE"     # reaper: remove any TASK worktree not tied to a live task. NEVER reaps the goal worktree. Idempotent.
```

`git_mode` + `max_parallel` drive Step 5/6/7/9. **Parallelism is driven by the plan, not a manual knob** — `max_parallel` is only a CEILING (default 5 = the batch cap); the pool naturally parallelizes whatever the DAG allows:
- **Independent tasks** (deps satisfied, same active milestone, **non-overlapping `Touches`**) run **concurrently** — up to `min(max_parallel, max_worktrees, batch cap 5)`. Each gets its own **task worktree** branched from `gid/goal-<slug>`, squash-merged back on validator pass.
- **Dependent / same-file tasks** automatically **serialize** — deps gate them, and `Touches` collision detection keeps overlapping-source tasks out of the same batch.
- When only **one** source task is eligible this tick, it runs directly in `_goal` (no task worktree — cheaper). Executor and its validator always share that one task's worktree.
- Set `max_parallel: 1` in `git_state.json` for fully sequential. In `worktree` mode, #6 (validator↔executor build race) is structurally impossible — each runs in its own worktree (or `_goal`). In `fallback` mode, Step 5's pool applies a scheduling guard instead.

## Step 1: Schema version check

Read the YAML block at the top of `.get-it-done/state.md`. If `schema_version` is missing or `< 2`, this is a pre-v2 file from an older plugin version:

> ".get-it-done/state.md 使用舊 schema。執行 `/objective <goal>` 來重設為 v2（這會保留 progress_log、validation_log、context/ 和 A-side learnings）。"

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

**Worktree-mode crash safety**: `goal-worktree-init` is idempotent — it reuses an existing `_goal` and re-asserts the shared-`.get-it-done` symlink after a crash. Sequential `goal-commit-task` no-ops on no changes; parallel `worktree-add` reuses an existing task worktree; `worktree-merge` is atomic and returns `skipped: already_merged` if the branch is gone, so a crash between merges loses nothing durable and never double-merges. Step 0.6's reaper removes orphaned TASK worktrees (never `_goal`). A benign duplicate `worktree-commit-wip --attempt N` after re-spawn is skipped by its no-change detection.

This split closes the validator-rerun edge case automatically — sub-case B never re-spawns a validator whose verdict already landed in `validation_log.md`, so the `(task_id, attempt_no)` dedup never has to arbitrate two different verdicts on the same attempt. Re-spawn (sub-case A) is safe by the idempotency rules in `.get-it-done/state.md` (executor scratch dir keyed by task_id; Attempts not yet incremented; validation_log dedup on `(task_id, attempt_no)` / `(milestone_id, attempt_no)`; analyst writes to a per-RQ file `.get-it-done/findings/RQ-X.md` that overwrites cleanly on re-run because `Status: open` still holds — a fulfilled RQ is never re-spawned).

## Step 3: Truncate-check (trimmed lines are archived, not lost)

**Script path**: `python3 "$GID_PY" truncate-logs` — archives trimmed lines to `.get-it-done/archive/<logname>.md` (append) before truncating, and appends the `[TRUNCATE]` marker itself. Done.

**Manual fallback**:
- `wc -l .get-it-done/progress_log.md > 400` → append all but the last 200 lines to `.get-it-done/archive/progress_log.md`, keep last 200 lines; append `<ISO> [TRUNCATE] progress_log.md from N to 200 (archived)`.
- `wc -l .get-it-done/validation_log.md > 500` → same with `.get-it-done/archive/validation_log.md`, keep last 250 lines.
- A-side patterns.md > 200 lines: defer to Reflector — do NOT auto-truncate.

The archive preserves the append-only audit trail *within this goal worktree* (`/objective` keeps progress_log / validation_log across a goal reset/replace and across `/adjust` — they are per-goal-worktree, not merged across distinct goals) while keeping the live files small. Idempotent — no edits if under the caps.

## Step 4: DAG pre-check

If `phase ∈ {EXECUTING, REPORTING}` AND `.get-it-done/task_queue.md` has any task entries:

**Script path**: `python3 "$GID_PY" dag-check` →
- `violations` non-empty → take the `[BAD_DAG]` branch below with the violation strings.
- `warnings` non-empty (e.g. `touches-overlap`) → append `<ISO> [DAG_WARN] <warning>` lines to progress_log.md but DO NOT block — the runtime collision check in Step 5 already defers overlapping executors.
- `ok: true` → proceed.

**Manual fallback**:

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

**Script path** (EXECUTING phase): `python3 "$GID_PY" pool --base "$GID_BASE" --git-mode <git_mode> --max-worktrees 8 --max-parallel <max_parallel>` computes everything below deterministically — derived milestone statuses, the priority-ordered pool (P1→P4) with Touches collision deferral, the sequentiality cap, the worktree hard-cap / fallback race guard, and the first-5 `batch` slice. Map its output to the decisions:
- `batch` non-empty → that IS your batch; log each `deferred` entry as `<ISO> [DEFER] <task_id> <reason>` (reasons: `touches conflict with ...`, `max_parallel` = more source executors than `max_parallel` allows this tick, `wt_cap` = task-worktree hard-cap backpressure, `fallback_race_guard` = #6 guard in non-git mode); GOTO Step 6.
- `batch` empty AND `all_done_and_validated: true` → set phase = REPORTING; run report_and_reflect(); EXIT.
- `batch` empty AND `any_blocked: true` → set phase = AWAITING_HUMAN; EXIT with blocked-task summary.
- `batch` empty AND `any_in_flight: true` → stale claim; re-enter Step 2 logic.
- `batch` empty otherwise → dependency/milestone deadlock → AWAITING_HUMAN (as in the fallback below).

**Script path** (ANALYZING phase): `python3 "$GID_PY" rqs` → spawn one analyst per `open_unclaimed[:5]`; `open_claimed` non-empty with nothing in flight → crash path; everything fulfilled → back to PLANNING. Clear any `fulfilled_with_stale_claim` markers.

Milestone ordering is **numeric** on the integer after `M` (`M2 < M10`); never compare milestone IDs as plain strings. The script already does this.

**Manual fallback**:

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
        # Stage 4: parallel analysts, one per open RQ, up to N_MAX.
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
    #   tasks_done  — all tasks done, no validator in flight, AND
    #                 either no VR entries yet OR latest VR was fail without escalate_to_blocked
    #   validated   — latest VR verdict == pass
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

### Heterogeneous batch — what's safe and what isn't

The batch is allowed to mix roles because every work item writes to a **disjoint write surface**:

| Role | Write surface | Conflict risk |
|---|---|---|
| Per-task validator | none (verdict in agent-return only) | none |
| Milestone validator | none (verdict in agent-return only) | none |
| Executor (any task) | `.get-it-done/workspace/exec-<task_id>/` — task-id-keyed | none vs peers in the same batch |
| Project-source-touching executor | project source paths declared in the task description | guarded by **PR-013** in planner rules: tasks with overlapping source paths MUST be made DAG-dependent so they never co-occur in the same batch. Validators don't write to project source. |

Order within the pool is **priority**, not arbitrary — validators come first so executed tasks unblock downstream pendings ASAP, then milestone validators (closing milestones unblocks the next milestone's pool), then reworks (converge stalled loops), then new pendings. Stage 3 still cannot peek ahead to see what would maximize total throughput across multiple ticks; this is a greedy, single-tick scheduler.

## Step 6: Atomic pre-write (state + claim every task in the batch)

Generate the next `batch_id`: `python3 "$GID_PY" batch-id` (monotonic over `## Batch` history + current `batch_id`). Manual fallback: read the highest existing `## Batch` block in state.md and increment; if none, start at `B0001`.

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

- `executor` item: set the task's `Claimed_by: exec-<task_id>`, `Claimed_at: <ISO now>`, `Status: claimed`. Do NOT touch `Attempts` yet. Ensure `.get-it-done/workspace/exec-<task_id>/` exists. **Worktree assignment** (worktree git_mode, source-touching task):
  - **Sequential** (`max_parallel<=1`, OR this batch has only 1 source executor): the task's worktree IS `_goal` — `.get-it-done/worktrees/_goal`. Do NOT call `worktree-add`.
  - **Parallel** (`max_parallel>1` AND this batch has ≥2 source executors): call `python3 "$GID_PY" worktree-add <task_id>` (branches `gid/<task_id>` from `gid/goal-<slug>`) and note the returned `path` (idempotent — reuses an existing worktree on crash-recovery / rework; recreates from the surviving branch for a blocked-retry).
- `validator` item with `mode: task`: set the task's `Claimed_by: val-<task_id>`, `Claimed_at: <ISO now>`, `Status: validating`.
- `validator` item with `mode: milestone`: in the `## Milestones` section of task_queue.md, set the milestone's `Claimed_by: mval-<milestone_id>`, `Claimed_at: <ISO now>`. The tasks inside the milestone keep their `Status: done` — milestone-mode validation does NOT touch per-task status fields directly (Step 9 may flip them to needs_rework based on `task_ids_to_rework` in the agent-return). The milestone has no persisted `Status:` field; derivation in Step 5 will see `Claimed_by != null` and return `"validating"`.
- `analyst` item: in `.get-it-done/research_requests.md`, set the matching RQ entry's `Claimed_by: analyst-<RQ-id>`, `Claimed_at: <ISO now>`. Leave `Status: open` (it flips to `fulfilled` on persist in Step 9). Do all RQ claims in the same rewrite as the state.md atomic pre-write.
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
  repo_root: $GID_BASE                     (the goal worktree; worktree-mode source executors/validators only)
  worktree: <_goal path OR task worktree path>   (worktree-mode source executors/validators only — cwd here for code/build/test)

Read your declared inputs, perform your work, write your artifacts to the paths listed in your
role definition (executor → scratch dir; analyst → .get-it-done/findings/<req_id>.md; planner →
.get-it-done/prd.md / .get-it-done/task_queue.md / .get-it-done/metrics.md / .get-it-done/research_requests.md as appropriate;
validator → no artifact).

Terminate by emitting exactly one fenced `---agent-return---` YAML block at the end of your
output, conforming to the contract in .get-it-done/state.md ("Agent-return YAML contract").

DO NOT edit .get-it-done/state.md, .get-it-done/progress_log.md, or .get-it-done/validation_log.md.
DO NOT read other sub-agents' scratch dirs or findings files even if you can see them in your
filesystem — they belong to peers running concurrently in this same batch.
The dispatcher persists shared state based on your agent-return.
```

Use `subagent_type: get-it-done:<role>` (namespaced form to avoid any bare-name collision with other plugins or user-registered roles).

**Platform note — sub-agents MUST run isolated, not inline** (see `platform-adapter.md` Section 4). On Claude Code the `Agent` tool guarantees this. On **GitHub Copilot CLI**, delegate to the discoverable custom agent **by name** (e.g. `get-it-done-executor`) and instruct it to run in its own context and return only its `---agent-return---` block — otherwise Copilot runs the work inline and breaks the relay. If Copilot does not run delegations concurrently, spawn fewer at once (down to one-at-a-time); flow control is unaffected.

**Worktree-mode source items** (executor or task-validator for a source-touching task in `worktree` git_mode): set `worktree` to the path from Step 6 — the **goal worktree** (`$GID_BASE`) when this task runs sequentially, or its **task worktree** (`<repo>.gid-goals/<slug>-<T>`) in parallel mode. The executor and its validator for the same task always get the SAME worktree. Include the `repo_root` (= `$GID_BASE`) + `worktree` lines above, and add this instruction: "Make all source-code edits and run all build/test commands inside `worktree` (cwd there). When `worktree` is a task worktree, its `.get-it-done/` is a **symlink to the goal worktree's `.get-it-done/`** (`$GID_BASE/.get-it-done/`); when `worktree` IS the goal worktree, its `.get-it-done/` is right there. Either way read/write all get-it-done state and your scratch dir through `repo_root/.get-it-done/...`. Do NOT run any git command; the dispatcher owns git." Milestone-mode validators run on the goal worktree (`$GID_BASE`, whose branch holds the merged source); all non-source items omit both lines.

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

**Agent contract note**: Agents MUST output the `---agent-return---` block at the **end** of their response, exactly as documented in `.get-it-done/state.md`. This is the ONLY field the dispatcher reads; all analysis and reasoning must be written to artifact files, not to stdout.

## Step 9: Persist the batch results

For each well-formed return (BAD_RETURN items skip this and just have Claimed_by/Claimed_at cleared + Status reverted to pre-claim):

**Executor return:**
- Set task `Artifact: <return.artifact>` (or null if return.status != completed).
- Increment `Attempts` by 1.
- Clear `Claimed_by`, `Claimed_at`.
- Set `Status: executed` if return.status == completed and return.artifact present.
- Set `Status: blocked` if return.status == failed (executor cannot complete) — also append `[BLOCKER] T-XXX: <notes>` to progress_log.md. **In worktree mode**, `python3 "$GID_PY" worktree-drop T-XXX --keep-branch` (remove the worktree, keep `gid/T-XXX` for forensics).
- Append `<ISO> [EXEC_DONE] T-XXX attempt=N artifact=<path> status=<status>` to progress_log.md.
- **Git (worktree mode), when Status became `executed`:**
  - **Sequential source task** (ran in `_goal`): no git call now — the edits sit in `_goal`'s working tree and are committed on validator PASS (below). The `_goal` worktree is never reaped mid-goal, so executor→validator share it (fixes the early-reap issue).
  - **Parallel source task** (had its own task worktree): `python3 "$GID_PY" worktree-commit-wip T-XXX --attempt <Attempts>` (durably commits the task worktree's changes to `gid/T-XXX`; no-ops cleanly if unchanged).
  - **No `Touches`** (artifact-only, possible under-declaration): run the stray-edit guard `python3 "$GID_PY" check-stray-edits T-XXX --revert`. If `dirty_source` is non-empty, the planner under-declared `Touches`: append those paths to the task's `Touches` field (you own task_queue), append `<ISO> [TOUCHES_UNDERDECLARED] T-XXX <paths>` to progress_log.md, and set `Status: needs_rework` (clear `Artifact`). The `--revert` already removed the stray edits, so nothing lingers — the rework re-runs in `_goal`/a task worktree next tick.

**Validator return (`mode: task`):**
- Append a new entry to the task's `Validation Results` array with `{ attempt_no: <Attempts at time of this run>, verdict, fail_reasons, escalate_to_blocked, notes, at }`.
- Append a `VAL-XXX` entry to `.get-it-done/validation_log.md` (next monotonic VAL number; dedup-key is `(task_id, attempt_no)` — if an entry with that key exists, skip the append).
- Clear `Claimed_by`, `Claimed_at`.
- If `verdict == pass`: set `Status: done`. **In worktree mode, if the task is source-touching**, commit it onto the goal branch:
  - **Sequential** (ran in `_goal`): `python3 "$GID_PY" goal-commit-task T-XXX` → one commit on `gid/goal-<slug>` (no-ops on no changes).
  - **Parallel** (own task worktree): `python3 "$GID_PY" worktree-merge T-XXX` → squash-merge into `gid/goal-<slug>` (worktree + branch removed). On `{ok:false, reason:"conflict", files:[...]}` → set `Status: needs_rework` instead of done, clear `Artifact`, append `<ISO> [MERGE_CONFLICT] T-XXX <files>` to progress_log.md, and carry the conflict files into the next rework as a fail-reason (the task worktree is kept for the retry).
- If `verdict == fail` AND `escalate_to_blocked == false`: set `Status: needs_rework`, clear `Artifact`. (Worktree mode: keep the worktree — the rework reuses it.)
- If `verdict == fail` AND `escalate_to_blocked == true`: set `Status: blocked`. Append `[BLOCKER] T-XXX escalated by validator after N attempts` to progress_log.md. **In worktree mode**: `python3 "$GID_PY" worktree-drop T-XXX --keep-branch`.

**Validator return (`mode: milestone`):**

Milestone status is derived (see task_queue.md "Derivation rule") — the dispatcher does NOT write a `Status:` field for milestones. Instead it persists the validator's verdict in the milestone's `Validation Results` array and (where applicable) flips per-task statuses; the next read of milestone_status() will reflect those changes naturally.

- In `## Milestones` section, **first increment** milestone `ValidatorAttempts` by 1, then append to the milestone's `Validation Results` array with `{ attempt_no: <milestone.ValidatorAttempts after increment>, verdict, fail_reasons, task_ids_to_rework, escalate_to_blocked, notes, at }`. Clear `Claimed_by`, `Claimed_at`.
- Append `MVAL-XXX` entry to `.get-it-done/validation_log.md` (next monotonic MVAL number; dedup-key is `(milestone_id, attempt_no)`).
- If `verdict == pass`: no per-task changes; milestone_status() will derive `validated` from the latest VR entry. Downstream-milestone tasks become eligible on the next tick. **In worktree mode**, consolidate this milestone's per-task commits into one: `python3 "$GID_PY" consolidate-milestone <M>` (safe here — all `M`'s tasks are merged and no downstream worktree exists yet; skips itself cleanly if already one commit or the branch is pushed). **Planned-pause check**: if the milestone entry has `PauseAfter: true`, **append** an entry `{ milestone_id: <M-X>, reason: <milestone.PauseReason> }` to a transient list `planned_pause_list` (initialise to `[]` at the start of Step 9 if not already set). The list is a list — not a single value — because a heterogeneous batch can contain multiple milestone validators, and each passing PauseAfter milestone must be announced (the previous single-value design clobbered earlier entries). Step 11 will read this list and EXIT cleanly after Step 10 closes the batch (soft pause: phase remains EXECUTING, status WAITING — the user's next /continue resumes the next downstream milestone naturally).
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
- In `.get-it-done/research_requests.md`, flip the matching `RQ-X` entry to `Status: fulfilled` and clear `Claimed_by`, `Claimed_at`. Confirm `.get-it-done/findings/<req_id>.md` exists; if not, treat as `[BAD_RETURN]` (above) — leave the RQ as `Status: open` with `Claimed_by: null` so the next tick re-spawns it.
- Append `<ISO> [ANALYST_DONE] <req_id>` to progress_log.md.

**Planner return:**
- Read `next_phase_request`:
  - `ANALYZING`: confirm `research_requests.md` now has the requested `RQ-` IDs with `Status: open`; set `phase = ANALYZING`.
  - `EXECUTING`: confirm `task_queue.md` and `.get-it-done/metrics.md` are populated, then run the **plan audit gate** below before flipping the phase.
  - `REPORTING`: rare — only when planner determines the goal is already satisfied; set `phase = REPORTING`.
- Append `<ISO> [PLAN_DONE] next=<next_phase_request>` to progress_log.md.

**Plan audit gate (quality check before EXECUTING):**

The autonomous path has no human plan review — this gate is its substitute. It catches the most expensive failure mode (a whole goal executed against vague or unverifiable criteria) for the cost of one extra spawn.

```
audit_fails := count of [PLAN_AUDIT_FAIL] lines in progress_log.md SINCE the latest
               [NEW_GOAL] or [GOAL_REFINED] line (current goal only)
IF audit_fails >= 2:
    # Avoid planner↔reviewer ping-pong; two strikes and we proceed with a warning.
    append "<ISO> [PLAN_AUDIT_SKIPPED] max audit rounds reached; proceeding to EXECUTING"
    rm -f .get-it-done/plan_audit.md
    set phase = EXECUTING
ELSE:
    spawn get-it-done:plan-reviewer (single Agent call, NOT a batch member) with mode `queue-audit`
    and absolute paths to: .get-it-done/task_queue.md, .get-it-done/metrics.md,
    .get-it-done/goal.md, .get-it-done/prd.md (if it exists).
    Parse its ---agent-return--- block (role: plan-reviewer, verdict: pass|fail, fail_reasons).
    IF verdict == pass (or the return is malformed — the gate must not deadlock the pipeline):
        append "<ISO> [PLAN_AUDIT_PASS]" (or "[PLAN_AUDIT_PASS] (malformed return — waved through)")
        rm -f .get-it-done/plan_audit.md
        set phase = EXECUTING
    IF verdict == fail:
        write the full fail_reasons list to .get-it-done/plan_audit.md (dispatcher-owned file;
        overwrite). Append "<ISO> [PLAN_AUDIT_FAIL] <one-line summary>".
        keep phase = PLANNING — next tick re-spawns planner, which reads plan_audit.md
        (listed in its inputs) and MUST address every issue before re-emitting EXECUTING.
```

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

3. Planned pause — soft EXIT at planner-declared checkpoints
   IF planned_pause_list is non-empty (Step 9 saw one or more passing PauseAfter:true milestones in this batch):
     → For each entry e in planned_pause_list (in milestone-id ascending order):
         Append "<ISO> [PLANNED_PAUSE] <e.milestone_id> — <e.reason>" to progress_log.md
     → state.md is already at status: WAITING (Step 10 close); phase remains EXECUTING.
       Do NOT touch phase — soft pause means the user's next /continue resumes naturally
       on the next downstream milestone.
     → EXIT with a user-facing message listing every paused milestone:
       "規劃中暫停：<M-X: reason; M-Y: reason; ...>。完成人工驗收後執行 /continue 繼續下一個 milestone。"

4. Otherwise — keep going. The dispatcher self-coordinates:
   GOTO step 2 (next inner tick in the SAME /continue invocation)
   This covers both phase transitions (PLANNING→ANALYZING→EXECUTING→REPORTING) and
   consecutive batches within the same phase. There is no artificial batch ceiling
   and no context-budget guard — the dispatcher runs to a terminal phase or planned
   pause. If context truly exhausts mid-batch, the session will end abruptly; the
   next /continue picks up via Step 2 crash recovery.
```

**Design intent**: `/continue` autopilots from start to finish. The only legitimate reasons to stop within a session are: (a) the goal is COMPLETE, (b) the team hit AWAITING_HUMAN (blocker), or (c) the planner declared a PauseAfter checkpoint at planning time. Context exhaustion is not a planned stopping point — if it happens, it's a crash, and Step 2 recovery handles it on the next /continue.

## `report_and_reflect()` — runs once when the goal closes

Reflector is NOT part of the relay. It runs once per goal, after every task reaches `Status: done`.

```
1. Read .get-it-done/goal.md, .get-it-done/task_queue.md, last ~20 entries of .get-it-done/validation_log.md.
1.5 Degraded-validation sweep: grep .get-it-done/validation_log.md for "DEGRADED:" among
    entries belonging to this goal (since the latest [NEW_GOAL]/[GOAL_REFINED]; validators
    write e.g. "DEGRADED: BROWSER_UNAVAILABLE — ..." in their notes when they had to fall
    back from the full verification protocol). IF any found:
      - append "<ISO> [DEGRADED_VALIDATION] <task IDs + reasons>" to progress_log.md
      - the [GOAL_COMPLETE] message MUST include a prominent "⚠️ 人工確認清單" section
        listing each degraded task ID, the reason, and what the human should manually verify.
        The goal still closes — but the user must not discover the gap by accident.
1.6 Final commit consolidation (worktree mode): IF git_state.json `commit_granularity == goal`,
    run `python3 "$GID_PY" consolidate-final` (collapses every milestone commit into one; skips
    cleanly if already a single commit or the branch is pushed). For the default `milestone`
    granularity, history is already one-commit-per-milestone from Step 9 — no action.
2. Append to .get-it-done/progress_log.md:
     "<ISO> [GOAL_COMPLETE] <goal one-liner>. <N> tasks completed across <M> milestones; first-pass rate <X>/<Y>. Key deliverables: <bullet list of .get-it-done/workspace/exec-*/ artifact paths>."
3. Rewrite state.md YAML: phase=COMPLETE, status=WAITING, batch_id=null, batch_started_at=null, batch_ended_at=null, active_agents=[], last_updated=<ISO>. Remove the most recent `## Batch` block IFF its `next_phase == REPORTING` (it's now stale).
4. Emit the [GOAL_COMPLETE] paragraph to the user (including the ⚠️ 人工確認清單 when step 1.5 found degraded validations). In worktree mode, report the goal branch and that the user's own branch is untouched: read `goal_branch` from git_state.json and add — "原始碼變更已累積在分支 `<goal_branch>`（<N> commits，每 milestone 一個；`git log --oneline <goal_base>..<goal_branch>`）。你的工作分支與工作目錄未被更動 —— 請自行 review / merge / 開 PR 此分支。" **Do NOT auto-merge into the user's branch.** Leave the `_goal` worktree and `gid/goal-<slug>` branch in place (only `/objective` or `/adjust hard` wipes them).
5. **Reflector gate (skip for small goals).** Count the task entries (`### T-XXX:` headings) in `.get-it-done/task_queue.md`.
   - **`task_count <= 2`** → do NOT spawn reflector. A goal this small carries too little signal to be worth an opus reflection pass (no batch-parallelization dynamics, ≤2 validation cycles, no DAG-shape evidence). Append `<ISO> [REFLECT_SKIPPED] task_count=<N> (<=2; small goal)` to progress_log.md and skip to step 6.
   - **`task_count >= 3`** → resolve the persistent per-project B-side dir first, then spawn reflector:
     ```bash
     BSIDE=$(python3 "$GID_PY" bside-dir --base "${GID_BASE:-.}" --plugin-data "$PLUGIN_DATA")   # → {"ok":true,"path":...}; use .path
     ```
     Spawn reflector via Agent tool. Prompt: "Execute your reflector role per agents/reflector.md. The goal just COMPLETE'd. **bside_context_dir: `<BSIDE.path>`** (absolute — write/read ALL B-side learnings here, NOT .get-it-done/context/). Analyse validation_log + progress_log + the most recent batch handoffs. Update A-side and B-side learnings per your classification matrix. Do NOT change .get-it-done/state.md phase. Do NOT emit an agent-return block — your output is the file writes themselves."
     (If `bside-dir` fails — e.g. Python/git unavailable — fall back to passing `bside_context_dir: .get-it-done/context` so reflection still runs, degraded to the old per-goal scope; append `<ISO> [BSIDE_FALLBACK] <reason>` to progress_log.md.)
6. Reflector returns (or was skipped); EXIT. Reflection failures are logged ([REFLECT_FAIL]) but do NOT roll back COMPLETE.
```

## Dispatcher self-loop principle

**The dispatcher autopilots from start to finish.** It does NOT yield mid-progress except at three legitimate stopping points:

1. **Terminal phase** — `phase ∈ {COMPLETE, AWAITING_HUMAN, IDLE}` → stop. The work is done, blocked on a human, or absent.
2. **Planned pause** — a milestone validator passed a milestone with `PauseAfter: true`. Soft EXIT; phase stays EXECUTING so the next /continue resumes naturally.
3. **Crash-retry wait** — a singleton planner is in flight and the dispatcher needs real wall-clock time to elapse before checking again (Step 2 sub-case 0, recent-crash branch) → stop and let the user re-issue `/continue` when ready.

There is no context-budget guard — if the session truly runs out of context mid-batch, the partial state on disk is recovered by Step 2 on the next /continue. In every other situation (phase transitions, batch completions, many consecutive batches) the dispatcher loops back to Step 2 within the same invocation.

## Exit conditions

- `phase: COMPLETE` — goal achieved.
- `phase: AWAITING_HUMAN` — blocker (DAG, dependency deadlock, validator escalation, planner-flagged).
- `phase: IDLE` — no active goal.
- `[PLANNED_PAUSE]` — planner declared a PauseAfter checkpoint at this milestone. State is preserved (`phase: EXECUTING`, `status: WAITING`); a fresh `/continue` resumes the next downstream milestone naturally.
- `[CRASH_WAIT]` — planner singleton recently crashed and we need real time to elapse before retrying. Fresh `/continue` from the user re-checks.

## What the dispatcher does NOT do

- No mid-flight communication with sub-agents (they cannot be interrupted; their result arrives whole).
- No direct edits to executor artifacts, analyst findings, or PRD content — those are sub-agent property.
- No silent retry of a task whose validator returned `escalate_to_blocked: true` — that goes straight to AWAITING_HUMAN.
- Stage 3: heterogeneous batches (mixed per-task validators, milestone validators, reworks, new executors), N≤5. Source-path collisions between parallel executors must be ruled out at planning time by PR-013 in `agent_rules/planner.md` (declare overlapping tasks as DAG-dependent).
- No reflector invocation outside `report_and_reflect()`, and no reflector at all for small goals (`task_count <= 2` → `[REFLECT_SKIPPED]`).

Keep this skill thin in spirit — but recognize that the dispatcher legitimately owns more logic now than in v1, because sub-agents no longer touch shared state. If something feels like it belongs in an agent .md, ask whether moving it would re-introduce concurrent writes to shared files. If yes, it stays here.
