# Implementation Plan — Worktree Isolation, Auto-Reaper & Commit Consolidation (#5 + #6)

**Status**: Implemented (v1.2.0). Verified by two adversarial review rounds with real git experiments (`[V1]`/`[V2]` fixes folded in), then built across Phases A–C and tested against real git fixtures. `gid.py` git subcommands all pass; SKILL/agent/template/doc wiring complete.
**Scope**: #5 (per-task git isolation + rollback), #6 (validation race), commit consolidation
**Out of scope**: #7 (cross-session lock) — deferred per user
**Target version**: 1.2.0

> **Verification note**: a reviewer ran real `git` experiments in throwaway repos and proved several
> git-mechanic assumptions wrong. Those fixes are folded in and marked `[V1]`. Load-bearing claims that
> were *tested and confirmed* are listed in §13 so they are not re-litigated.

---

## 1. Problem recap

- **#5** — Executors may edit the project's main source tree directly (`executor.md` "Artifact storage" §). On rework the dispatcher only clears the `Artifact` field; the failed attempt's source edits stay in the working tree, so rework executors build on top of half-broken code. No selective rollback; `/objective` and `/adjust hard` resets do not touch source the executor already wrote.
- **#6** — A per-task validator runs `npm build` / dev-server / tests (`validator.md` Type:code / Type:webapp) while a source-touching executor in the **same heterogeneous batch** mutates the shared tree → false fails / false passes / env collisions.
- Both share one root cause: **agents share one mutable working tree with no isolation**.

## 2. Design in one paragraph

Give every **source-touching** executor its own `git worktree` (an isolated checkout). The executor edits code there; its validator runs build/test **in that same worktree**; nothing touches the shared main tree during sub-agent execution. When a task passes, the dispatcher **squash-merges** its worktree branch into main as **one commit per task** (attempt noise stays on a throwaway branch). When a milestone is validated, those per-task commits are **consolidated into one commit per milestone**. Worktrees are bounded to O(active-milestone-size), reaped every tick, hard-capped, and wiped on goal reset. Non-git projects fall back to today's behavior plus a scheduling guard for #6.

This makes **#6 a structural consequence of #5**: a validator in `worktree/T-002` cannot see an executor's edits in `worktree/T-004`. The standalone scheduling rule is only needed in the non-git fallback path.

## 3. Core invariants (the safety we rely on)

1. **All merges happen in Step 9 (dispatcher persistence), never during sub-agent execution.** Step 7 waits for ALL sub-agents to return before Step 8/9. So main is mutated by exactly one actor (the dispatcher) at a time.
2. **Worktree branches (`gid/T-XXX`) only ever change source — never `.get-it-done/` and never linked dep dirs.** `.get-it-done/` *is* a git-tracked dir, so `git worktree add` DOES check out a copy of it `[V1]`; the inertness is therefore **enforced mechanically, not by agent discipline**: every staging operation uses a scoped `git add` that excludes `.get-it-done/` and every `link_dir` (§8.1 item 3). Result: the branch's `.get-it-done/` tree always equals the merge-base's, so squash-merge produces an empty diff there and never conflicts on state files. `[V1]`
3. **Milestone commits on main are contiguous and ordered**, *because of milestone gating*: Step 5 P4 only queues tasks whose `Milestone == active_ms`, and downstream milestones are blocked until the current one is validated, so per-task merges for `M_k` all land before any `M_{k+1}` task merges `[V1 confirmed]`. This is the precondition that makes `git reset --soft <milestone_base>` an exact consolidation. **If a future change ever lets two milestones' tasks merge interleaved, this breaks** — note it where the gate is defined.
4. **Squash preserves tree content; only commit SHAs change.** Downstream worktrees branch from current main HEAD and see identical file content after any consolidation. `[V1 confirmed]`
5. **Per-task source commits exclude `.get-it-done/`** because (a) the worktree branch never stages it (invariant 2) and (b) `worktree-merge` commits without `-a`, so the dispatcher's perpetual uncommitted churn in main's `.get-it-done/` is neither swept into source commits nor lost `[V1 confirmed]`. When/whether `.get-it-done/` itself is committed is the user's existing workflow (out of scope).

## 4. Worktree lifecycle

```
Step 6 claim executor T-XXX  (source-touching: Touches non-empty)
  ├─ first attempt: gid.py worktree-add T-XXX
  │     → git branch gid/T-XXX at main HEAD; git worktree add .get-it-done/worktrees/T-XXX
  │     → write the worktree's .git/info/exclude for link_dirs; link_dirs symlinked/junctioned from main; record base_sha
  └─ rework / blocked-retry: if worktree dir exists → reuse; if only the branch exists → recreate worktree from gid/T-XXX
Step 7 spawn: executor prompt carries repo_root + worktree=.get-it-done/worktrees/T-XXX
executor edits code in the worktree; writes CHANGES.md/artifact to repo_root/.get-it-done/workspace/exec-T-XXX/
Step 9 persist executor return → Status: executed
  → gid.py worktree-commit-wip T-XXX --attempt N   (scoped add excl .get-it-done + link_dirs; commit to gid/T-XXX; durability)
  → worktree kept alive for the validator
─ next tick ─
Step 6 claim validator T-XXX (mode task): no new worktree; reuse T-XXX's
Step 7 spawn: validator prompt carries worktree=.get-it-done/worktrees/T-XXX (runs build/test THERE)
Step 9 persist validator verdict:
  ├─ pass → Status: done
  │     → gid.py worktree-merge T-XXX
  │         (squash-merge gid/T-XXX into main = ONE commit, title self-sourced from task_queue;
  │          record milestone_base if first task of its milestone; remove worktree; delete branch)
  │         (on conflict → returns {ok:false, reason:conflict}; dispatcher sets needs_rework)
  ├─ fail (needs_rework) → keep worktree + branch; next rework executor adds another wip commit
  └─ fail (blocked) → gid.py worktree-drop T-XXX --keep-branch  (remove worktree, keep gid/T-XXX for forensics)
Step 9 persist milestone validator pass (mode milestone):
  → gid.py consolidate-milestone M_k   (git reset --soft milestone_base[M_k] && commit "M_k: <title>")
  → main history now has ONE commit for the whole milestone
```

Milestone validators (mode milestone) run on **main HEAD** (read-only) — provably no concurrent writer (all `M_k` tasks done & merged; downstream gated). No worktree needed for them.

## 5. Worktree explosion controls (explicit)

| Control | Where | Effect |
|---|---|---|
| Structural bound | lifecycle | A worktree exists only for a source-touching task in `{claimed, executed, validating, needs_rework}`. Milestone gating limits eligible tasks to the active milestone → realistic ceiling ≈ active-milestone size. |
| **Reaper (every tick)** | new Step 0.6 → `gid.py worktree-gc` | `git worktree prune` + remove any `.get-it-done/worktrees/*` whose task is not in the live set (crash orphans, leftover done/blocked). Idempotent. |
| Hard cap + backpressure | `gid.py pool` | If live+needed worktrees ≥ `max_worktrees` (default 8), stop adding **new (P4)** executors this batch; rework (P3, reuses existing) and validators still allowed. Emits them in `deferred` with reason `wt_cap`; dispatcher logs `[WT_CAP]`. |
| Reset wipe | `/objective`, `/adjust hard` | `gid.py worktree-reset-all` → remove all worktrees, prune, delete `gid/*` branches, `rm -rf .get-it-done/worktrees`. |

## 6. Commit consolidation (explicit)

Two always-on levels + one optional:

- **Level 1 — attempt → task (always).** Multiple attempts' commits live only on the throwaway `gid/T-XXX` branch. On pass, `git merge --squash` lands **one commit per task** on main. Main never sees attempt noise.
- **Level 2 — task → milestone (default).** When a milestone validates, `gid.py consolidate-milestone <M>` does `git reset --soft <milestone_base> && git commit -m "M<k>: <title>" -m "<body>"` (title + body = milestone title and its task list, self-sourced from task_queue.md). Final history = **one commit per milestone**. This is the "最後收整" the user asked for, realized incrementally (crash-safe: a dead session still leaves clean per-milestone history; end state is identical to a single final pass). `[V1 confirmed: reset --soft gives identical tree + correct parent]`
- **Level 3 — milestone → goal (optional, `commit_granularity: goal`).** `report_and_reflect()` runs `gid.py consolidate-final`: `git reset --soft <goal_base> && git commit -m "<goal one-liner>" -m "<per-milestone summary>"`, collapsing all milestone commits into one. **No-op cases the command must handle:** single-milestone goal (`goal_base == milestone_bases[M1]` → already one commit after Level 2; skip), and `goal_base..HEAD` already a single commit. Default is `milestone`, so Level 3 is off unless configured.

**Safety net before any rewrite:** `gid.py` moves a ref `gid/pre-consolidate-<goal-slug>` to current HEAD before each consolidation, so the latest rewrite is one command to undo; reflog covers deeper recovery. Consolidation is **skipped** (logged `[CONSOLIDATE_SKIP]`) if the goal branch has an upstream that already contains the commits (avoids force-push hazard) — per-task commits are then left as-is.

`commit_granularity ∈ {task, milestone(default), goal}` lives in `.get-it-done/git_state.json`.

## 7. Machine-state file: `.get-it-done/git_state.json`

Script-owned (gid.py reads/writes; the LLM never hand-edits it):

```json
{
  "git_mode": "auto",                  // auto | worktree | fallback (auto = decide via git-preflight)
  "commit_granularity": "milestone",   // task | milestone | goal
  "max_worktrees": 8,
  "link_dirs": ["node_modules"],       // ignored dep dirs to symlink/junction into each worktree
  "goal_base": "<sha>",                // main HEAD when the goal's first task merged
  "milestone_bases": { "M1": "<sha>" },// main HEAD before each milestone's first task merged
  "worktrees": { "T-003": { "branch": "gid/T-003", "base": "<sha>", "created": "<iso>" } }
}
```

## 8. File-by-file changes

### 8.1 `skills/continue/scripts/gid.py` — new git subcommands

gid.py gains **side-effecting** git operations. Each prints `{"ok": true, ...}` or `{"ok": false, "reason": ...}` on stdout; exit 0 even on logical failure (dispatcher reads `ok`), exit 2 only on unusable environment. All run from repo root. New helpers: `run_git(args) -> (rc, out)`, `load_git_state()/save_git_state()`, and reuse of the existing `parse_task_queue()` for titles/milestones/touches/status. **Titles are self-sourced** from `parse_task_queue()` — no `--title` args are passed by the SKILL `[V1]`. Define `source_touching(task) = bool(task["touches"])`.

1. `git-preflight` → `{is_git, dirty, head_sha, worktree_supported}`. `is_git` = `git rev-parse --is-inside-work-tree`; `dirty` = `git status --porcelain` non-empty (informational). Dispatcher uses this to set `git_mode`.
2. `worktree-add <T-XXX>` → idempotent, three cases:
   - worktree dir exists → `{ok, path, reused:true}`.
   - branch `gid/<T>` exists but dir missing (blocked-retry / crash) → `git worktree add .get-it-done/worktrees/<T> gid/<T>` (recreate). `[V1]`
   - neither → `git branch gid/<T> <HEAD>`; `git worktree add .get-it-done/worktrees/<T> gid/<T>`.
   Then: symlink/junction each `link_dir` from repo root if it exists there; record in `git_state.worktrees`. (Optional belt-and-suspenders for *untracked* link_dirs only: append each `link_dir` slash-less to the exclude file at `git -C <wt> rev-parse --git-path info/exclude` — note a linked worktree's `.git` is a *gitdir-pointer file*, so this resolves to the **shared** main `.git/info/exclude`; dedup before appending. `[V2]` This does nothing for the *tracked* `.get-it-done/` copy — exclude only affects untracked files — so the **load-bearing defense is always the scoped add in item 3**, not exclude.) Returns `{ok, path, branch, base_sha, reused}`.
3. `worktree-commit-wip <T-XXX> --attempt N` →
   - If `<T>` not in `git_state.worktrees` (artifact-only / no worktree) → `{ok, skipped:"no_worktree"}`. `[V1]`
   - Stage with a **scoped add that excludes state + deps** (this is the load-bearing fix for BLOCKER #2/#3): `git -C <wt> add -A -- . ':(exclude).get-it-done'` plus one `':(exclude)<dir>'` per `link_dir`. `[V1]`
   - If nothing staged (tree unchanged since last wip — also covers crash double-spawn) → `{ok, skipped:"no_changes"}`. `[V1]`
   - Else `git -C <wt> commit -m "wip(<T>): attempt N"`. Returns `{ok, wip_sha}`.
4. `worktree-merge <T-XXX>` → idempotent.
   - If branch `gid/<T>` gone AND task absent from `git_state.worktrees` → `{ok, skipped:"already_merged"}`.
   - Ensure WT committed (call the commit-wip staging path if a live worktree has uncommitted changes).
   - From repo root: `git merge --squash gid/<T>`. **On conflict**: `git reset --merge` (NOT `git merge --abort` — a `--squash` merge records no MERGE_HEAD, so `--abort` fails and leaves a `UU` tree) `[V1]`, then `{ok:false, reason:"conflict", files:[...]}`.
   - On clean: `git commit -m "<T>: <title>"` (title from parser; **no `-a`** so `.get-it-done/` churn stays out). **Milestone-base record:** read `Milestone` of `<T>`; `if M not in git_state.milestone_bases: milestone_bases[M] = <HEAD sha BEFORE this commit>` `[V1]`; if `goal_base` unset, set it to the same pre-commit HEAD.
   - Cleanup (tolerant): `git worktree remove --force <wt>` (ignore "not a working tree"); `git branch -D gid/<T>` (ignore "not found"); drop from `git_state.worktrees`. `[V1]`
   - Returns `{ok, merged_sha}`.
5. `worktree-drop <T-XXX> [--keep-branch]` → `git worktree remove --force <wt>` (tolerant); delete branch unless `--keep-branch`; update git_state. Returns `{ok}`.
6. `worktree-gc` → reads task_queue.md; `live = {T : source_touching AND status ∈ {claimed,executed,validating,needs_rework}}`; `git worktree prune`; for each `.get-it-done/worktrees/*` whose task ∉ live → `worktree remove --force` (delete branch if task done/absent; keep if blocked). Returns `{removed:[...], kept:[...]}`.
7. `consolidate-milestone <M>` → reads `milestone_bases[M]` and the milestone title + task list from the parser; updates backup ref `gid/pre-consolidate-<goalslug>` → HEAD; upstream-guard check (skip → `{ok, skipped:"upstream"}`); `git reset --soft <base>`; `git commit -m "<M>: <title>" -m "<task list>"`. Returns `{ok, commit_sha}`.
8. `consolidate-final` → as §6 Level 3: backup ref + upstream guard; `git reset --soft <goal_base> && git commit`; handle the single-commit / single-milestone no-op (`{ok, skipped:"already_consolidated"}`). Returns `{ok, commit_sha}`.
9. `worktree-reset-all` → remove every worktree under `.get-it-done/worktrees/`, `git worktree prune`, delete all `gid/*` branches, `rm -rf .get-it-done/worktrees`, reset `git_state` worktrees/bases. Returns `{ok}`.
10. `check-stray-edits <T-XXX> [--revert]` `[V2]` → in worktree mode, detect source edits a **no-worktree** executor wrote directly into main (the under-declared-`Touches` hole). Returns `{dirty_source:[paths]}` = `git status --porcelain` minus `.get-it-done/`, `.get-it-done/worktrees/`, and every `link_dir`. With `--revert`, also restores those paths (`git checkout -- <tracked>`; `git clean -fdq -- <untracked>`) so nothing lingers on main. Returns `{ok, dirty_source, reverted}`.

Extend **`pool`**: accept `--git-mode worktree|fallback` and `--max-worktrees N`.
- `worktree` mode → hard-cap backpressure: when live worktrees ≥ cap, skip new P4 executors (emit in `deferred`, reason `wt_cap`).
- `fallback` mode → the **#6 scheduling rule**: if the batch already holds an executing-type validator (target task `Type ∈ {code, webapp, test, api, infra}`) OR a source-touching executor, do not co-add the opposing role — defer it (reason `fallback_race_guard`). Artifact-only executors (empty `Touches`) and artifact-type validators (`Type ∈ {research, docs, planning, design}`) are unaffected. **Use the exact schema enum** — `planning` (not "plan"), `docs` (not "documentation") `[V1]`.

Link helper: POSIX `os.symlink`; Windows junction via `subprocess.run(["cmd","/c","mklink","/J",link,target])` (no admin needed); best-effort, never fatal.

Unit tests: extend the existing throwaway-fixture pattern with a real `git init` repo and assert: add (all three cases) idempotent; commit-wip scoped add never stages `.get-it-done/` or a `node_modules` symlink; merge → exactly one squash commit, branch+worktree gone, `.get-it-done/` absent from the commit; conflict path returns `conflict` AND leaves a clean tree (`reset --merge`); gc removes orphans/keeps live; consolidate-milestone collapses a 3-task milestone to one commit with the right parent; reset-all cleans everything.

### 8.2 `skills/continue/SKILL.md` — dispatcher edits

- **Step 0.5**: note gid.py now owns git operations; list the new subcommands.
- **New Step 0.6 — Git mode + worktree reaper**: run `gid.py git-preflight`; set `git_mode` (`worktree` if `is_git` and supported, else `fallback`; honor explicit override). Then `gid.py worktree-gc`. In fallback mode log `[GIT_FALLBACK] non-git/unusable; source executors write main tree directly (no rollback)` once per goal.
- **Step 5 (pool)**: pass `--git-mode <mode> --max-worktrees N`. Document defer reasons `wt_cap`, `fallback_race_guard`. State #6 is structurally solved in worktree mode; the scheduling rule applies only in fallback.
- **Step 6 (claim)**: after claiming an executor for a **source-touching** task in worktree mode, call `gid.py worktree-add <T>` and record the path. (Idempotent on crash recovery.)
- **Step 7 (spawn)**: for worktree-mode source executors/validators, the prompt template gains `repo_root: <abs main repo>` + `worktree: .get-it-done/worktrees/<T>` + the instruction block (§8.3/§8.4). Non-worktree items unchanged.
- **Step 9 (persist)**:
  - executor → executed: **if `source_touching(task)`**, `gid.py worktree-commit-wip <T> --attempt <Attempts>` (the command itself also no-ops on no-worktree, belt & suspenders) `[V1]`. **Else (no Touches, worktree mode)** run the under-declared-`Touches` guard `[V2]`: `gid.py check-stray-edits <T> --revert`; if `dirty_source` is non-empty the planner under-declared — append those paths to the task's `Touches` field (the dispatcher owns task_queue), append `[TOUCHES_UNDERDECLARED] <T> <paths>` to progress_log, and set `Status: needs_rework` (clear Artifact) so the rework re-runs isolated in a real worktree. The `--revert` already removed the stray edits from main, so nothing lingers (the reverted attempt's work is regenerated on rework).
  - task validator pass → done: **if `source_touching(task)`**, `gid.py worktree-merge <T>`; if it returns `conflict` → set `Status: needs_rework`, append `[MERGE_CONFLICT] <T>: <files>`, carry the conflict files into the next rework's context (like a fail_reason).
  - task validator fail (needs_rework): keep worktree (no action).
  - task validator fail (blocked) / executor blocker: `gid.py worktree-drop <T> --keep-branch`.
  - milestone validator pass (worktree mode): after existing logic, `gid.py consolidate-milestone <M>`.
- **`report_and_reflect()`**: if `commit_granularity == goal`, `gid.py consolidate-final` before `[GOAL_COMPLETE]`. Always add a "原始碼歷史：N commits（每 milestone 一個）" line to the completion message.
- **Crash recovery (Step 2)**: add a sentence — re-spawned executors reuse their worktree (`worktree-add` idempotent); the Step 0.6 reaper clears orphans; merges are per-task atomic so partial-batch crashes lose nothing durable. A double `worktree-commit-wip --attempt N` after re-spawn is benign (scoped add finds no changes → `skipped:"no_changes"`) `[V1]`.

### 8.3 `agents/executor.md` — worktree mode section

Add "## Worktree mode (source tasks)": when the spawn prompt includes `worktree:`, all **source code** edits go under that worktree path (relative `Touches` paths map into it); all **get-it-done state** (task_queue, metrics, prd, your scratch dir `workspace/exec-<T>/`) is read/written via `repo_root/.get-it-done/...` — **ignore the worktree's own `.get-it-done/` copy entirely** (the dispatcher's scoped commit guarantees nothing you do there reaches history, but reading the stale copy would mislead you). Run build/test/lint with cwd = worktree. Dependencies are pre-linked; if a command fails for missing deps, install inside the worktree. **Do NOT run any `git` command** — the dispatcher owns all git. Rework: your worktree persists across attempts (it holds your prior attempt). Keep the existing "Artifact storage" direct-write paragraph but prefix it "In fallback (non-git) mode only, …".

### 8.4 `agents/validator.md` — worktree mode section

Add "## Worktree mode": when the spawn prompt includes `worktree:`, run all build/test/dev-server/browser verification with cwd = that worktree (it holds exactly this one task's changes on validated upstream — isolated from peers; this isolation is why a parallel executor cannot corrupt your build). Read get-it-done state via `repo_root/.get-it-done/...`. Do NOT run `git`. Milestone-mode validators run on `repo_root` (main) directly — no worktree — because all milestone tasks are merged and no executor is concurrently active.

### 8.5 Templates

- **`templates/.get-it-done/.gitignore`** (new, committed): ignore `worktrees/`, `workspace/`, `archive/`, `git_state.json`. `git worktree add` into this gitignored subdir is clean `[V1 confirmed]`.
- **`git_state.json`**: NOT shipped as a template — the sibling `.get-it-done/.gitignore` would ignore it. Instead `gid.py` self-creates it with the §7 defaults on the first tick (Step 0.6 `worktree-gc` calls `save_git_state`); `load_git_state()` returns defaults whenever it is absent. Users can edit it after the first run.
- **`templates/.get-it-done/state.md`**: add a "Git isolation (v2.1)" subsection — worktree mode, git_state.json ownership, the per-task→per-milestone commit model, and the gate-dependency of invariant 3.
- **`templates/.get-it-done/task_queue.md`**: document that `Touches` non-empty ⇒ "source-touching" ⇒ the task runs in an isolated worktree (second use of the existing collision field).

### 8.6 `skills/objective/SKILL.md` + `skills/adjust/SKILL.md`

- Bootstrap already rsyncs new template files (`.gitignore`, `git_state.json`) via `--ignore-existing` — confirm only.
- `/objective` Step 4 reset and `/adjust hard` Step 3b reset: add `gid.py worktree-reset-all`. `/adjust soft` Step 3a does NOT reset worktrees (preserves in-flight work).

### 8.7 `references/platform-adapter.md`

Add "## Git worktree operations": worktrees live under `.get-it-done/worktrees/<T>` (gitignored); dep linking uses `ln -s` (macOS/Linux) and `mklink /J` junction (Windows, no admin `[V1 confirmed]`); all git work is done by `gid.py` so the only harness difference is the Python invocation. Note the non-git fallback.

### 8.8 Docs

- `references/main-flow.md`: worktree isolation + commit model in the Autonomous Path + a note in the EXECUTING description.
- `plugins/get-it-done/README.md` + root `README.md`: one bullet each ("Per-task git-worktree isolation with rollback; per-milestone commit consolidation").

## 9. Edge cases & handling

| Case | Handling |
|---|---|
| Non-git project | `git-preflight` → fallback: today's direct-write + CHANGES.md, plus the #6 scheduling guard. Logged once. |
| Dirty main tree at goal start | `git-preflight` reports `dirty`; warn the user. The dispatcher *continuously* leaves `.get-it-done/` uncommitted on main — this is **safe only because** the worktree branch never stages `.get-it-done/` (invariant 2) and `worktree-merge` commits without `-a` (invariant 5) `[V1]`. Non-`.get-it-done` uncommitted user changes on main may be swept by `consolidate` `reset --soft`; warn about that specifically. |
| Squash-merge conflict | `worktree-merge` → `git reset --merge` (clean recovery — `--abort` does NOT work for `--squash`) `[V1]` → task `needs_rework` with conflict files as context. Repeated → normal escalation. |
| node_modules / heavy deps | Linked once per worktree, excluded from staging by the scoped add + `.git/info/exclude` `[V1]`; manifest-changing tasks reinstall inside their worktree. |
| Windows symlink privilege | Directory junctions (`mklink /J`) — no admin/Developer-Mode `[V1 confirmed]`. |
| Worktree's tracked `.get-it-done/` copy | Materialized by `worktree add` but never staged (scoped exclude add); branch's `.get-it-done/` tree == base's → empty squash diff `[V1]`. |
| Blocked → retry | `worktree-drop --keep-branch` on block keeps `gid/<T>`; on retry, `worktree-add` recreates the worktree from the surviving branch; `worktree-merge` cleanup tolerates an already-missing worktree dir `[V1]`. |
| Crash mid-batch with worktrees | Reaper keeps live-task worktrees; `worktree-add`/`-merge`/`-commit-wip` idempotent; per-task atomic merges → no double-merge, no lost work; benign duplicate wip skipped by no-change detection `[V1]`. |
| Goal branch pushed mid-flight | Consolidation upstream-guard skips the rewrite (logged) to avoid force-push hazard. |
| Pathological wide milestone | `max_worktrees` backpressure caps concurrent worktrees; excess deferred. |
| Under-declared `Touches` (planner forgot to mark a code task source-touching) | `[V2]` worktree-mode guard: after a no-worktree executor returns, `gid.py check-stray-edits <T> --revert` detects + reverts stray source edits on main, the dispatcher records the dirty paths into the task's `Touches`, logs `[TOUCHES_UNDERDECLARED]`, and sets `needs_rework` → the retry runs isolated. Closes the silent-corruption hole. |

## 10. Testing plan

1. **gid.py git unit tests** (throwaway `git init` fixture): all three `worktree-add` cases; commit-wip scoped add proves `.get-it-done/` and a `node_modules` symlink are never staged; merge → one squash commit with `.get-it-done/` absent; conflict path returns `conflict` and leaves a clean (`reset --merge`) tree; gc orphan/live; consolidate-milestone collapse with correct parent; reset-all.
2. **Pool tests**: worktree mode caps P4 at `max_worktrees`; fallback mode defers validator↔executor co-batching with the corrected Type enum.
3. **Dry-run walkthrough**: 2-milestone, 4-task synthetic goal in a temp git repo, driving gid.py in dispatcher order; assert final `git log --oneline` = 2 commits and the working tree = union of task changes, with no `.get-it-done/` paths in either source commit.
4. **Fallback smoke**: same in a non-git dir → no worktrees, scheduling guard observed.
5. **Under-declared Touches**: a `Type: code` task with empty `Touches` whose executor writes a source file directly → `check-stray-edits --revert` returns the path, reverts it on main, dispatcher records Touches + needs_rework. Assert main is clean afterward and the retry gets a worktree.

## 11. Rollout / sequencing

- **Phase A** — gid.py: all subcommands + pool flags + git_state.json + unit tests. Ships dark (no behavior change until SKILL wires it).
- **Phase B** — continue/SKILL.md Steps 0.6/5/6/7/9 + executor.md/validator.md worktree sections + templates + gitignore.
- **Phase C** — consolidate-milestone/-final + report_and_reflect wiring + objective/adjust reset + docs.

## 12. Open defaults (chosen, override-able)

- `commit_granularity = milestone`; `max_worktrees = 8`; `link_dirs = ["node_modules"]`.
- Worktree location `.get-it-done/worktrees/<T>` (gitignored, sandbox-safe).
- Milestone validator runs on main (not a worktree).
- Worktree persists per-task across attempts (bounded by milestone size + reaper + cap).
- Titles self-sourced by gid.py from task_queue.md (no `--title` args).

## 13. Verified-correct (tested in throwaway repos — do not re-litigate)

- `git merge --squash gid/<T>` + `git commit` (no `-a`) carries ONLY source; uncommitted `.get-it-done/` on main is neither committed nor lost — **provided the branch never stages `.get-it-done/`** (the scoped-add fix).
- `git reset --soft <base> && git commit` consolidation: identical resulting tree, parent == base, collapses N contiguous commits to one, leaves working tree + other worktrees untouched.
- `git worktree add` into a gitignored subdir of the same repo is clean (no `git status` confusion).
- `git merge --squash` is a 3-way merge vs merge-base — does not revert unrelated files main advanced after branch creation.
- Overlapping-file squash-merge DOES conflict (so the conflict path is real and needed); after a `--squash` conflict, `git merge --abort` FAILS — `git reset --merge` is required.
- `node` resolves a symlinked `node_modules`; but `git add -A` WILL stage a `node_modules` symlink unless excluded (slash pattern `node_modules/` does not match the symlink file) — hence the scoped exclude add.
- `mklink /J` needs no elevation; `python3`/`python` invocation matches existing Step 0.5.
- gid.py's parser already exposes every field the new commands need; new subcommands slot into `main()` without reworking existing functions. All SKILL Steps the plan edits exist and the edits don't contradict the pool P1–P4, milestone gating, or the plan-audit gate.
