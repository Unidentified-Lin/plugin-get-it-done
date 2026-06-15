#!/usr/bin/env python3
"""gid.py — deterministic helper for the get-it-done dispatcher (/continue).

Read-only derivation + log maintenance. The dispatcher (LLM) remains the only
writer of task_queue.md / state.md; this script removes the error-prone
computation steps (state parsing, DAG validation, milestone derivation, batch
selection, log truncation) from the model's hands.

Stdlib only (no PyYAML) — must run on any Python 3.8+ without installs.

Subcommands (all emit JSON on stdout):
  state          — parse the YAML block at the top of .get-it-done/state.md
  dag-check      — validate the task DAG (self-ref / orphan / cycle / touches overlap)
  pool           — derive milestone statuses + the prioritized actionable pool (Step 5)
  rqs            — parse research_requests.md entries (Status / Claimed_by)
  batch-id       — next monotonic batch id from state.md history
  truncate-logs  — archive + truncate progress_log.md / validation_log.md (writes files)

Exit code 0 = ran cleanly (check JSON "ok"/"violations" fields for verdicts);
exit code 2 = could not parse required files (dispatcher falls back to manual procedure).
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

GID_DIR = ".get-it-done"
GIT_STATE_PATH = os.path.join(GID_DIR, "git_state.json")
WT_ROOT = os.path.join(GID_DIR, "worktrees")
EXECUTING_TYPES = {"code", "webapp", "test", "api", "infra"}   # build/test-running task types
DEFAULT_GIT_STATE = {
    "git_mode": "auto",
    "commit_granularity": "milestone",
    "max_worktrees": 8,
    "link_dirs": ["node_modules"],
    "goal_base": None,
    "milestone_bases": {},
    "worktrees": {},
}


def die(msg):
    print(json.dumps({"error": msg}), file=sys.stdout)
    sys.exit(2)


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- state.md

def parse_state(text):
    """Parse the first fenced yaml block (or bare top block) of state.md."""
    m = re.search(r"```yaml\s*\n(.*?)```", text, re.S)
    block = m.group(1) if m else text
    state = {}
    for line in block.splitlines():
        km = re.match(r"^(\w+):\s*(.*?)\s*(#.*)?$", line)
        if not km:
            continue
        key, val = km.group(1), km.group(2).strip()
        if key == "active_agents":
            continue
        if val in ("null", "", "~"):
            state[key] = None
        elif val in ("true", "false"):
            state[key] = val == "true"
        elif val.isdigit():
            state[key] = int(val)
        else:
            state[key] = val.strip("'\"")
    # count active_agents entries (list items under the key)
    agents = re.findall(r"^\s*-\s+role:\s*(\S+)", block, re.M)
    state["active_agent_count"] = len(agents)
    state["active_agent_roles"] = agents
    return state


def cmd_state():
    text = read(os.path.join(GID_DIR, "state.md"))
    if text is None:
        die("state.md not found")
    print(json.dumps(parse_state(text), ensure_ascii=False, indent=2))


def cmd_batch_id():
    text = read(os.path.join(GID_DIR, "state.md")) or ""
    ids = [int(m) for m in re.findall(r"^##\s+Batch\s+B(\d+)", text, re.M)]
    cur = re.search(r"^batch_id:\s*[\"']?B(\d+)", text, re.M)
    if cur:
        ids.append(int(cur.group(1)))
    nxt = (max(ids) + 1) if ids else 1
    print(json.dumps({"next_batch_id": "B%04d" % nxt}))


# ------------------------------------------------------------ task_queue.md

FIELD_RE = re.compile(r"^[\s>*-]*\*\*([A-Za-z][\w ]*?)\*\*\s*:\s*(.*)$")
TASK_HEAD_RE = re.compile(r"^###\s+((?!M\d)[A-Z][\w-]*?)\s*:\s*(.*)$")
MILESTONE_HEAD_RE = re.compile(r"^###\s+(M\d+)\s*:\s*(.*)$")


def parse_list(val):
    """Parse inline list like `[T-001, T-002]` or `["src/a.ts", "src/b.ts"]`."""
    val = val.strip()
    if not val or val in ("[]", "null", "none"):
        return []
    val = val.strip("[]")
    return [x.strip().strip("'\"`") for x in val.split(",") if x.strip().strip("'\"`")]


def parse_vr_entries(lines):
    """Parse a Validation Results block (yaml-ish list) into dicts."""
    entries, cur = [], None
    for ln in lines:
        if re.match(r"^\s*-\s+attempt_no\s*:", ln):
            cur = {}
            entries.append(cur)
        if cur is None:
            continue
        m = re.match(r"^\s*-?\s*(\w+)\s*:\s*(.*)$", ln)
        if m and m.group(1) in ("attempt_no", "verdict", "escalate_to_blocked"):
            v = m.group(2).strip().strip("'\"")
            if v in ("true", "false"):
                v = v == "true"
            elif v.isdigit():
                v = int(v)
            cur[m.group(1)] = v
    return entries


def parse_task_queue(text):
    lines = text.splitlines()
    tasks, milestones = {}, {}
    in_milestones = False
    cur = None          # current entry dict
    vr_lines = None     # accumulating Validation Results lines
    vr_target = None

    def flush_vr():
        nonlocal vr_lines, vr_target
        if vr_target is not None and vr_lines is not None:
            vr_target["validation_results"] = parse_vr_entries(vr_lines)
        vr_lines, vr_target = None, None

    for ln in lines:
        if re.match(r"^##\s+Milestones\b", ln):
            flush_vr()
            in_milestones = True
            cur = None
            continue
        hm = MILESTONE_HEAD_RE.match(ln) if in_milestones else None
        ht = TASK_HEAD_RE.match(ln) if not in_milestones else None
        if hm:
            flush_vr()
            cur = {"id": hm.group(1), "title": hm.group(2).strip(), "validation_results": []}
            milestones[cur["id"]] = cur
            continue
        if ht:
            flush_vr()
            cur = {"id": ht.group(1), "title": ht.group(2).strip(), "validation_results": []}
            tasks[cur["id"]] = cur
            continue
        if re.match(r"^##\s", ln):
            flush_vr()
            cur = None
            continue
        if cur is None:
            continue
        fm = FIELD_RE.match(ln)
        if fm:
            key = fm.group(1).strip().lower().replace(" ", "_")
            val = fm.group(2).strip()
            if key == "validation_results":
                flush_vr()
                if val and val not in ("[]",):
                    cur["validation_results"] = []  # inline non-empty unsupported; entries follow
                vr_lines, vr_target = [], cur
            elif key in ("dependencies", "touches", "tasks"):
                cur[key] = parse_list(val)
            else:
                if val in ("null", ""):
                    val = None
                cur[key] = val
        elif vr_lines is not None:
            vr_lines.append(ln)
    flush_vr()

    # normalize
    for t in tasks.values():
        t.setdefault("dependencies", [])
        t.setdefault("touches", [])
        t["status"] = (t.get("status") or "pending").strip()
        t["claimed_by"] = t.get("claimed_by")
        try:
            t["attempts"] = int(t.get("attempts") or 0)
        except (TypeError, ValueError):
            t["attempts"] = 0
    for m in milestones.values():
        m.setdefault("tasks", [])
        m["claimed_by"] = m.get("claimed_by")
        m["num"] = int(re.match(r"M0*(\d+)", m["id"]).group(1))
    return tasks, milestones


def dag_violations(tasks, milestones):
    """Returns (violations, warnings). Violations trip [BAD_DAG] → PLANNING;
    warnings (e.g. touches overlap) are planner-quality issues the dispatcher's
    runtime collision check already guards against — log but do not block."""
    v, w = [], []
    ids = set(tasks)
    for t in tasks.values():
        for dep in t["dependencies"]:
            if dep == t["id"]:
                v.append(f"self-ref: {t['id']} depends on itself")
            elif dep not in ids:
                v.append(f"orphan: {t['id']} depends on unknown {dep}")
    # cycle detection (iterative DFS, ignore orphan deps already reported)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in tasks}
    for root in tasks:
        if color[root] != WHITE:
            continue
        stack = [(root, iter([d for d in tasks[root]["dependencies"] if d in ids]))]
        color[root] = GRAY
        while stack:
            node, it = stack[-1]
            advanced = False
            for dep in it:
                if color[dep] == GRAY:
                    v.append(f"cycle: detected through {dep}")
                elif color[dep] == WHITE:
                    color[dep] = GRAY
                    stack.append((dep, iter([d for d in tasks[dep]["dependencies"] if d in ids])))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
    # milestone partition: every task in exactly one milestone's Tasks list
    if milestones:
        assigned = {}
        for m in milestones.values():
            for tid in m["tasks"]:
                if tid in assigned:
                    v.append(f"milestone-overlap: {tid} listed in both {assigned[tid]} and {m['id']}")
                assigned[tid] = m["id"]
                if tid not in ids:
                    v.append(f"milestone-orphan: {m['id']} lists unknown task {tid}")
        for tid in ids:
            if tid not in assigned:
                v.append(f"milestone-unassigned: {tid} belongs to no milestone")
    # same-milestone Touches overlap without dependency (planner self-check PR-013)
    for m in milestones.values():
        code = [tasks[tid] for tid in m["tasks"] if tid in tasks and tasks[tid].get("touches")]
        for i, a in enumerate(code):
            for b in code[i + 1:]:
                if set(a["touches"]) & set(b["touches"]):
                    if a["id"] not in b["dependencies"] and b["id"] not in a["dependencies"]:
                        w.append(
                            f"touches-overlap: {a['id']} and {b['id']} in {m['id']} share paths "
                            f"{sorted(set(a['touches']) & set(b['touches']))} without a dependency")
    return v, w


def cmd_dag_check():
    text = read(os.path.join(GID_DIR, "task_queue.md"))
    if text is None:
        die("task_queue.md not found")
    tasks, milestones = parse_task_queue(text)
    v, w = dag_violations(tasks, milestones)
    print(json.dumps({"ok": not v, "task_count": len(tasks),
                      "milestone_count": len(milestones), "violations": v,
                      "warnings": w},
                     ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- pool

def milestone_status(m, tasks):
    if m["claimed_by"]:
        return "validating"
    for tid in m["tasks"]:
        if tasks.get(tid, {}).get("status") != "done":
            return "pending"
    vrs = m.get("validation_results") or []
    if not vrs:
        return "tasks_done"
    latest = vrs[-1]
    if latest.get("verdict") == "pass":
        return "validated"
    if latest.get("escalate_to_blocked"):
        return "blocked"
    return "tasks_done"


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def cmd_pool(n_max=5, git_mode="worktree", max_worktrees=8):
    text = read(os.path.join(GID_DIR, "task_queue.md"))
    if text is None:
        die("task_queue.md not found")
    tasks, milestones = parse_task_queue(text)

    gs = load_git_state()
    existing_wt = len(gs.get("worktrees", {}))   # worktrees currently on disk (worktree mode)
    new_wt = 0                                    # new worktrees this batch would create

    ms_status = {mid: milestone_status(m, tasks) for mid, m in milestones.items()}
    active_ms = None
    for m in sorted(milestones.values(), key=lambda x: x["num"]):
        if ms_status[m["id"]] != "validated":
            active_ms = m["id"]
            break

    def created(t):
        return t.get("created") or ""

    pool, deferred = [], []
    touching = []   # [(task_id, set(touches))] of executors already in pool

    def collides(t):
        ts = set(t.get("touches") or [])
        if not ts:
            return None
        for tid, other in touching:
            if ts & other:
                return tid
        return None

    # P1 per-task validators
    for t in sorted([t for t in tasks.values() if t["status"] == "executed"], key=created):
        pool.append({"role": "validator", "mode": "task", "task_id": t["id"], "scratch": None})
    # P2 milestone validators
    for m in sorted([m for m in milestones.values() if ms_status[m["id"]] == "tasks_done"],
                    key=lambda x: x["num"]):
        pool.append({"role": "validator", "mode": "milestone", "task_id": m["id"], "scratch": None})
    # P3 rework executors
    for t in sorted([t for t in tasks.values() if t["status"] == "needs_rework"], key=created):
        c = collides(t)
        if c:
            deferred.append({"task_id": t["id"], "reason": f"touches conflict with {c}"})
            continue
        pool.append({"role": "executor", "task_id": t["id"],
                     "scratch": f"{GID_DIR}/workspace/exec-{t['id']}/"})
        if t.get("touches"):
            touching.append((t["id"], set(t["touches"])))
    # P4 new executors
    def p4_key(t):
        return (PRIORITY_ORDER.get((t.get("priority") or "medium").lower(), 1), created(t))
    for t in sorted([t for t in tasks.values()
                     if t["status"] == "pending"
                     and all(tasks.get(d, {}).get("status") == "done" for d in t["dependencies"])
                     and (active_ms is None or not milestones or t.get("milestone") == active_ms)],
                    key=p4_key):
        c = collides(t)
        if c:
            deferred.append({"task_id": t["id"], "reason": f"touches conflict with {c}"})
            continue
        # Worktree hard-cap backpressure: a new (P4) source-touching executor needs a fresh
        # worktree; defer it if we are already at max. Rework (P3) reuses an existing worktree.
        if git_mode == "worktree" and t.get("touches") and t["id"] not in gs.get("worktrees", {}):
            if existing_wt + new_wt >= max_worktrees:
                deferred.append({"task_id": t["id"], "reason": "wt_cap"})
                continue
            new_wt += 1
        pool.append({"role": "executor", "task_id": t["id"],
                     "scratch": f"{GID_DIR}/workspace/exec-{t['id']}/"})
        if t.get("touches"):
            touching.append((t["id"], set(t["touches"])))

    # Fallback (non-git) race guard for #6: a validator that runs build/test cannot share a
    # batch with a source-touching executor mutating the same shared tree. In worktree mode
    # this is structurally impossible (each runs in its own worktree), so the guard is skipped.
    if git_mode == "fallback":
        def is_exec_validator(item):
            return (item["role"] == "validator" and item.get("mode") == "task"
                    and (tasks.get(item["task_id"], {}).get("type") or "").lower() in EXECUTING_TYPES)
        def is_source_executor(item):
            return item["role"] == "executor" and bool(tasks.get(item["task_id"], {}).get("touches"))
        if any(is_exec_validator(i) for i in pool):
            kept = []
            for i in pool:
                if is_source_executor(i):
                    deferred.append({"task_id": i["task_id"], "reason": "fallback_race_guard"})
                else:
                    kept.append(i)
            pool = kept

    statuses = {}
    for t in tasks.values():
        statuses[t["status"]] = statuses.get(t["status"], 0) + 1

    out = {
        "batch": pool[:n_max],
        "pool_size": len(pool),
        "deferred": deferred,
        "active_milestone": active_ms,
        "milestone_status": ms_status,
        "task_status_counts": statuses,
        "all_done_and_validated": (
            len(tasks) > 0
            and all(t["status"] == "done" for t in tasks.values())
            and all(s == "validated" for s in ms_status.values())
        ),
        "any_blocked": any(t["status"] == "blocked" for t in tasks.values()),
        "any_in_flight": any(t["status"] in ("claimed", "validating") for t in tasks.values())
                         or any(m["claimed_by"] for m in milestones.values()),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- rqs

def cmd_rqs():
    text = read(os.path.join(GID_DIR, "research_requests.md"))
    if text is None:
        die("research_requests.md not found")
    rqs, cur = [], None
    for ln in text.splitlines():
        h = re.match(r"^###\s+(RQ-\w+)\s*$", ln)
        if h:
            cur = {"id": h.group(1), "status": "open", "claimed_by": None}
            rqs.append(cur)
            continue
        if cur is None:
            continue
        fm = FIELD_RE.match(ln)
        if fm:
            key = fm.group(1).strip().lower().replace(" ", "_")
            val = fm.group(2).strip()
            if key in ("status", "claimed_by"):
                cur[key] = None if val in ("null", "") else val
    open_unclaimed = [r["id"] for r in rqs if r["status"] == "open" and not r["claimed_by"]]
    open_claimed = [r["id"] for r in rqs if r["status"] == "open" and r["claimed_by"]]
    fulfilled_claimed = [r["id"] for r in rqs if r["status"] == "fulfilled" and r["claimed_by"]]
    print(json.dumps({"rqs": rqs, "open_unclaimed": sorted(open_unclaimed),
                      "open_claimed": sorted(open_claimed),
                      "fulfilled_with_stale_claim": sorted(fulfilled_claimed)},
                     ensure_ascii=False, indent=2))


# ---------------------------------------------------------- truncate-logs

def truncate_one(path, cap, keep, archive_dir):
    text = read(path)
    if text is None:
        return {"file": path, "skipped": "missing"}
    lines = text.splitlines(keepends=True)
    if len(lines) <= cap:
        return {"file": path, "skipped": f"under cap ({len(lines)} <= {cap})"}
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, os.path.basename(path))
    trimmed, kept = lines[:-keep], lines[-keep:]
    with open(archive_path, "a", encoding="utf-8") as f:
        f.writelines(trimmed)
        if trimmed and not trimmed[-1].endswith("\n"):
            f.write("\n")
    marker = f"{now_iso()} [TRUNCATE] {os.path.basename(path)} from {len(lines)} to {keep} (archived to {archive_path})\n"
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(kept)
        if kept and not kept[-1].endswith("\n"):
            f.write("\n")
        f.write(marker)
    return {"file": path, "truncated_from": len(lines), "kept": keep, "archive": archive_path}


def cmd_truncate_logs():
    archive_dir = os.path.join(GID_DIR, "archive")
    results = [
        truncate_one(os.path.join(GID_DIR, "progress_log.md"), 400, 200, archive_dir),
        truncate_one(os.path.join(GID_DIR, "validation_log.md"), 500, 250, archive_dir),
    ]
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- git helpers

def run_git(args, cwd=None):
    """Run a git command; return (returncode, stdout, stderr).
    stdout is rstrip'd of trailing newlines ONLY — leading whitespace is significant in
    `git status --porcelain` (the XY status column), so we must not strip the whole string."""
    p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout or "").rstrip("\r\n"), (p.stderr or "").strip()


def load_git_state():
    txt = read(GIT_STATE_PATH)
    state = dict(DEFAULT_GIT_STATE)
    if txt:
        try:
            loaded = json.loads(txt)
            if isinstance(loaded, dict):
                state.update(loaded)
        except (ValueError, TypeError):
            pass
    for k, v in DEFAULT_GIT_STATE.items():
        state.setdefault(k, v)
    return state


def save_git_state(state):
    os.makedirs(GID_DIR, exist_ok=True)
    with open(GIT_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def wt_path(tid):
    return os.path.join(WT_ROOT, tid)


def wt_branch(tid):
    return "gid/" + tid


def load_tasks():
    txt = read(os.path.join(GID_DIR, "task_queue.md"))
    if txt is None:
        return {}, {}
    return parse_task_queue(txt)


def link_one(name, dst_parent):
    """Best-effort symlink/junction <repo>/name into the worktree. Never fatal."""
    src = os.path.abspath(name)
    dst = os.path.join(dst_parent, name)
    if not os.path.exists(src) or os.path.lexists(dst):
        return False
    try:
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", dst, src],
                           capture_output=True, text=True)
        else:
            os.symlink(src, dst)
        return True
    except OSError:
        return False


def scoped_add(wt, link_dirs):
    """Stage all worktree changes EXCEPT .get-it-done/ and every link_dir (slash-less
    pathspec — a trailing slash fails past a symlink). This is the load-bearing guard that
    keeps state churn and symlinked deps out of source commits."""
    pathspec = [".", ":(exclude).get-it-done"] + [f":(exclude){d}" for d in link_dirs]
    return run_git(["-C", wt, "add", "-A", "--"] + pathspec)


def goal_slug():
    txt = read(os.path.join(GID_DIR, "goal.md")) or ""
    m = re.search(r"^##\s*Goal\s*\n+(.+)$", txt, re.M)
    base = (m.group(1).strip() if m else "goal")[:40]
    return re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").lower() or "goal"


def upstream_contains_head():
    """True if HEAD is already on the branch's upstream — rewriting would force-push. Skip then."""
    rc, up, _ = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if rc != 0 or not up:
        return False
    rc2, _, _ = run_git(["merge-base", "--is-ancestor", "HEAD", up])
    return rc2 == 0


# ---------------------------------------------------------------- git commands

def cmd_git_preflight():
    rc, out, _ = run_git(["rev-parse", "--is-inside-work-tree"])
    is_git = (rc == 0 and out == "true")
    dirty, head, supported = False, None, False
    if is_git:
        _, st, _ = run_git(["status", "--porcelain"])
        dirty = bool(st)
        rc3, head_out, _ = run_git(["rev-parse", "HEAD"])
        head = head_out if rc3 == 0 else None
        rc4, _, _ = run_git(["worktree", "list"])
        supported = rc4 == 0
    print(json.dumps({"is_git": is_git, "dirty": dirty,
                      "head_sha": head, "worktree_supported": supported}))


def cmd_worktree_add(tid):
    gs = load_git_state()
    path, branch = wt_path(tid), wt_branch(tid)
    _, head, _ = run_git(["rev-parse", "HEAD"])
    if os.path.isdir(path):
        print(json.dumps({"ok": True, "path": path, "branch": branch, "reused": True}))
        return
    os.makedirs(WT_ROOT, exist_ok=True)
    rcb, _, _ = run_git(["rev-parse", "--verify", "--quiet", branch])
    if rcb == 0:                                    # branch exists (blocked-retry / crash) → recreate WT
        rc, _, err = run_git(["worktree", "add", path, branch])
    else:                                           # first attempt → new branch + WT at HEAD
        rc, _, err = run_git(["worktree", "add", "-b", branch, path, "HEAD"])
    if rc != 0:
        print(json.dumps({"ok": False, "reason": err}))
        return
    linked = [d for d in gs.get("link_dirs", []) if link_one(d, path)]
    gs["worktrees"][tid] = {"branch": branch, "base": head, "created": now_iso()}
    save_git_state(gs)
    print(json.dumps({"ok": True, "path": path, "branch": branch,
                      "base_sha": head, "reused": False, "linked": linked}, ensure_ascii=False))


def cmd_worktree_commit_wip(tid, attempt):
    gs = load_git_state()
    if tid not in gs.get("worktrees", {}):
        print(json.dumps({"ok": True, "skipped": "no_worktree"}))
        return
    wt = wt_path(tid)
    scoped_add(wt, gs.get("link_dirs", []))
    _, staged, _ = run_git(["-C", wt, "diff", "--cached", "--name-only"])
    if not staged:
        print(json.dumps({"ok": True, "skipped": "no_changes"}))
        return
    rc, _, err = run_git(["-C", wt, "commit", "-m", f"wip({tid}): attempt {attempt}"])
    if rc != 0:
        print(json.dumps({"ok": False, "reason": err}))
        return
    _, sha, _ = run_git(["-C", wt, "rev-parse", "HEAD"])
    print(json.dumps({"ok": True, "wip_sha": sha}))


def cmd_worktree_merge(tid):
    gs = load_git_state()
    branch, wt = wt_branch(tid), wt_path(tid)
    rcb, _, _ = run_git(["rev-parse", "--verify", "--quiet", branch])
    if rcb != 0 and tid not in gs.get("worktrees", {}):
        print(json.dumps({"ok": True, "skipped": "already_merged"}))
        return
    # Ensure any last-moment worktree changes are committed to the branch.
    if os.path.isdir(wt):
        scoped_add(wt, gs.get("link_dirs", []))
        _, staged, _ = run_git(["-C", wt, "diff", "--cached", "--name-only"])
        if staged:
            run_git(["-C", wt, "commit", "-m", f"wip({tid}): pre-merge"])
    _, pre_head, _ = run_git(["rev-parse", "HEAD"])
    rcm, _, _ = run_git(["merge", "--squash", branch])
    if rcm != 0:
        _, confl, _ = run_git(["diff", "--name-only", "--diff-filter=U"])
        run_git(["reset", "--merge"])              # --abort does NOT work after a --squash conflict
        print(json.dumps({"ok": False, "reason": "conflict",
                          "files": [f for f in confl.splitlines() if f]}, ensure_ascii=False))
        return
    tasks, milestones = load_tasks()
    title = tasks.get(tid, {}).get("title", "")
    _, staged, _ = run_git(["diff", "--cached", "--name-only"])
    if staged:
        rc, _, err = run_git(["commit", "-m", f"{tid}: {title}"])   # NO -a → excludes .get-it-done churn
        if rc != 0:
            print(json.dumps({"ok": False, "reason": err}))
            return
        _, commit_sha, _ = run_git(["rev-parse", "HEAD"])
    else:
        commit_sha = pre_head                        # empty diff (no-op merge)
    M = tasks.get(tid, {}).get("milestone")
    if M and M not in gs["milestone_bases"]:
        gs["milestone_bases"][M] = pre_head
    if not gs.get("goal_base"):
        gs["goal_base"] = pre_head
    if os.path.isdir(wt):
        run_git(["worktree", "remove", "--force", wt])
    run_git(["worktree", "prune"])
    run_git(["branch", "-D", branch])
    gs.get("worktrees", {}).pop(tid, None)
    save_git_state(gs)
    print(json.dumps({"ok": True, "merged_sha": commit_sha}))


def cmd_worktree_drop(tid, keep_branch):
    gs = load_git_state()
    wt, branch = wt_path(tid), wt_branch(tid)
    if os.path.isdir(wt):
        run_git(["worktree", "remove", "--force", wt])
    run_git(["worktree", "prune"])
    if not keep_branch:
        run_git(["branch", "-D", branch])
    gs.get("worktrees", {}).pop(tid, None)
    save_git_state(gs)
    print(json.dumps({"ok": True}))


LIVE_WT_STATUSES = {"claimed", "executed", "validating", "needs_rework"}


def cmd_worktree_gc():
    gs = load_git_state()
    tasks, _ = load_tasks()
    live = {tid for tid, t in tasks.items()
            if t.get("touches") and t.get("status") in LIVE_WT_STATUSES}
    run_git(["worktree", "prune"])
    removed, kept = [], []
    if os.path.isdir(WT_ROOT):
        for name in sorted(os.listdir(WT_ROOT)):
            p = os.path.join(WT_ROOT, name)
            if not os.path.isdir(p):
                continue
            if name in live:
                kept.append(name)
                continue
            run_git(["worktree", "remove", "--force", p])
            if tasks.get(name, {}).get("status") != "blocked":
                run_git(["branch", "-D", wt_branch(name)])
            gs.get("worktrees", {}).pop(name, None)
            removed.append(name)
    run_git(["worktree", "prune"])
    save_git_state(gs)
    print(json.dumps({"removed": removed, "kept": kept}, ensure_ascii=False))


def cmd_worktree_reset_all():
    _, out, _ = run_git(["worktree", "list", "--porcelain"])
    wt_abs = os.path.abspath(WT_ROOT)
    for line in out.splitlines():
        if line.startswith("worktree "):
            p = line[len("worktree "):].strip()
            if os.path.abspath(p).startswith(wt_abs):
                run_git(["worktree", "remove", "--force", p])
    run_git(["worktree", "prune"])
    _, branches, _ = run_git(["for-each-ref", "--format=%(refname:short)", "refs/heads/gid/"])
    for b in branches.splitlines():
        if b.strip():
            run_git(["branch", "-D", b.strip()])
    if os.path.isdir(WT_ROOT):
        shutil.rmtree(WT_ROOT, ignore_errors=True)
    gs = load_git_state()
    gs["worktrees"], gs["milestone_bases"], gs["goal_base"] = {}, {}, None
    save_git_state(gs)
    print(json.dumps({"ok": True}))


def _stray_source_paths(link_dirs):
    """Lines from git status --porcelain that are source (not .get-it-done/ or a link_dir)."""
    _, out, _ = run_git(["status", "--porcelain", "--untracked-files=all"])
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        code, path = line[:2], line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        norm = path.replace("\\", "/")
        if norm.startswith(".get-it-done/"):
            continue
        if any(norm == d or norm.startswith(d + "/") for d in link_dirs):
            continue
        rows.append((code, path))
    return rows


def cmd_check_stray_edits(tid, revert):
    gs = load_git_state()
    rows = _stray_source_paths(gs.get("link_dirs", []))
    dirty = [p for _, p in rows]
    reverted = False
    if revert and rows:
        tracked = [p for code, p in rows if code.strip() != "??"]
        untracked = [p for code, p in rows if code.strip() == "??"]
        if tracked:
            run_git(["checkout", "--"] + tracked)
        if untracked:
            run_git(["clean", "-fdq", "--"] + untracked)
        reverted = True
    print(json.dumps({"ok": True, "dirty_source": dirty, "reverted": reverted}, ensure_ascii=False))


def _consolidate(base, msg_subject, msg_body, label):
    if not base:
        print(json.dumps({"ok": True, "skipped": "no_base"}))
        return
    if upstream_contains_head():
        print(json.dumps({"ok": True, "skipped": "upstream"}))
        return
    _, cnt, _ = run_git(["rev-list", "--count", f"{base}..HEAD"])
    if int(cnt or "0") <= 1:
        print(json.dumps({"ok": True, "skipped": "already_consolidated"}))
        return
    run_git(["branch", "-f", f"gid/pre-consolidate-{goal_slug()}", "HEAD"])
    rc, _, err = run_git(["reset", "--soft", base])
    if rc != 0:
        print(json.dumps({"ok": False, "reason": err}))
        return
    rc2, _, err2 = run_git(["commit", "-m", msg_subject, "-m", msg_body])
    if rc2 != 0:
        print(json.dumps({"ok": False, "reason": err2}))
        return
    _, sha, _ = run_git(["rev-parse", "HEAD"])
    print(json.dumps({"ok": True, "commit_sha": sha, "label": label}, ensure_ascii=False))


def cmd_consolidate_milestone(mid):
    gs = load_git_state()
    base = gs.get("milestone_bases", {}).get(mid)
    tasks, milestones = load_tasks()
    title = milestones.get(mid, {}).get("title", "")
    body = "\n".join(f"- {tid}: {tasks.get(tid, {}).get('title', '')}"
                     for tid in milestones.get(mid, {}).get("tasks", []))
    _consolidate(base, f"{mid}: {title}", body or f"{mid} tasks", mid)


def cmd_consolidate_final():
    gs = load_git_state()
    base = gs.get("goal_base")
    _, milestones = load_tasks()
    goal_txt = read(os.path.join(GID_DIR, "goal.md")) or ""
    m = re.search(r"^##\s*Goal\s*\n+(.+)$", goal_txt, re.M)
    subject = (m.group(1).strip() if m else "goal")[:72]
    body = "\n".join(f"- {mid}: {milestones[mid].get('title', '')}"
                     for mid in sorted(milestones, key=lambda x: milestones[x].get("num", 0)))
    _consolidate(base, subject, body or "goal milestones", "final")


# ---------------------------------------------------------------- arg helpers

def _flag(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default
    return default


def _positional():
    """First non-flag token after the subcommand (argv[2]), if it isn't a --flag."""
    return sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None


# ---------------------------------------------------------------- main

def main():
    if len(sys.argv) < 2:
        die("usage: gid.py <state|dag-check|pool|rqs|batch-id|truncate-logs|"
            "git-preflight|worktree-add|worktree-commit-wip|worktree-merge|worktree-drop|"
            "worktree-gc|worktree-reset-all|check-stray-edits|consolidate-milestone|consolidate-final>")
    cmd = sys.argv[1]
    tid = _positional()

    if cmd == "pool":
        cmd_pool(git_mode=_flag("--git-mode", "worktree"),
                 max_worktrees=int(_flag("--max-worktrees", "8")))
        return
    if cmd == "worktree-add":
        cmd_worktree_add(tid); return
    if cmd == "worktree-commit-wip":
        cmd_worktree_commit_wip(tid, _flag("--attempt", "0")); return
    if cmd == "worktree-merge":
        cmd_worktree_merge(tid); return
    if cmd == "worktree-drop":
        cmd_worktree_drop(tid, "--keep-branch" in sys.argv); return
    if cmd == "check-stray-edits":
        cmd_check_stray_edits(tid, "--revert" in sys.argv); return
    if cmd == "consolidate-milestone":
        cmd_consolidate_milestone(tid); return

    {
        "state": cmd_state,
        "dag-check": cmd_dag_check,
        "rqs": cmd_rqs,
        "batch-id": cmd_batch_id,
        "truncate-logs": cmd_truncate_logs,
        "git-preflight": cmd_git_preflight,
        "worktree-gc": cmd_worktree_gc,
        "worktree-reset-all": cmd_worktree_reset_all,
        "consolidate-final": cmd_consolidate_final,
    }.get(cmd, lambda: die(f"unknown subcommand: {cmd}"))()


if __name__ == "__main__":
    main()
