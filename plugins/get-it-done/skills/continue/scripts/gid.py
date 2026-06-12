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
import sys
from datetime import datetime, timezone

GID_DIR = ".get-it-done"


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


def cmd_pool(n_max=5):
    text = read(os.path.join(GID_DIR, "task_queue.md"))
    if text is None:
        die("task_queue.md not found")
    tasks, milestones = parse_task_queue(text)

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
        pool.append({"role": "executor", "task_id": t["id"],
                     "scratch": f"{GID_DIR}/workspace/exec-{t['id']}/"})
        if t.get("touches"):
            touching.append((t["id"], set(t["touches"])))

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


# ---------------------------------------------------------------- main

def main():
    if len(sys.argv) < 2:
        die("usage: gid.py <state|dag-check|pool|rqs|batch-id|truncate-logs>")
    cmd = sys.argv[1]
    {
        "state": cmd_state,
        "dag-check": cmd_dag_check,
        "pool": cmd_pool,
        "rqs": cmd_rqs,
        "batch-id": cmd_batch_id,
        "truncate-logs": cmd_truncate_logs,
    }.get(cmd, lambda: die(f"unknown subcommand: {cmd}"))()


if __name__ == "__main__":
    main()
