#!/usr/bin/env python3
"""bootstrap.py — workspace initializer for the get-it-done plugin.

Handles template copying and per-goal reset so SKILL.md does not need to run
platform-specific shell commands (rsync / robocopy / cp) directly.

PLUGIN_ROOT is self-derived from __file__ — no --plugin-root parameter needed.
--base defaults to cwd (back-compat: single-goal at repo root when GID_BASE unset).

Subcommands (all emit JSON on stdout):
  init   --base <GID_BASE> --plugin-data <PLUGIN_DATA>
         Copy templates → destinations (skip-existing). Idempotent.
         Used by /objective Step 0 and /continue Step 0.

  reset  --base <GID_BASE>
         Force-copy per-goal scaffold files + clear workspace, stale findings,
         and leftover prd/plan_audit artifacts from a prior goal.
         Used by /objective Step 4.

Exit codes:
  0 — success (check JSON "ok" field)
  2 — fatal error (bad args, missing templates, filesystem failure)
"""

import json
import os
import shutil
import sys
from pathlib import Path

# Self-derive: this file lives at <plugin-root>/skills/objective/scripts/bootstrap.py
# parent        → scripts/
# parent.parent → objective/
# parent.parent.parent → skills/
# parent.parent.parent.parent → <plugin-root>/
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATES_GID = PLUGIN_ROOT / "templates" / ".get-it-done"
TEMPLATES_TL = PLUGIN_ROOT / "templates" / "team_learnings"

# Files that must be force-copied on goal reset (not skip-existing)
PER_GOAL_RESET_FILES = [
    "task_queue.md",
    "metrics.md",
    "research_requests.md",
]


def die(msg: str):
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(2)


def copy_tree_skip_existing(src: Path, dst: Path, copied: list, skipped: list):
    """Recursively copy src → dst, skipping files that already exist at dst."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            if target.exists():
                skipped.append(str(rel))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                copied.append(str(rel))


def cmd_init(args: dict):
    base = Path(args.get("base", ".")).resolve()
    plugin_data_raw = args.get("plugin_data")
    if not plugin_data_raw:
        die("--plugin-data is required for init")
    plugin_data = Path(plugin_data_raw).expanduser().resolve()

    if not TEMPLATES_GID.exists():
        die(f"templates/.get-it-done not found: {TEMPLATES_GID}")
    if not TEMPLATES_TL.exists():
        die(f"templates/team_learnings not found: {TEMPLATES_TL}")

    created_dirs = []
    copied = []
    skipped = []

    # Ensure required subdirs exist (even if templates don't have them)
    for subdir in ["context", "findings", "workspace", "archive"]:
        target = base / ".get-it-done" / subdir
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(target.relative_to(base)))

    # A-side: cross-project team_learnings (skip-existing)
    tl_dst = plugin_data / "team_learnings"
    tl_dst.mkdir(parents=True, exist_ok=True)
    copy_tree_skip_existing(TEMPLATES_TL, tl_dst, copied, skipped)

    # B-side: per-goal .get-it-done (skip-existing)
    gid_dst = base / ".get-it-done"
    copy_tree_skip_existing(TEMPLATES_GID, gid_dst, copied, skipped)

    print(json.dumps({
        "ok": True,
        "created_dirs": created_dirs,
        "copied": copied,
        "skipped": skipped,
    }))


def cmd_reset(args: dict):
    base = Path(args.get("base", ".")).resolve()
    gid = base / ".get-it-done"

    if not gid.exists():
        die(f".get-it-done not found at {gid} — run init first")

    force_copied = []
    deleted = []

    # Force-copy per-goal scaffold files (overwrite whatever was there)
    for name in PER_GOAL_RESET_FILES:
        src = TEMPLATES_GID / name
        if not src.exists():
            die(f"template file not found: {src}")
        shutil.copy2(src, gid / name)
        force_copied.append(name)

    # Force-copy findings/_meta.md
    findings_meta_src = TEMPLATES_GID / "findings" / "_meta.md"
    if findings_meta_src.exists():
        findings_meta_dst = gid / "findings" / "_meta.md"
        findings_meta_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(findings_meta_src, findings_meta_dst)
        force_copied.append("findings/_meta.md")

    # Delete per-request findings files from the prior goal
    for f in (gid / "findings").glob("RQ-*.md"):
        f.unlink()
        deleted.append(f"findings/{f.name}")

    # Clear executor scratch workspace
    workspace = gid / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
        deleted.append("workspace/")
    workspace.mkdir(parents=True, exist_ok=True)

    # Remove stale planner artifacts
    for name in ["prd.md", "plan_audit.md"]:
        p = gid / name
        if p.exists():
            p.unlink()
            deleted.append(name)

    print(json.dumps({
        "ok": True,
        "force_copied": force_copied,
        "deleted": deleted,
    }))


def parse_args(argv: list):
    if len(argv) < 2:
        die("Usage: bootstrap.py <init|reset> [--base <path>] [--plugin-data <path>]")
    cmd = argv[1]
    args = {}
    i = 2
    while i < len(argv):
        if argv[i] == "--base" and i + 1 < len(argv):
            args["base"] = argv[i + 1]
            i += 2
        elif argv[i] == "--plugin-data" and i + 1 < len(argv):
            args["plugin_data"] = argv[i + 1]
            i += 2
        else:
            die(f"Unknown argument: {argv[i]}")
    return cmd, args


def main():
    cmd, args = parse_args(sys.argv)
    if cmd == "init":
        cmd_init(args)
    elif cmd == "reset":
        cmd_reset(args)
    else:
        die(f"Unknown subcommand: {cmd!r}. Use 'init' or 'reset'.")


if __name__ == "__main__":
    main()
