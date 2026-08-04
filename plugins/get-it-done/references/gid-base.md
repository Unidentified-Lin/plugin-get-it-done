# GID_BASE — Goal Worktree Resolution & Creation

> **Canonical source** for GID_BASE logic, referenced by `skills/continue/SKILL.md`, `skills/adjust/SKILL.md`, `skills/objective/SKILL.md`, and `skills/blueprint/SKILL.md`. Each skill site keeps only a short summary + a pointer to the matching section below — do not re-derive this logic locally.

## Concept

Each goal runs in its **own git worktree** under `<repo>.gid-goals/<slug>/` (branch `gid/goal-<slug>` from the repo's HEAD), which contains that goal's `.get-it-done/`. **`GID_BASE` = that worktree's absolute path.** This is how one repo-root window drives a chosen goal, and how multiple windows drive different goals at once.

- **Every `.get-it-done/...` path is under `$GID_BASE/`** — read/write `"$GID_BASE/.get-it-done/..."`.
- **Pass `--base "$GID_BASE"` to every `python3 "$GID_PY" <cmd>`** EXCEPT `git-preflight`, `goals`, and `goal-worktree-init` (those run at the repo root).
- **Spawn sub-agents with `repo_root = $GID_BASE`** (their cwd / state home).
- **Back-compat:** if `GID_BASE` is unset, base = repo root (legacy single-goal `.get-it-done/`). Everything still works.
- **Terminology:** where a skill says "`_goal`" / "the goal worktree", that means **`$GID_BASE` itself** in multi-goal mode (the goal worktree IS the base; `gid.py` operates there via `--base`), or the legacy `.get-it-done/worktrees/_goal` in back-compat mode. Task worktrees are grouped siblings `<repo>.gid-goals/<slug>-<T>` whose `.get-it-done/` symlinks to `$GID_BASE/.get-it-done/`.

## Resolve — find/select an existing goal

> **Used by**: `/continue` (every invocation, before Step 0), `/adjust` (Step 0a).

1. If this window already established `GID_BASE` (set earlier this session via `/objective` or a prior `/continue`) → reuse it. Validate it still appears in `python3 "$GID_PY" goals`; if gone, re-resolve.
2. Else run `python3 "$GID_PY" goals`:
   - **0 goals** → no isolated goals exist; if a legacy repo-root `.get-it-done/state.md` exists, run in single-goal back-compat (`GID_BASE` unset = repo root). Otherwise tell the user to run `/objective <goal>` and stop.
   - **1 goal** → set `GID_BASE` = its `path`.
   - **≥2 goals** → ask the user which goal (list the slugs) and set `GID_BASE` to the chosen `path`.
3. `export GID_BASE="<path>"` so every subsequent command inherits it.

## Create — establish a brand-new goal worktree

> **Used by**: `/objective` (Step 0a), `/blueprint` (Plan Freeze & Handoff, establishing the goal worktree before initializing execution state).

```
GID_PY := "${CLAUDE_PLUGIN_ROOT}/skills/continue/scripts/gid.py"
preflight := python3 "$GID_PY" git-preflight              # at repo root
slug := a short lowercase-hyphenated slug from the goal text (e.g. "add-login-flow"; keep <40 chars, unique)
IF preflight.is_git AND preflight.worktree_supported:
    result := python3 "$GID_PY" goal-worktree-init --slug "<slug>"   # creates <repo>.gid-goals/<slug> on gid/goal-<slug> from HEAD
    export GID_BASE = result.path                       # absolute path to the goal worktree
ELSE:
    GID_BASE unset → single-goal back-compat at the repo root (non-git or no worktree support)
```

`GID_BASE` = the active goal's worktree (unset ⇒ repo root). For the rest of the invoking skill: every `.get-it-done/...` path is under `"$GID_BASE/.get-it-done/..."`, and every `python3 "$GID_PY" <cmd>` (except `git-preflight`/`goals`/`goal-worktree-init`) takes `--base "$GID_BASE"`.
