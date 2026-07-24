# Phase 6 Handoff — Scripted State Writes + state.md Split

> Read this BEFORE touching any code. It is written so a fresh session with zero prior
> context can pick up exactly where the last one stopped. Companion doc:
> `docs/plans/skill-optimization-plan.md` (the full 6-phase plan; Phase 6's original spec
> is there too — this doc supersedes it with concrete implementation detail).

---

## 0. Where things stand right now

- Repo: `plugin-get-it-done`. Phases 1–5 of the optimization plan are **done**, each on
  its own branch, stacked linearly:
  `fix/p0-stale-terms-and-adjust-base-paths` → `feature/slim-continue-skill` →
  `feature/dedupe-shared-rules` → `feature/wording-cleanup` → `feature/gid-tests`
  (HEAD, commit `28aba06` at time of writing).
- **None of this is merged to `master` yet.** Per `CLAUDE.md`: new branch per unit of
  work, commit only (no push), no self-merge — wait for explicit user confirmation
  before merging anything, and only bump `plugins/get-it-done/.claude-plugin/plugin.json`
  version when merge is confirmed.
- Start Phase 6 with: `git checkout -b feature/scripted-state-writes feature/gid-tests`
  (branch off the tip that has all prior phases + the 47-test suite).
- Before writing any code, run the existing suite and confirm it's green:
  ```bash
  python3 -m unittest discover -s plugins/get-it-done/skills/continue/scripts/tests -p "test_*.py" -v
  ```
  47 tests should pass. If they don't, something upstream broke — stop and investigate
  before starting Phase 6, don't build on a red baseline.

## 1. Why Phase 6 exists (motivation, already user-confirmed)

The user's top concern across this whole optimization effort was **context load on the
dispatcher LLM**. `/continue` currently Reads and Edits `.get-it-done/state.md` and
`task_queue.md` directly, by hand, every tick — large files, error-prone bookkeeping
(claim writes, YAML rewrites, log appends with dedup keys). `gid.py` already computes
everything *deterministically* (DAG checks, pool selection, milestone derivation) but is
**read-only** for `.get-it-done/*.md` — the LLM still does every write itself.

**Direction A** (confirmed by the user mid-session, before Phase 1 started): extend
`gid.py` with write subcommands so the dispatcher stops directly Read/Editing state
files for the fully-mechanical steps (claiming a batch, persisting a return, closing a
batch) and instead calls a script that does it atomically and correctly. The **single-writer
principle is preserved** — the writer just changes from "the LLM's Edit tool" to "the
dispatcher's sequential script calls," still gated by the dispatcher's own logic for
*which* action to take.

Paired with this: split `state.md`'s YAML/log content (which the dispatcher touches
every tick) from its prose specification (state machine docs, phase definitions,
transition rules, agent-return contract — which sub-agents read once per spawn but
never write). Machine state should be small; the spec doc can be as long as it needs
to be since it's read, not carried in a hot loop.

## 2. The user's scoping decision (READ THIS FIRST, before writing code)

When this was raised as the next step, the user was asked: full-scope Phase 6 (every
branch of Step 9's decision table) vs. core-path-with-documented-fallback vs. defer.
**They chose to defer** rather than pick a scope, specifically because this is the
highest-risk, hardest-to-verify-by-testing phase in the whole plan, and they wanted
more room to make that scoping call carefully rather than rushed.

**Do not assume an answer for them. Ask again, at the start of the new session**, using
essentially the same framing:

- **Full scope**: the 4 new subcommands cover every branch Step 9 currently handles by
  hand, including the rare ones (milestone structural failure → AWAITING_HUMAN with
  evidence preserved; `TOUCHES_UNDERDECLARED` auto-detection and rework; multiple
  `PauseAfter` milestones in one batch). Higher effort, harder to fully verify since some
  of these paths are awkward to hit in a unit test (they depend on specific validator
  verdict sequences).
- **Core-path-first**: the 4 subcommands handle the common cases (executor
  completed/failed, validator task pass/fail, validator milestone pass/fail including
  `task_ids_to_rework`, analyst fulfilled, planner phase transition + plan audit gate
  trigger) and explicitly fall back to the existing hand-written Step 9 prose for the
  rare edge branches — documented in `STATE_SPEC.md` (see §5) with a table of "scripted
  vs. still-manual" so it's auditable, not silently incomplete.

Given the size of this phase, **core-path-first is the safer default** if the user
doesn't have a strong preference — it gets the majority of the context-load win (the
common case is >90% of ticks) while keeping the riskiest, least-tested logic in the
form that's easiest for a human to review (readable prose the LLM executes directly,
same as today) until it's proven out.

## 3. Exact scope: 4 new gid.py subcommands

All four are **new functions in the existing `plugins/get-it-done/skills/continue/scripts/gid.py`**
(same file, same stdlib-only constraint — no PyYAML, no external deps). Follow the
existing code's conventions: `cmd_<name>()` functions, JSON on stdout, exit 2 + `{"error":...}`
on fatal failure via `die()`, wired into the `main()` dispatch table and `NO_CHDIR_CMDS`
handling exactly like the existing `worktree-*` / `consolidate-*` commands.

Read the whole file first (1290 lines) — `parse_state`, `parse_task_queue`,
`dag_violations`, `milestone_status`, `cmd_pool`, and the git helpers (`run_git`,
`load_git_state`/`save_git_state`, `wt_path`/`wt_branch`, `goal_wt_path`) are all things
the new commands will reuse, not reimplement.

### 3.1 `claim-batch` — replaces Step 6 (continue/SKILL.md lines ~201-233)

**Input**: a JSON batch description on stdin (or a `--batch-file <path>`, whichever is
more natural given how the dispatcher would construct it — the dispatcher already has
this shape in memory from Step 5's `pool` output, so passing it straight through with
minimal reshaping is the goal). Shape mirrors `cmd_pool`'s `batch` list:
```json
{"batch": [{"role": "executor", "task_id": "T-003", "scratch": ".get-it-done/workspace/exec-T-003/"},
           {"role": "validator", "mode": "task", "task_id": "T-001", "scratch": null}],
 "phase": "EXECUTING",
 "git_mode": "worktree", "max_parallel": 5}
```

**Does**, atomically (single pass, write once):
1. Compute next `batch_id` (reuse `cmd_batch_id`'s logic — don't duplicate the regex).
2. Rewrite `state.md`'s YAML block: `status: RUNNING`, new `batch_id`, `batch_started_at:
   now`, `batch_ended_at: null`, `active_agents` built from the batch list, `last_updated:
   now`. **Preserve everything below the YAML block** (the spec content, or after the
   split in §5, whatever's left there) — this is a targeted regex/string replace of the
   fenced block only, same pattern `parse_state` uses to *find* the block.
3. For each item, apply the exact claim semantics from the current Step 6 prose:
   - `executor`: task `Claimed_by: exec-<task_id>`, `Claimed_at: now`, `Status: claimed`.
     `os.makedirs` the scratch dir.
   - `validator, mode: task`: task `Claimed_by: val-<task_id>`, `Claimed_at: now`,
     `Status: validating`.
   - `validator, mode: milestone`: in `## Milestones`, that milestone's `Claimed_by:
     mval-<milestone_id>`, `Claimed_at: now`. Per-task `Status` untouched.
   - `analyst`: in `research_requests.md`, matching RQ's `Claimed_by: analyst-<RQ-id>`,
     `Claimed_at: now`. `Status` stays `open`.
   - `planner`: no task_queue change.
4. **Worktree assignment logic for source-touching executors** (currently embedded in
   Step 6's prose, git_mode-dependent) — decide sequential-vs-parallel and call the
   *existing* `cmd_worktree_add` when parallel mode applies, exactly per the current
   rule (`max_parallel<=1` OR only 1 source executor this batch ⇒ sequential/`_goal`;
   else parallel ⇒ `worktree-add`). This is the one place claim-batch calls into git —
   everything else in this subcommand is pure `.md`/JSON file writes.

**Output**: `{"ok": true, "batch_id": "B0042", "active_agents": [...]}` (echo what was
written, so the dispatcher doesn't need to re-Read state.md to confirm).

**Failure mode**: if any file write fails partway, this is the one place atomicity
actually matters operationally — either do the task_queue.md rewrite as a single
in-memory transform + single write (like `parse_task_queue`/write-back does today
conceptually, even though today it's the LLM doing it), or accept that a crash mid-write
here is covered by the *existing* crash-recovery contract in Step 2 (claimed markers are
the recovery signal — a partial claim-batch write looks like a crash and gets recovered
the same way a crashed LLM-Edit sequence would). Prefer the latter — don't invent new
transactionality the rest of the system doesn't have; match the existing failure model.

### 3.2 `persist-return` — replaces (the scripted part of) Step 9

**Input**: one parsed agent-return dict on stdin, plus context the dispatcher already
has (`task_id`/`req_id`, `role`, `batch_id`, `git_mode`, worktree mode flags). One call
per batch item — the dispatcher loops Step 8's parsed returns and calls this once per
well-formed item (BAD_RETURN items still get handled by the dispatcher directly, not by
this command — see the existing Step 8/9 split, unchanged).

**Does** (core-path — see §2 for what "core path" means if that's the chosen scope):
- **Executor return**: `Artifact`, `Attempts+1`, clear `Claimed_by`/`Claimed_at`, `Status`
  → `executed` or `blocked` per the existing rule. Append `[EXEC_DONE]`/`[BLOCKER]` to
  `progress_log.md`.
- **Validator return, mode: task**: append to `Validation Results`, append `VAL-XXX` to
  `validation_log.md` (dedup on `(task_id, attempt_no)` — **reuse this dedup logic, it's
  security-critical for crash-recovery correctness, don't rewrite it from scratch**),
  clear claim, `Status` → `done`/`needs_rework`/`blocked` per verdict.
- **Validator return, mode: milestone**: increment `ValidatorAttempts`, append VR, append
  `MVAL-XXX` (dedup on `(milestone_id, attempt_no)`), clear claim. On `verdict: pass`,
  no per-task change (milestone_status derives it). On `fail` with non-empty
  `task_ids_to_rework`, flip those tasks to `needs_rework`.
- **Analyst return**: RQ → `fulfilled`, clear claim, confirm findings file exists.
- **Planner return**: read `next_phase_request`; for `EXECUTING`, this command should
  **NOT** run the plan-audit-gate spawn itself (that's a sub-agent spawn, orchestration
  stays in the dispatcher/SKILL.md) — just report back what the requested transition is
  and let the dispatcher run the existing plan-audit-gate procedure
  (`references/plan-audit-gate.md`) before actually setting `phase: EXECUTING`.

**Git side-effects**: per the original plan wording, `persist-return` should **return an
`next_actions` list** of gid.py subcommands the dispatcher must run afterward (e.g.
`["goal-commit-task T-003"]` or `["worktree-merge T-003"]`), rather than invoking git
itself. This keeps clean separation — git orchestration stays in the already-tested
`worktree-*`/`goal-commit-task`/`consolidate-milestone` commands, `persist-return` only
decides *which* to call. Example output:
```json
{"ok": true, "status_after": "done", "next_actions": ["worktree-merge T-003"]}
```
The dispatcher runs `next_actions` in order, then proceeds.

**Edge branches — explicitly flag these as in/out of scope depending on §2's answer**:
- `TOUCHES_UNDERDECLARED` detection (`check-stray-edits --revert`, appending to `Touches`,
  flipping to `needs_rework`) — this mutates the task's `Touches` field, which is
  planner-owned data; scripting this is *more* invasive than the other branches.
- Milestone structural failure (`task_ids_to_rework` empty on a `fail` verdict) →
  AWAITING_HUMAN with evidence preserved — a phase flip with no task_queue mutation,
  should be straightforward to script, but is rare enough that it's hard to test
  realistically without a lot of fixture setup.
- `PauseAfter` multi-milestone announcement list — this is cross-cutting with Step 11,
  not really part of "persisting one return," so it likely belongs to the dispatcher
  still assembling `planned_pause_list` from multiple `persist-return` calls' outputs
  in one batch, not something a single `persist-return` invocation owns.

### 3.3 `close-batch` — replaces Step 10 (continue/SKILL.md lines ~373-393)

**Input**: `{"batch_id": "B0042", "phase": "EXECUTING", "items": [{"role":"executor","task_id":"T-003","status_or_verdict":"completed","artifact":"..."}], "intent": "validate T-003 next tick"}`

**Does**: rewrite state.md YAML (`status: WAITING`, `batch_ended_at: now`,
`active_agents: []`, `last_updated: now`, `phase: <given>`), append the `## Batch <id> —
...` block to the bottom of state.md (or, post-split, wherever the batch history lives
— see §5, there's an open question about whether to keep this at all since the
dispatcher never reads it back).

**Output**: `{"ok": true}`.

### 3.4 `log-append` — generic log utility

**Input**: `{"file": "progress_log.md", "line": "[EXEC_DONE] T-003 ..."}` or a structured
form for VAL/MVAL entries with dedup keys. This is mostly a refactor of logic that
`persist-return` and `close-batch` both need (progress_log append is used everywhere;
validation_log append with dedup is used by validator persistence) — factor it out as a
shared internal function first, then decide whether it also needs to be an independently
callable subcommand (the plan says yes, for cases like Step 2's crash-recovery log lines
which aren't part of a persist-return/close-batch call). Reuse `truncate_one`'s
neighboring code style; this should be a small, low-risk piece — good one to build and
test first before tackling `persist-return`.

## 4. SKILL.md changes

Once the subcommands exist and are tested:

- `continue/SKILL.md` Step 6 (~lines 201-233): replace the manual claim-writing prose
  with a call to `claim-batch`, keeping the git-mode/worktree-assignment explanation as
  context the dispatcher needs to construct the input JSON, but removing the literal
  file-rewrite instructions.
- `continue/SKILL.md` Step 9 (~lines 315-372): same treatment — replace the per-role
  bullet lists with "call `persist-return` per item, then run any `next_actions`." If
  core-path-only scope was chosen, the edge-branch prose (TOUCHES_UNDERDECLARED,
  milestone structural failure) **stays inline** as the fallback, clearly marked "not yet
  scripted — see STATE_SPEC.md."
- `continue/SKILL.md` Step 10 (~lines 373-393): replace with a `close-batch` call.
- **Explicit read restriction** (per the original plan wording): once these exist, add a
  line near the top of `continue/SKILL.md` (near where `GID_BASE`/Step 0.5 already
  explain the script-first philosophy) stating that outside of the documented fallback
  paths, the dispatcher must NOT directly Read `state.md`/`task_queue.md`/
  `research_requests.md` — it reads via `gid.py state`/`pool`/`rqs` JSON instead. This is
  a real behavior change (removes the dispatcher's general-purpose Read access to these
  files in the common path) — call it out clearly in the PR/commit description, since
  it's exactly the kind of "must not change semantics without flagging" item the
  project's guardrails care about, except here it's the *intended* semantic change this
  whole phase exists to make.
- `skills/objective/SKILL.md` Step 2 (state.md YAML reset) and `skills/adjust/SKILL.md`
  Step 3a/3b (state.md YAML rewrites) currently do their own direct YAML rewrites for a
  *different* purpose (resetting to a fresh goal, not batch lifecycle) — the plan
  suggests scripting these too ("objective / adjust 的狀態寫入段落同步腳本化"). This is
  smaller and lower-risk than the batch-lifecycle commands (no crash-recovery
  interaction, no dedup logic) — consider whether it's worth a `reset-state`-style
  subcommand or whether the existing `bootstrap.py reset` is the right place to extend
  instead (it already owns the "reset per-goal files" responsibility from Phase 1).
  `/adjust`'s Step 1 RUNNING-rollback logic (clearing stale claims) is also flagged in
  the original plan as "納入腳本化範圍" — this is genuinely the same shape as crash
  recovery, so it's a reasonable candidate to fold into whatever `claim-batch`-adjacent
  cleanup logic gets built, but verify the semantics match exactly (rollback direction
  is claimed→pending / validating→executed, the *reverse* of claim-batch's forward
  direction) before assuming code reuse actually saves work here.

## 5. state.md split

- `templates/.get-it-done/state.md` (currently 164 lines, read in full at the start of
  this session if you haven't already — it has: YAML schema block, `active_agents` entry
  schema, Phase Definitions table, Transition Rules, Batch lifecycle contract, Crash
  detection contract, Git isolation section — now the **canonical** worktree-model
  source per Phase 3's dedup work, don't break that — Agent-return YAML contract, Batch
  handoff log format) needs to become:
  - **`templates/.get-it-done/state.md`**: just the YAML block + (open question, decide
    with fresh eyes) whether to keep the `## Batch <id>` history at all. The doc itself
    already says "the dispatcher never reads them — it derives the next batch from
    task_queue.md state alone" (line ~160 in the current file) — so removing it entirely
    is on the table, trading a human-auditable history for a smaller hot file. If kept,
    it's the one thing `close-batch` still appends to.
  - **New `templates/.get-it-done/STATE_SPEC.md`** (or `plugins/get-it-done/references/state-spec.md`
    — decide based on whether this is meant to be a per-project template (copied into
    the user's `.get-it-done/`, like state.md is) or a plugin-level reference (read from
    the plugin install, like `platform-adapter.md`). Given sub-agents currently list
    `.get-it-done/state.md` in their **Inputs** sections specifically to read the
    Agent-return contract and Phase Definitions — check `agents/executor.md`,
    `agents/validator.md`, `agents/planner.md`, `agents/analyst.md`, `agents/reflector.md`
    for exactly where they reference it — this argues for keeping it as a per-project
    template file (so it's always present without a plugin-root path), even though its
    content never changes per-project. Whichever you choose, **every one of those Inputs
    references must be updated in the same commit**, along with the "Batch lifecycle
    (dispatcher contract)" §1 line in state.md that currently says "see
    `skills/continue/SKILL.md`" — that line's accuracy depends on this split landing
    correctly.
- After the split, verify with `grep -rln "\.get-it-done/state\.md" plugins/get-it-done`
  and manually confirm every hit still makes sense — some references want "the machine
  state" (still `state.md`) and some want "the spec" (now `STATE_SPEC.md`); getting this
  wrong silently breaks a sub-agent's ability to find the agent-return contract, which
  is a hard-to-notice failure (the sub-agent will just improvise a return format that
  doesn't match, which Step 8's `BAD_RETURN` handling will catch, but you don't want to
  discover this via CI/manual testing after the fact — get it right during the split).

## 6. Testing requirements

The Phase 5 suite (`plugins/get-it-done/skills/continue/scripts/tests/test_gid.py`, 47
tests) is the safety net for this phase — **it must stay green throughout**. Extend it,
don't work around it:

- Unit tests for each new subcommand's pure logic, following the existing patterns in
  the file: `temp_project()` context manager for file-based commands (`claim-batch`,
  `close-batch`, `log-append` can likely all be tested this way — write a `state.md` +
  `task_queue.md` fixture, call the `cmd_*` function, assert on the rewritten file
  content and the returned JSON).
- `persist-return`'s dedup logic (VAL/MVAL keyed on `(task_id, attempt_no)`) needs an
  explicit test that calls it twice with the same attempt number and asserts the second
  call does NOT double-append to `validation_log.md` — this is exactly the kind of
  regression the existing crash-recovery contract depends on, and it's cheap to test.
- Extend `TestGitIntegration` if `claim-batch`'s worktree-assignment branch or
  `persist-return`'s `next_actions` → actual git command execution needs coverage in a
  real repo (likely yes for at least one round-trip: claim a parallel executor task,
  simulate its return with `verdict: pass`, confirm `persist-return` returns
  `["worktree-merge T-XXX"]`, actually run it, confirm the merge happened).
- Run the full suite (`python3 -m unittest discover -s plugins/get-it-done/skills/continue/scripts/tests -p "test_*.py" -v`)
  before every commit in this phase, not just at the end.

## 7. Acceptance criteria (from the original plan, still the bar to hit)

> A complete goal cycle (PLANNING→EXECUTING→REPORTING→COMPLETE, including rework and
> crash-recovery simulation) has the dispatcher doing **zero direct Read/Edit** on
> `.get-it-done/*.md` outside of documented fallback situations; the Phase 5 test suite,
> extended to cover the new subcommands, is fully green; `/continue`'s SKILL.md line
> count drops further (original target: ≤250 lines — sanity-check this is still
> realistic once you see how much Step 6/9/10 actually shrink; if the target turns out
> to be as loosely calibrated as Phase 2's ≤350 line target was pre-execution, don't
> force it — explain the discrepancy honestly like Phase 2's write-up did).

## 8. Process reminders (same as every prior phase)

- New branch (`feature/scripted-state-writes`) off `feature/gid-tests`. Commit only, no
  push, no self-merge, no version bump — per `CLAUDE.md`.
- This phase, unlike Phases 1–4, **is** a semantic/architectural change — that's already
  been approved in principle (Direction A, confirmed 2026-07-24, before Phase 1 began).
  What still needs a fresh check-in is the *scope* (§2) and any judgment call you hit
  that isn't already answered by this doc or the original plan — stop and ask rather
  than silently deciding, same standard as every prior phase (e.g. the Windows
  `--base "."` bug found mid-Phase-3 was paused on and confirmed before fixing).
- Verify each sub-step the way prior phases did: for pure logic, tests you actually run;
  for anything that changes what an LLM agent would do differently (SKILL.md prose,
  cross-file reference updates), an independent sub-agent semantic-equivalence check is
  the pattern used in Phases 2–4 — reuse it here for the SKILL.md rewrites in §4, since
  those are exactly the kind of "does this still mean the same thing" question a fresh
  sub-agent is good at catching.
