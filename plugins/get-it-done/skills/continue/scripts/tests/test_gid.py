#!/usr/bin/env python3
"""Tests for gid.py — the get-it-done dispatcher helper script.

Stdlib-only (unittest), matching gid.py's own no-install-required philosophy.

Run:
  python3 -m unittest discover -s plugins/get-it-done/skills/continue/scripts/tests -p "test_*.py" -v
  # or directly:
  python3 plugins/get-it-done/skills/continue/scripts/tests/test_gid.py

Two suites:
  - Pure-logic tests (no subprocess git): parse_state, parse_task_queue (incl. the
    in_milestones section-boundary regression), dag_violations, milestone_status,
    cmd_pool priority/collision/cap behavior, batch-id, truncate-logs.
  - Git integration tests: build a real temp git repo and exercise
    goal-worktree-init -> worktree-add -> worktree-commit-wip -> worktree-merge
    (including the conflict path) -> consolidate-milestone -> goal-reset ->
    worktree-gc. Skipped automatically if `git` is not on PATH.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

GID_PY = Path(__file__).resolve().parent.parent / "gid.py"

_spec = importlib.util.spec_from_file_location("gid", GID_PY)
gid = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gid)


def capture_json(func, *args, **kwargs):
    """Call a cmd_* function that prints JSON to stdout; return the parsed object."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        func(*args, **kwargs)
    return json.loads(buf.getvalue())


@contextlib.contextmanager
def temp_project(files=None):
    """A temp cwd containing a .get-it-done/ dir pre-populated with `files`
    ({relative_path: content}), chdir'd into for the duration of the block."""
    d = tempfile.mkdtemp()
    old_cwd = os.getcwd()
    try:
        gid_dir = os.path.join(d, gid.GID_DIR)
        os.makedirs(gid_dir, exist_ok=True)
        for rel, content in (files or {}).items():
            path = os.path.join(d, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        os.chdir(d)
        yield d
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(d, ignore_errors=True)


# ============================================================ parse_state

class TestParseState(unittest.TestCase):
    def test_basic_fields(self):
        text = """# Team State
```yaml
schema_version: 2
phase: EXECUTING
status: RUNNING
batch_id: "B0007"
batch_started_at: 2026-01-01T00:00:00Z
batch_ended_at: null
active_agents:
  - role: executor
    task_id: T-001
  - role: validator
    task_id: T-002
goal_set: true
last_updated: 2026-01-01T00:00:00Z
```
"""
        st = gid.parse_state(text)
        self.assertEqual(st["schema_version"], 2)
        self.assertEqual(st["phase"], "EXECUTING")
        self.assertEqual(st["status"], "RUNNING")
        self.assertEqual(st["batch_id"], "B0007")
        self.assertIsNone(st["batch_ended_at"])
        self.assertTrue(st["goal_set"])
        self.assertEqual(st["active_agent_count"], 2)
        self.assertEqual(st["active_agent_roles"], ["executor", "validator"])

    def test_idle_state(self):
        text = """```yaml
schema_version: 2
phase: IDLE
status: WAITING
batch_id: null
batch_started_at: null
batch_ended_at: null
active_agents: []
goal_set: false
last_updated: null
```
"""
        st = gid.parse_state(text)
        self.assertEqual(st["phase"], "IDLE")
        self.assertFalse(st["goal_set"])
        self.assertEqual(st["active_agent_count"], 0)


# ======================================================== parse_task_queue

class TestParseTaskQueue(unittest.TestCase):
    def test_basic_task_fields(self):
        text = """## Tasks

### T-001: Do the thing
- **Status**: pending
- **Dependencies**: []
- **Touches**: ["src/a.ts", "src/b.ts"]
- **Attempts**: 0
- **Milestone**: M1
"""
        tasks, milestones = gid.parse_task_queue(text)
        self.assertIn("T-001", tasks)
        t = tasks["T-001"]
        self.assertEqual(t["status"], "pending")
        self.assertEqual(t["dependencies"], [])
        self.assertEqual(t["touches"], ["src/a.ts", "src/b.ts"])
        self.assertEqual(t["attempts"], 0)
        self.assertEqual(t["milestone"], "M1")
        self.assertEqual(milestones, {})

    def test_dependencies_parsed_as_list(self):
        text = """### T-002: Second task
- **Status**: pending
- **Dependencies**: [T-001]
"""
        tasks, _ = gid.parse_task_queue(text)
        self.assertEqual(tasks["T-002"]["dependencies"], ["T-001"])

    def test_milestones_section_parsed(self):
        text = """### T-001: A
- **Status**: done

## Milestones

### M1: First milestone
- **Tasks**: [T-001]
- **Claimed_by**: null
"""
        tasks, milestones = gid.parse_task_queue(text)
        self.assertIn("T-001", tasks)
        self.assertIn("M1", milestones)
        self.assertEqual(milestones["M1"]["tasks"], ["T-001"])
        self.assertEqual(milestones["M1"]["num"], 1)

    def test_in_milestones_flag_resets_on_any_section_header(self):
        """Regression: a `## <anything>` header after `## Milestones` must reset the
        in_milestones flag, otherwise a `### T-XXX:` heading appearing after it would
        never be recognized as a task (TASK_HEAD_RE is only tried when NOT in_milestones).
        Mirrors the real-world bug fixed in commit 16db9d5."""
        text = """### T-001: A
- **Status**: done

## Milestones

### M1: First milestone
- **Tasks**: [T-001]

## Notes

### T-002: Stray task after an unrelated section
- **Status**: pending
"""
        tasks, milestones = gid.parse_task_queue(text)
        self.assertIn("T-001", tasks)
        self.assertIn("M1", milestones)
        self.assertIn("T-002", tasks, "T-002 must be parsed as a task — in_milestones "
                                       "should have reset at '## Notes', not stayed True")
        self.assertNotIn("T-002", milestones)

    def test_validation_results_parsed(self):
        text = """### T-001: A
- **Status**: needs_rework
- **Validation Results**:
  - attempt_no: 1
    verdict: fail
    escalate_to_blocked: false
  - attempt_no: 2
    verdict: pass
    escalate_to_blocked: false
"""
        tasks, _ = gid.parse_task_queue(text)
        vr = tasks["T-001"]["validation_results"]
        self.assertEqual(len(vr), 2)
        self.assertEqual(vr[0], {"attempt_no": 1, "verdict": "fail", "escalate_to_blocked": False})
        self.assertEqual(vr[1]["verdict"], "pass")

    def test_defaults_applied(self):
        text = "### T-001: Minimal task\n"
        tasks, _ = gid.parse_task_queue(text)
        t = tasks["T-001"]
        self.assertEqual(t["status"], "pending")
        self.assertEqual(t["dependencies"], [])
        self.assertEqual(t["touches"], [])
        self.assertEqual(t["attempts"], 0)
        self.assertIsNone(t["claimed_by"])


# ========================================================== dag_violations

class TestDagViolations(unittest.TestCase):
    def _tasks(self, spec):
        """spec: {id: {deps, touches, milestone}} -> tasks dict shaped like parse_task_queue output."""
        tasks = {}
        for tid, s in spec.items():
            tasks[tid] = {
                "id": tid, "title": tid, "validation_results": [],
                "dependencies": s.get("deps", []),
                "touches": s.get("touches", []),
                "milestone": s.get("milestone"),
                "status": s.get("status", "pending"),
                "claimed_by": None, "attempts": 0,
            }
        return tasks

    def test_no_violations_clean_dag(self):
        tasks = self._tasks({"T-001": {}, "T-002": {"deps": ["T-001"]}})
        v, w = gid.dag_violations(tasks, {})
        self.assertEqual(v, [])
        self.assertEqual(w, [])

    def test_self_reference(self):
        tasks = self._tasks({"T-001": {"deps": ["T-001"]}})
        v, w = gid.dag_violations(tasks, {})
        self.assertTrue(any("self-ref" in x for x in v))

    def test_orphan_dependency(self):
        tasks = self._tasks({"T-001": {"deps": ["T-999"]}})
        v, w = gid.dag_violations(tasks, {})
        self.assertTrue(any("orphan" in x for x in v))

    def test_cycle_detected(self):
        tasks = self._tasks({
            "T-001": {"deps": ["T-002"]},
            "T-002": {"deps": ["T-003"]},
            "T-003": {"deps": ["T-001"]},
        })
        v, w = gid.dag_violations(tasks, {})
        self.assertTrue(any("cycle" in x for x in v))

    def test_touches_overlap_is_warning_not_violation(self):
        tasks = self._tasks({
            "T-001": {"touches": ["src/a.ts"], "milestone": "M1"},
            "T-002": {"touches": ["src/a.ts"], "milestone": "M1"},
        })
        milestones = {"M1": {"id": "M1", "num": 1, "tasks": ["T-001", "T-002"], "claimed_by": None}}
        v, w = gid.dag_violations(tasks, milestones)
        self.assertEqual(v, [])
        self.assertTrue(any("touches-overlap" in x for x in w))

    def test_touches_overlap_suppressed_when_dependent(self):
        tasks = self._tasks({
            "T-001": {"touches": ["src/a.ts"], "milestone": "M1"},
            "T-002": {"touches": ["src/a.ts"], "milestone": "M1", "deps": ["T-001"]},
        })
        milestones = {"M1": {"id": "M1", "num": 1, "tasks": ["T-001", "T-002"], "claimed_by": None}}
        v, w = gid.dag_violations(tasks, milestones)
        self.assertEqual(w, [])

    def test_milestone_unassigned_task(self):
        tasks = self._tasks({"T-001": {}, "T-002": {}})
        milestones = {"M1": {"id": "M1", "num": 1, "tasks": ["T-001"], "claimed_by": None}}
        v, w = gid.dag_violations(tasks, milestones)
        self.assertTrue(any("milestone-unassigned" in x and "T-002" in x for x in v))

    def test_milestone_overlap(self):
        tasks = self._tasks({"T-001": {}})
        milestones = {
            "M1": {"id": "M1", "num": 1, "tasks": ["T-001"], "claimed_by": None},
            "M2": {"id": "M2", "num": 2, "tasks": ["T-001"], "claimed_by": None},
        }
        v, w = gid.dag_violations(tasks, milestones)
        self.assertTrue(any("milestone-overlap" in x for x in v))

    def test_milestone_orphan_task_ref(self):
        tasks = self._tasks({"T-001": {}})
        milestones = {"M1": {"id": "M1", "num": 1, "tasks": ["T-001", "T-999"], "claimed_by": None}}
        v, w = gid.dag_violations(tasks, milestones)
        self.assertTrue(any("milestone-orphan" in x for x in v))


# ========================================================= milestone_status

class TestMilestoneStatus(unittest.TestCase):
    def _milestone(self, tasks_list, claimed_by=None, vrs=None):
        return {"id": "M1", "num": 1, "tasks": tasks_list, "claimed_by": claimed_by,
                "validation_results": vrs or []}

    def test_validating_when_claimed(self):
        m = self._milestone(["T-001"], claimed_by="mval-M1")
        tasks = {"T-001": {"status": "done"}}
        self.assertEqual(gid.milestone_status(m, tasks), "validating")

    def test_pending_when_task_not_done(self):
        m = self._milestone(["T-001", "T-002"])
        tasks = {"T-001": {"status": "done"}, "T-002": {"status": "pending"}}
        self.assertEqual(gid.milestone_status(m, tasks), "pending")

    def test_single_task_milestone_auto_validates(self):
        m = self._milestone(["T-001"])
        tasks = {"T-001": {"status": "done"}}
        self.assertEqual(gid.milestone_status(m, tasks), "validated")

    def test_multi_task_milestone_needs_validator_when_all_done(self):
        m = self._milestone(["T-001", "T-002"])
        tasks = {"T-001": {"status": "done"}, "T-002": {"status": "done"}}
        self.assertEqual(gid.milestone_status(m, tasks), "tasks_done")

    def test_validated_after_pass_verdict(self):
        m = self._milestone(["T-001", "T-002"],
                            vrs=[{"attempt_no": 1, "verdict": "pass", "escalate_to_blocked": False}])
        tasks = {"T-001": {"status": "done"}, "T-002": {"status": "done"}}
        self.assertEqual(gid.milestone_status(m, tasks), "validated")

    def test_blocked_after_escalation(self):
        m = self._milestone(["T-001", "T-002"],
                            vrs=[{"attempt_no": 1, "verdict": "fail", "escalate_to_blocked": True}])
        tasks = {"T-001": {"status": "done"}, "T-002": {"status": "done"}}
        self.assertEqual(gid.milestone_status(m, tasks), "blocked")

    def test_tasks_done_after_fail_without_escalation(self):
        m = self._milestone(["T-001", "T-002"],
                            vrs=[{"attempt_no": 1, "verdict": "fail", "escalate_to_blocked": False}])
        tasks = {"T-001": {"status": "done"}, "T-002": {"status": "done"}}
        self.assertEqual(gid.milestone_status(m, tasks), "tasks_done")


# ================================================================ cmd_pool

TASK_TMPL = """### {id}: {title}
- **Status**: {status}
- **Dependencies**: {deps}
- **Touches**: {touches}
- **Attempts**: {attempts}
- **Milestone**: {milestone}
"""


def task_block(id, title="t", status="pending", deps=None, touches=None, attempts=0, milestone="M1"):
    return TASK_TMPL.format(
        id=id, title=title, status=status,
        deps="[" + ", ".join(deps or []) + "]",
        touches="[" + ", ".join(f'"{t}"' for t in (touches or [])) + "]",
        attempts=attempts, milestone=milestone,
    )


class TestCmdPool(unittest.TestCase):
    def test_priority_order_validators_before_executors(self):
        text = ("## Tasks\n"
                + task_block("T-001", status="executed")
                + task_block("T-002", status="pending"))
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_pool)
        roles = [(i["role"], i["task_id"]) for i in out["batch"]]
        self.assertEqual(roles[0], ("validator", "T-001"))
        self.assertEqual(roles[1], ("executor", "T-002"))

    def test_rework_before_new_pending(self):
        text = ("## Tasks\n"
                + task_block("T-001", status="pending")
                + task_block("T-002", status="needs_rework"))
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_pool)
        roles = [i["task_id"] for i in out["batch"]]
        self.assertEqual(roles[0], "T-002")  # rework (P3) before new pending (P4)
        self.assertEqual(roles[1], "T-001")

    def test_touches_collision_defers_second_executor(self):
        text = ("## Tasks\n"
                + task_block("T-001", status="pending", touches=["src/a.ts"])
                + task_block("T-002", status="pending", touches=["src/a.ts"]))
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_pool)
        batch_ids = [i["task_id"] for i in out["batch"]]
        self.assertIn("T-001", batch_ids)
        self.assertNotIn("T-002", batch_ids)
        self.assertEqual(out["deferred"][0]["task_id"], "T-002")
        self.assertIn("touches conflict", out["deferred"][0]["reason"])

    def test_no_collision_when_touches_disjoint(self):
        text = ("## Tasks\n"
                + task_block("T-001", status="pending", touches=["src/a.ts"])
                + task_block("T-002", status="pending", touches=["src/b.ts"]))
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_pool)
        batch_ids = [i["task_id"] for i in out["batch"]]
        self.assertIn("T-001", batch_ids)
        self.assertIn("T-002", batch_ids)

    def test_max_parallel_cap_defers_excess_source_executors(self):
        text = "## Tasks\n" + "".join(
            task_block(f"T-{n:03d}", status="pending", touches=[f"src/{n}.ts"])
            for n in range(1, 4)
        )
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_pool, git_mode="worktree", max_parallel=2)
        batch_ids = {i["task_id"] for i in out["batch"]}
        self.assertEqual(len(batch_ids & {"T-001", "T-002", "T-003"}), 2)
        deferred_reasons = {d["task_id"]: d["reason"] for d in out["deferred"]}
        self.assertEqual(len(deferred_reasons), 1)
        self.assertIn("max_parallel", list(deferred_reasons.values())[0])

    def test_batch_capped_at_n_max(self):
        text = "## Tasks\n" + "".join(
            task_block(f"T-{n:03d}", status="pending") for n in range(1, 8)
        )
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_pool)
        self.assertEqual(len(out["batch"]), 5)
        self.assertEqual(out["pool_size"], 7)

    def test_milestone_gate_blocks_downstream_task(self):
        text = ("## Tasks\n"
                + task_block("T-001", status="pending", milestone="M1")
                + task_block("T-002", status="pending", milestone="M2")
                + "\n## Milestones\n"
                  "### M1: First\n- **Tasks**: [T-001]\n- **Claimed_by**: null\n"
                  "### M2: Second\n- **Tasks**: [T-002]\n- **Claimed_by**: null\n")
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_pool)
        batch_ids = [i["task_id"] for i in out["batch"]]
        self.assertIn("T-001", batch_ids)
        self.assertNotIn("T-002", batch_ids, "T-002 is in M2 and M1 is not yet validated")

    def test_all_done_and_validated(self):
        text = ("## Tasks\n" + task_block("T-001", status="done", milestone="M1")
                + "\n## Milestones\n### M1: First\n- **Tasks**: [T-001]\n- **Claimed_by**: null\n")
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_pool)
        self.assertEqual(out["batch"], [])
        self.assertTrue(out["all_done_and_validated"])

    def test_any_blocked_flag(self):
        text = "## Tasks\n" + task_block("T-001", status="blocked")
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_pool)
        self.assertTrue(out["any_blocked"])


# ================================================================ batch-id

class TestBatchId(unittest.TestCase):
    def test_starts_at_b0001_when_no_history(self):
        state = "```yaml\nbatch_id: null\n```\n"
        with temp_project({os.path.join(gid.GID_DIR, "state.md"): state}):
            out = capture_json(gid.cmd_batch_id)
        self.assertEqual(out["next_batch_id"], "B0001")

    def test_increments_past_batch_history(self):
        state = ("```yaml\nbatch_id: null\n```\n\n"
                 "## Batch B0003 — start -> end\n- executor T-001 -> completed\n\n"
                 "## Batch B0005 — start -> end\n- executor T-002 -> completed\n")
        with temp_project({os.path.join(gid.GID_DIR, "state.md"): state}):
            out = capture_json(gid.cmd_batch_id)
        self.assertEqual(out["next_batch_id"], "B0006")

    def test_considers_current_in_flight_batch_id(self):
        state = "```yaml\nbatch_id: \"B0010\"\n```\n\n## Batch B0009 — a -> b\n"
        with temp_project({os.path.join(gid.GID_DIR, "state.md"): state}):
            out = capture_json(gid.cmd_batch_id)
        self.assertEqual(out["next_batch_id"], "B0011")


# =========================================================== truncate-logs

class TestTruncateLogs(unittest.TestCase):
    def test_under_cap_is_noop(self):
        content = "".join(f"line {n}\n" for n in range(10))
        with temp_project({os.path.join(gid.GID_DIR, "progress_log.md"): content}) as d:
            gid.truncate_one(os.path.join(gid.GID_DIR, "progress_log.md"), 400, 200,
                             os.path.join(gid.GID_DIR, "archive"))
            with open(os.path.join(gid.GID_DIR, "progress_log.md"), encoding="utf-8") as f:
                self.assertEqual(f.read(), content)
            self.assertFalse(os.path.isdir(os.path.join(d, gid.GID_DIR, "archive")))

    def test_over_cap_archives_and_truncates(self):
        content = "".join(f"line {n}\n" for n in range(500))
        with temp_project({os.path.join(gid.GID_DIR, "progress_log.md"): content}) as d:
            result = gid.truncate_one(os.path.join(gid.GID_DIR, "progress_log.md"), 400, 200,
                                      os.path.join(gid.GID_DIR, "archive"))
            self.assertEqual(result["truncated_from"], 500)
            self.assertEqual(result["kept"], 200)
            with open(os.path.join(gid.GID_DIR, "progress_log.md"), encoding="utf-8") as f:
                live_lines = f.readlines()
            # 200 kept lines + the [TRUNCATE] marker line
            self.assertEqual(len(live_lines), 201)
            self.assertIn("line 300", live_lines[0])  # first of the last 200 original lines
            self.assertIn("[TRUNCATE]", live_lines[-1])
            archive_path = os.path.join(d, gid.GID_DIR, "archive", "progress_log.md")
            self.assertTrue(os.path.isfile(archive_path))
            with open(archive_path, encoding="utf-8") as f:
                archived_lines = f.readlines()
            self.assertEqual(len(archived_lines), 300)
            self.assertIn("line 0", archived_lines[0])

    def test_missing_file_is_skipped(self):
        with temp_project():
            result = gid.truncate_one(os.path.join(gid.GID_DIR, "nope.md"), 400, 200,
                                      os.path.join(gid.GID_DIR, "archive"))
            self.assertEqual(result["skipped"], "missing")


# ============================================================ atomic_write

def _tmp_leftovers(d):
    return [f for f in os.listdir(d) if f.startswith(".gid-tmp-")]


class TestAtomicWrite(unittest.TestCase):
    """Regression cover for issue #15: a state-file write that fails must leave the previous
    content intact. The old `open(path, "w")` truncated the destination before writing, so a
    mid-write UnicodeEncodeError emptied task_queue.md — the dispatcher's only task state."""

    def test_lone_surrogate_is_escaped_not_raised(self):
        # UTF-8 CAN encode ☐/☑ and emoji; the only thing it cannot encode is an unpaired
        # surrogate (a split emoji, or a surrogateescape'd Windows path). That is the real
        # trigger — a test using checkbox glyphs would pass without exercising the bug.
        with temp_project({"a.md": "original\n"}) as d:
            path = os.path.join(d, "a.md")
            gid.atomic_write(path, "kept \ud83d line\n")
            out = gid.read(path)
            self.assertEqual(_tmp_leftovers(d), [])
        self.assertIn("kept", out)
        self.assertIn("line", out)
        self.assertNotIn("\ud83d", out)

    def test_write_lines_survives_lone_surrogate(self):
        with temp_project({"q.md": "### T-001\n"}) as d:
            path = os.path.join(d, "q.md")
            gid._write_lines(path, ["### T-001", "- Notes: bad \udce9 byte", ""])
            out = gid.read(path)
        self.assertTrue(out.startswith("### T-001\n"))
        self.assertIn("- Notes:", out)

    def test_checkbox_glyphs_round_trip_unchanged(self):
        with temp_project({"q.md": "old\n"}) as d:
            path = os.path.join(d, "q.md")
            gid._write_lines(path, ["☐ pending", "☑ done"])
            out = gid.read(path)
        self.assertEqual(out, "☐ pending\n☑ done\n")

    def test_destination_untouched_when_rename_fails(self):
        with temp_project({"q.md": "PREVIOUS\n"}) as d:
            path = os.path.join(d, "q.md")
            with mock.patch("os.replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    gid.atomic_write(path, "NEW\n")
            self.assertEqual(gid.read(path), "PREVIOUS\n")
            self.assertEqual(_tmp_leftovers(d), [])

    def test_rename_retries_transient_permission_error(self):
        # Windows: the destination cannot be replaced while another handle is open on it.
        real_replace = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("locked")
            real_replace(src, dst)

        with temp_project({"q.md": "old\n"}) as d:
            path = os.path.join(d, "q.md")
            with mock.patch("os.replace", flaky):
                gid.atomic_write(path, "new\n")
            self.assertEqual(gid.read(path), "new\n")
            self.assertEqual(_tmp_leftovers(d), [])
        self.assertEqual(len(calls), 3)

    def test_temp_file_lands_beside_destination(self):
        # rename is only atomic within one filesystem, and .get-it-done/ may be a junction.
        seen = {}
        real_mkstemp = tempfile.mkstemp

        def spy(**kwargs):
            seen["dir"] = kwargs.get("dir")
            return real_mkstemp(**kwargs)

        with temp_project() as d:
            path = os.path.join(d, gid.GID_DIR, "state.md")
            with mock.patch("tempfile.mkstemp", spy):
                gid.atomic_write(path, "x\n")
        self.assertEqual(os.path.normcase(seen["dir"]),
                         os.path.normcase(os.path.dirname(os.path.abspath(path))))


# =========================================================== dag-check e2e

class TestDagCheckEndToEnd(unittest.TestCase):
    def test_clean_task_queue_ok(self):
        text = "## Tasks\n" + task_block("T-001") + task_block("T-002", deps=["T-001"])
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_dag_check)
        self.assertTrue(out["ok"])
        self.assertEqual(out["violations"], [])

    def test_cycle_flagged(self):
        text = "## Tasks\n" + task_block("T-001", deps=["T-002"]) + task_block("T-002", deps=["T-001"])
        with temp_project({os.path.join(gid.GID_DIR, "task_queue.md"): text}):
            out = capture_json(gid.cmd_dag_check)
        self.assertFalse(out["ok"])
        self.assertTrue(any("cycle" in v for v in out["violations"]))


# =================================================== scripted state writes (Phase 6)

STATE_FIXTURE = """# Team State
```yaml
schema_version: 2
phase: EXECUTING
status: WAITING
batch_id: null
batch_started_at: null
batch_ended_at: null
active_agents: []
goal_set: true
last_updated: null
```

## Phase Definitions
_(spec prose below the YAML block — must be preserved verbatim across rewrites.)_
"""

FULL_TASK_TMPL = """### {id}: {title}
- **Type**: {type}
- **Status**: {status}
- **Milestone**: {milestone}
- **Dependencies**: []
- **Touches**: {touches}
- **Claimed_by**: null
- **Claimed_at**: null
- **Artifact**: null
- **Attempts**: {attempts}
- **Validation Results**: []
- **Created**: 2026-01-01T00:00:00Z
- **Updated**: 2026-01-01T00:00:00Z
"""


def full_task(id, title="t", type="docs", status="pending", touches="[]", attempts=0, milestone="M1"):
    return FULL_TASK_TMPL.format(id=id, title=title, type=type, status=status,
                                 touches=touches, attempts=attempts, milestone=milestone)


def milestone_block(id="M1", title="First", tasks="[T-001]", pause_after=None):
    b = ("### {id}: {title}\n- **Tasks**: {tasks}\n- **Claimed_by**: null\n"
         "- **Claimed_at**: null\n- **ValidatorAttempts**: 0\n").format(
        id=id, title=title, tasks=tasks)
    if pause_after is not None:
        b += "- **PauseAfter**: {p}\n- **PauseReason**: {r}\n".format(
            p="true" if pause_after else "false", r=pause_after if isinstance(pause_after, str) else "null")
    b += "- **Validation Results**: []\n"
    return b


def _fields(text, task_id):
    """Parse one task/milestone back out of a written task_queue.md."""
    tasks, milestones = gid.parse_task_queue(text)
    return tasks.get(task_id) or milestones.get(task_id)


class TestClaimBatch(unittest.TestCase):
    def _project(self, tq):
        return temp_project({
            os.path.join(gid.GID_DIR, "state.md"): STATE_FIXTURE,
            os.path.join(gid.GID_DIR, "task_queue.md"): tq,
        })

    def test_rewrites_state_and_preserves_spec(self):
        tq = "## Tasks\n" + full_task("T-001")
        with self._project(tq):
            out = capture_json(gid.cmd_claim_batch, payload={
                "batch": [{"role": "executor", "task_id": "T-001",
                           "scratch": ".get-it-done/workspace/exec-T-001/"}],
                "git_mode": "fallback", "max_parallel": 5})
            self.assertEqual(out["batch_id"], "B0001")
            st = gid.parse_state(gid.read(os.path.join(gid.GID_DIR, "state.md")))
            self.assertEqual(st["status"], "RUNNING")
            self.assertEqual(st["batch_id"], "B0001")
            self.assertEqual(st["active_agent_count"], 1)
            self.assertIsNotNone(st["batch_started_at"])
            self.assertIsNone(st["batch_ended_at"])
            raw = gid.read(os.path.join(gid.GID_DIR, "state.md"))
            self.assertIn("Phase Definitions", raw, "spec prose below YAML must survive")
            self.assertIn("must be preserved verbatim", raw)
            self.assertTrue(os.path.isdir(".get-it-done/workspace/exec-T-001/"))

    def test_claims_executor_validator_milestone(self):
        tq = ("## Tasks\n" + full_task("T-001", status="pending")
              + full_task("T-002", status="executed")
              + "\n## Milestones\n" + milestone_block("M1", tasks="[T-001, T-002]"))
        with self._project(tq):
            capture_json(gid.cmd_claim_batch, payload={"batch": [
                {"role": "executor", "task_id": "T-001", "scratch": ".get-it-done/workspace/exec-T-001/"},
                {"role": "validator", "mode": "task", "task_id": "T-002"},
                {"role": "validator", "mode": "milestone", "task_id": "M1"},
            ], "git_mode": "fallback"})
            text = gid.read(os.path.join(gid.GID_DIR, "task_queue.md"))
            self.assertEqual(_fields(text, "T-001")["status"], "claimed")
            self.assertEqual(_fields(text, "T-001")["claimed_by"], "exec-T-001")
            self.assertEqual(_fields(text, "T-002")["status"], "validating")
            self.assertEqual(_fields(text, "T-002")["claimed_by"], "val-T-002")
            self.assertEqual(_fields(text, "M1")["claimed_by"], "mval-M1")

    def test_analyst_claim_in_research_requests(self):
        tq = "## Tasks\n" + full_task("T-001")
        rr = ("# Research Requests\n\n### RQ-1\n- **Question**: q?\n"
              "- **Status**: open\n- **Claimed_by**: null\n- **Claimed_at**: null\n")
        with temp_project({
            os.path.join(gid.GID_DIR, "state.md"): STATE_FIXTURE,
            os.path.join(gid.GID_DIR, "task_queue.md"): tq,
            os.path.join(gid.GID_DIR, "research_requests.md"): rr,
        }):
            capture_json(gid.cmd_claim_batch, payload={
                "batch": [{"role": "analyst", "task_id": "RQ-1"}], "git_mode": "fallback"})
            out = capture_json(gid.cmd_rqs)
            self.assertIn("RQ-1", out["open_claimed"])


class TestPersistReturnExecutor(unittest.TestCase):
    def _project(self, tq):
        return temp_project({
            os.path.join(gid.GID_DIR, "state.md"): STATE_FIXTURE,
            os.path.join(gid.GID_DIR, "task_queue.md"): tq,
            os.path.join(gid.GID_DIR, "progress_log.md"): "# Progress Log\n",
        })

    def test_completed_sets_executed_and_increments_attempts(self):
        tq = "## Tasks\n" + full_task("T-001", status="claimed", attempts=0)
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "executor", "task_id": "T-001", "git_mode": "fallback",
                "return": {"status": "completed", "artifact": "a/result.md", "notes": "x"}})
            self.assertEqual(out["status_after"], "executed")
            t = _fields(gid.read(os.path.join(gid.GID_DIR, "task_queue.md")), "T-001")
            self.assertEqual(t["status"], "executed")
            self.assertEqual(t["attempts"], 1)
            self.assertEqual(t["artifact"], "a/result.md")
            self.assertIsNone(t["claimed_by"])

    def test_failed_sets_blocked_and_drops_worktree(self):
        tq = "## Tasks\n" + full_task("T-001", status="claimed", type="code", touches='["src/a.ts"]')
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "executor", "task_id": "T-001", "git_mode": "worktree",
                "worktree_mode": "parallel",
                "return": {"status": "failed", "notes": "cannot"}})
            self.assertEqual(out["status_after"], "blocked")
            self.assertIn("worktree-drop T-001 --keep-branch", out["next_actions"])
            log = gid.read(os.path.join(gid.GID_DIR, "progress_log.md"))
            self.assertIn("[BLOCKER] T-001", log)

    def test_parallel_source_task_emits_commit_wip(self):
        tq = "## Tasks\n" + full_task("T-001", status="claimed", type="code", touches='["src/a.ts"]')
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "executor", "task_id": "T-001", "git_mode": "worktree",
                "worktree_mode": "parallel",
                "return": {"status": "completed", "artifact": ""}})
            self.assertIn("worktree-commit-wip T-001 --attempt 1", out["next_actions"])


class TestPersistReturnValidator(unittest.TestCase):
    def _project(self, tq):
        return temp_project({
            os.path.join(gid.GID_DIR, "state.md"): STATE_FIXTURE,
            os.path.join(gid.GID_DIR, "task_queue.md"): tq,
            os.path.join(gid.GID_DIR, "progress_log.md"): "# Progress Log\n",
            os.path.join(gid.GID_DIR, "validation_log.md"): "# Validation Log\n",
        })

    def test_task_pass_sets_done_and_appends_parseable_vr(self):
        tq = "## Tasks\n" + full_task("T-001", status="validating", attempts=1)
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "validator", "mode": "task", "task_id": "T-001", "git_mode": "fallback",
                "return": {"verdict": "pass", "fail_reasons": [], "escalate_to_blocked": False,
                           "notes": "ok"}})
            self.assertEqual(out["status_after"], "done")
            text = gid.read(os.path.join(gid.GID_DIR, "task_queue.md"))
            t = _fields(text, "T-001")
            self.assertEqual(t["status"], "done")
            self.assertEqual(len(t["validation_results"]), 1)
            self.assertEqual(t["validation_results"][0], {"attempt_no": 1, "verdict": "pass",
                                                          "escalate_to_blocked": False})
            vlog = gid.read(os.path.join(gid.GID_DIR, "validation_log.md"))
            self.assertIn("VAL-0001", vlog)
            self.assertIn("T-001", vlog)

    def test_task_pass_parallel_source_returns_merge(self):
        tq = "## Tasks\n" + full_task("T-001", status="validating", type="code",
                                      touches='["src/a.ts"]', attempts=1)
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "validator", "mode": "task", "task_id": "T-001", "git_mode": "worktree",
                "worktree_mode": "parallel",
                "return": {"verdict": "pass", "escalate_to_blocked": False}})
            self.assertIn("worktree-merge T-001", out["next_actions"])

    def test_task_pass_sequential_source_returns_goal_commit(self):
        tq = "## Tasks\n" + full_task("T-001", status="validating", type="code",
                                      touches='["src/a.ts"]', attempts=1)
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "validator", "mode": "task", "task_id": "T-001", "git_mode": "worktree",
                "worktree_mode": "sequential",
                "return": {"verdict": "pass", "escalate_to_blocked": False}})
            self.assertIn("goal-commit-task T-001", out["next_actions"])

    def test_task_fail_sets_needs_rework(self):
        tq = "## Tasks\n" + full_task("T-001", status="validating", attempts=1)
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "validator", "mode": "task", "task_id": "T-001", "git_mode": "fallback",
                "return": {"verdict": "fail", "fail_reasons": ["criterion C2: x"],
                           "escalate_to_blocked": False}})
            self.assertEqual(out["status_after"], "needs_rework")
            t = _fields(gid.read(os.path.join(gid.GID_DIR, "task_queue.md")), "T-001")
            self.assertEqual(t["status"], "needs_rework")
            self.assertIsNone(t["artifact"])

    def test_task_fail_escalate_sets_blocked(self):
        tq = "## Tasks\n" + full_task("T-001", status="validating", attempts=2)
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "validator", "mode": "task", "task_id": "T-001", "git_mode": "fallback",
                "return": {"verdict": "fail", "escalate_to_blocked": True}})
            self.assertEqual(out["status_after"], "blocked")
            self.assertIn("[BLOCKER] T-001", gid.read(os.path.join(gid.GID_DIR, "progress_log.md")))

    def test_validation_log_dedup_on_reattempt(self):
        """Crash-recovery correctness: two persists of the same (task_id, attempt_no) must
        append exactly ONE validation_log entry."""
        tq = "## Tasks\n" + full_task("T-001", status="validating", attempts=1)
        with self._project(tq):
            payload = {"role": "validator", "mode": "task", "task_id": "T-001", "git_mode": "fallback",
                       "return": {"verdict": "pass", "escalate_to_blocked": False}}
            capture_json(gid.cmd_persist_return, payload=dict(payload))
            out2 = capture_json(gid.cmd_persist_return, payload=dict(payload))
            self.assertFalse(out2["validation_log"]["appended"])
            self.assertEqual(out2["validation_log"]["reason"], "dedup")
            vlog = gid.read(os.path.join(gid.GID_DIR, "validation_log.md"))
            self.assertEqual(vlog.count("| T-001 | attempt=1 |"), 1)

    def test_milestone_pass_returns_consolidate_and_pause(self):
        tq = ("## Tasks\n" + full_task("T-001", status="done") + full_task("T-002", status="done")
              + "\n## Milestones\n" + milestone_block("M1", tasks="[T-001, T-002]", pause_after="review UX"))
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "validator", "mode": "milestone", "task_id": "M1", "git_mode": "worktree",
                "return": {"verdict": "pass", "escalate_to_blocked": False}})
            self.assertEqual(out["status_after"], "validated")
            self.assertIn("consolidate-milestone M1", out["next_actions"])
            self.assertEqual(out["planned_pause"], {"milestone_id": "M1", "reason": "review UX"})
            m = _fields(gid.read(os.path.join(gid.GID_DIR, "task_queue.md")), "M1")
            self.assertEqual(m["validatorattempts"], "1")

    def test_milestone_fail_with_rework_flips_tasks(self):
        tq = ("## Tasks\n" + full_task("T-001", status="done") + full_task("T-002", status="done")
              + "\n## Milestones\n" + milestone_block("M1", tasks="[T-001, T-002]"))
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "validator", "mode": "milestone", "task_id": "M1", "git_mode": "fallback",
                "return": {"verdict": "fail", "escalate_to_blocked": False,
                           "task_ids_to_rework": ["T-002"]}})
            self.assertEqual(out["status_after"], "rework")
            text = gid.read(os.path.join(gid.GID_DIR, "task_queue.md"))
            self.assertEqual(_fields(text, "T-002")["status"], "needs_rework")
            self.assertEqual(_fields(text, "T-001")["status"], "done")

    def test_milestone_structural_fail_requests_awaiting_human(self):
        tq = ("## Tasks\n" + full_task("T-001", status="done") + full_task("T-002", status="done")
              + "\n## Milestones\n" + milestone_block("M1", tasks="[T-001, T-002]"))
        with self._project(tq):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "validator", "mode": "milestone", "task_id": "M1", "git_mode": "fallback",
                "return": {"verdict": "fail", "escalate_to_blocked": False, "task_ids_to_rework": []}})
            self.assertEqual(out["status_after"], "structural_fail")
            self.assertEqual(out["phase_request"], "AWAITING_HUMAN")
            self.assertTrue(out["followups"])
            self.assertIn("[BAD_MILESTONE]", gid.read(os.path.join(gid.GID_DIR, "progress_log.md")))


class TestPersistReturnAnalystPlanner(unittest.TestCase):
    def test_analyst_fulfilled_when_findings_exist(self):
        rr = "# RR\n\n### RQ-1\n- **Status**: open\n- **Claimed_by**: analyst-RQ-1\n- **Claimed_at**: t\n"
        with temp_project({
            os.path.join(gid.GID_DIR, "research_requests.md"): rr,
            os.path.join(gid.GID_DIR, "findings", "RQ-1.md"): "findings\n",
            os.path.join(gid.GID_DIR, "progress_log.md"): "# P\n",
        }):
            out = capture_json(gid.cmd_persist_return, payload={"role": "analyst", "task_id": "RQ-1",
                                                                "return": {"status": "completed"}})
            self.assertEqual(out["status_after"], "fulfilled")
            rout = capture_json(gid.cmd_rqs)
            self.assertEqual(rout["rqs"][0]["status"], "fulfilled")
            self.assertIsNone(rout["rqs"][0]["claimed_by"])

    def test_analyst_missing_findings_is_bad_return(self):
        rr = "# RR\n\n### RQ-1\n- **Status**: open\n- **Claimed_by**: analyst-RQ-1\n- **Claimed_at**: t\n"
        with temp_project({
            os.path.join(gid.GID_DIR, "research_requests.md"): rr,
            os.path.join(gid.GID_DIR, "progress_log.md"): "# P\n",
        }):
            out = capture_json(gid.cmd_persist_return, payload={"role": "analyst", "task_id": "RQ-1",
                                                                "return": {"status": "completed"}})
            self.assertEqual(out["status_after"], "open")
            self.assertTrue(out["followups"])

    def test_planner_executing_requests_gate_followup(self):
        with temp_project({os.path.join(gid.GID_DIR, "progress_log.md"): "# P\n"}):
            out = capture_json(gid.cmd_persist_return, payload={
                "role": "planner", "return": {"next_phase_request": "EXECUTING"}})
            self.assertEqual(out["phase_request"], "EXECUTING")
            self.assertTrue(any("plan-audit-gate" in f for f in out["followups"]))


class TestCloseBatch(unittest.TestCase):
    def test_closes_envelope_and_appends_history(self):
        with temp_project({os.path.join(gid.GID_DIR, "state.md"): STATE_FIXTURE}):
            gid.write_state_yaml({"status": "RUNNING", "batch_id": "B0007",
                                  "batch_started_at": "2026-01-01T00:00:00Z"},
                                 [{"role": "executor", "task_id": "T-001", "started_at": "t"}])
            out = capture_json(gid.cmd_close_batch, payload={
                "phase": "REPORTING",
                "items": [{"role": "executor", "task_id": "T-001",
                           "status_or_verdict": "completed", "artifact": "a/r.md"}],
                "intent": "finalize"})
            self.assertEqual(out["batch_id"], "B0007")
            raw = gid.read(os.path.join(gid.GID_DIR, "state.md"))
            st = gid.parse_state(raw)
            self.assertEqual(st["status"], "WAITING")
            self.assertEqual(st["phase"], "REPORTING")
            self.assertEqual(st["active_agent_count"], 0)
            self.assertIsNotNone(st["batch_ended_at"])
            self.assertIn("## Batch B0007 —", raw)
            self.assertIn("executor T-001 → completed", raw)
            self.assertIn("intent: finalize", raw)
            self.assertIn("Phase Definitions", raw, "spec prose preserved")
            # batch-id derivation now sees the closed batch in history
            self.assertEqual(gid.next_batch_id(), "B0008")


class TestLogAppend(unittest.TestCase):
    def test_append_and_dedup(self):
        import sys as _sys
        with temp_project({os.path.join(gid.GID_DIR, "progress_log.md"): "# P\n"}):
            old = _sys.argv
            try:
                _sys.argv = ["gid.py", "log-append", "--file", "progress_log.md",
                             "--line", "X [CRASH_DETECTED] batch=B1", "--dedup", "[CRASH_DETECTED] batch=B1"]
                out1 = capture_json(gid.cmd_log_append)
                self.assertTrue(out1["appended"])
                out2 = capture_json(gid.cmd_log_append)
                self.assertFalse(out2["appended"])
            finally:
                _sys.argv = old
            log = gid.read(os.path.join(gid.GID_DIR, "progress_log.md"))
            self.assertEqual(log.count("[CRASH_DETECTED] batch=B1"), 1)


class TestResetState(unittest.TestCase):
    STATE_WITH_HISTORY = (STATE_FIXTURE.replace("phase: EXECUTING", "phase: EXECUTING")
                          + "\n## Batch B0001 — a → b\n- executor T-001 → completed\n"
                            "next_phase: EXECUTING\nintent: x\n"
                            "\n## Batch B0002 — c → d\n- validator T-001 → pass\n"
                            "next_phase: EXECUTING\nintent: y\n")

    def _run(self, *argv):
        import sys as _sys
        old = _sys.argv
        try:
            _sys.argv = ["gid.py"] + list(argv)
            return capture_json(gid.cmd_reset_state)
        finally:
            _sys.argv = old

    def test_resets_yaml_preserves_history_by_default(self):
        with temp_project({os.path.join(gid.GID_DIR, "state.md"): self.STATE_WITH_HISTORY}):
            out = self._run("reset-state", "--phase", "PLANNING")
            self.assertEqual(out["phase"], "PLANNING")
            self.assertEqual(out["history_lines_stripped"], 0)
            raw = gid.read(os.path.join(gid.GID_DIR, "state.md"))
            st = gid.parse_state(raw)
            self.assertEqual(st["phase"], "PLANNING")
            self.assertEqual(st["status"], "WAITING")
            self.assertIsNone(st["batch_id"])
            self.assertTrue(st["goal_set"])
            self.assertEqual(raw.count("## Batch B"), 2, "history preserved without --clear-history")

    def test_clear_history_strips_batch_blocks_but_keeps_prose(self):
        with temp_project({os.path.join(gid.GID_DIR, "state.md"): self.STATE_WITH_HISTORY}):
            out = self._run("reset-state", "--phase", "PLANNING", "--clear-history")
            self.assertGreater(out["history_lines_stripped"], 0)
            raw = gid.read(os.path.join(gid.GID_DIR, "state.md"))
            self.assertEqual(raw.count("## Batch B"), 0, "batch blocks removed")
            self.assertIn("Phase Definitions", raw, "template prose above history preserved")
            self.assertIn("schema_version: 2", raw)

    def test_default_phase_is_planning(self):
        with temp_project({os.path.join(gid.GID_DIR, "state.md"): STATE_FIXTURE}):
            out = self._run("reset-state")
            self.assertEqual(out["phase"], "PLANNING")


class TestRollbackClaims(unittest.TestCase):
    def _project(self):
        state = STATE_FIXTURE.replace("status: WAITING", "status: RUNNING").replace(
            "batch_id: null", 'batch_id: "B0007"')
        tq = ("## Tasks\n"
              + FULL_TASK_TMPL.format(id="T-001", title="a", type="docs", status="claimed",
                                      touches="[]", attempts=1, milestone="M1")
                .replace("- **Claimed_by**: null", "- **Claimed_by**: exec-T-001")
              + FULL_TASK_TMPL.format(id="T-002", title="b", type="docs", status="validating",
                                      touches="[]", attempts=1, milestone="M1")
                .replace("- **Claimed_by**: null", "- **Claimed_by**: val-T-002")
                .replace("- **Artifact**: null", "- **Artifact**: a/r.md")
              + FULL_TASK_TMPL.format(id="T-003", title="c", type="docs", status="done",
                                      touches="[]", attempts=1, milestone="M1")
              + "\n## Milestones\n### M1: First\n- **Tasks**: [T-001, T-002, T-003]\n"
                "- **Claimed_by**: mval-M1\n- **Claimed_at**: t\n- **ValidatorAttempts**: 0\n")
        rr = ("# RR\n\n### RQ-1\n- **Status**: open\n- **Claimed_by**: analyst-RQ-1\n- **Claimed_at**: t\n"
              "\n### RQ-2\n- **Status**: fulfilled\n- **Claimed_by**: null\n- **Claimed_at**: null\n")
        return temp_project({
            os.path.join(gid.GID_DIR, "state.md"): state,
            os.path.join(gid.GID_DIR, "task_queue.md"): tq,
            os.path.join(gid.GID_DIR, "research_requests.md"): rr,
        })

    def test_reverts_claims_and_parks_awaiting_human(self):
        with self._project():
            out = capture_json(gid.cmd_rollback_claims)
            self.assertEqual(set(out["rolled_back"]["tasks"]), {"T-001", "T-002"})
            self.assertEqual(out["rolled_back"]["milestones"], ["M1"])
            self.assertEqual(out["rolled_back"]["rqs"], ["RQ-1"])
            text = gid.read(os.path.join(gid.GID_DIR, "task_queue.md"))
            self.assertEqual(_fields(text, "T-001")["status"], "pending")     # claimed → pending
            self.assertEqual(_fields(text, "T-002")["status"], "executed")    # validating → executed
            self.assertEqual(_fields(text, "T-002")["artifact"], "a/r.md")    # persisted fields kept
            self.assertEqual(_fields(text, "T-003")["status"], "done")        # untouched
            self.assertIsNone(_fields(text, "T-001")["claimed_by"])
            self.assertIsNone(_fields(text, "M1")["claimed_by"])
            rout = capture_json(gid.cmd_rqs)
            self.assertNotIn("RQ-1", rout["open_claimed"])                    # claim cleared
            st = gid.parse_state(gid.read(os.path.join(gid.GID_DIR, "state.md")))
            self.assertEqual(st["phase"], "AWAITING_HUMAN")
            self.assertEqual(st["status"], "WAITING")
            self.assertEqual(st["active_agent_count"], 0)
            self.assertIsNone(st["batch_id"])
            self.assertIsNotNone(st["batch_ended_at"])


# ==================================================== git integration tests

GIT_AVAILABLE = shutil.which("git") is not None


def run_gid(args, cwd, env=None, stdin=None):
    p = subprocess.run([sys.executable, str(GID_PY)] + args, cwd=cwd,
                       capture_output=True, text=True, env=env,
                       input=(json.dumps(stdin) if stdin is not None else None))
    try:
        data = json.loads(p.stdout) if p.stdout.strip() else None
    except json.JSONDecodeError:
        data = None
    return p.returncode, data, p.stdout, p.stderr


@unittest.skipUnless(GIT_AVAILABLE, "git not on PATH")
class TestGitIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test")
        with open(os.path.join(self.repo, "README.md"), "w") as f:
            f.write("hello\n")
        self._git("add", "README.md")
        self._git("commit", "-q", "-m", "initial")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, *args, cwd=None):
        subprocess.run(["git"] + list(args), cwd=cwd or self.repo, check=True,
                       capture_output=True, text=True)

    def _write_task_queue(self, goal_wt, extra_milestones=""):
        gid_dir = os.path.join(goal_wt, gid.GID_DIR)
        os.makedirs(gid_dir, exist_ok=True)
        content = (
            "## Tasks\n"
            + task_block("T-001", status="pending", touches=["file.txt"], milestone="M1")
            + task_block("T-002", status="pending", touches=["file.txt"], milestone="M1")
            + "\n## Milestones\n"
              "### M1: First\n- **Tasks**: [T-001, T-002]\n- **Claimed_by**: null\n"
            + extra_milestones
        )
        with open(os.path.join(gid_dir, "task_queue.md"), "w") as f:
            f.write(content)

    def test_goal_worktree_init_creates_sibling_worktree(self):
        rc, data, out, err = run_gid(["goal-worktree-init", "--slug", "testgoal"], cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertTrue(data["ok"], data)
        self.assertTrue(os.path.isdir(data["path"]))
        self.assertEqual(data["branch"], "gid/goal-testgoal")
        self.assertFalse(data["reused"])
        # idempotent re-assert
        rc2, data2, _, err2 = run_gid(["goal-worktree-init", "--slug", "testgoal"], cwd=self.repo)
        self.assertEqual(rc2, 0, err2)
        self.assertTrue(data2["reused"])

    def test_worktree_add_commit_and_merge(self):
        _, ginit, _, err = run_gid(["goal-worktree-init", "--slug", "testgoal"], cwd=self.repo)
        self.assertTrue(ginit["ok"], err)
        goal_wt = ginit["path"]
        self._write_task_queue(goal_wt)

        rc, wa, _, err = run_gid(["worktree-add", "T-001", "--base", goal_wt], cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertTrue(wa["ok"], wa)
        task_wt = wa["path"]
        self.assertTrue(os.path.isdir(task_wt))

        with open(os.path.join(task_wt, "file.txt"), "w") as f:
            f.write("edited by T-001\n")
        rc, wc, _, err = run_gid(["worktree-commit-wip", "T-001", "--attempt", "1", "--base", goal_wt],
                                 cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertTrue(wc["ok"], wc)
        self.assertIn("wip_sha", wc)

        rc, wm, _, err = run_gid(["worktree-merge", "T-001", "--base", goal_wt], cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertTrue(wm["ok"], wm)
        self.assertIn("merged_sha", wm)
        self.assertFalse(os.path.isdir(task_wt), "task worktree should be removed after merge")

        with open(os.path.join(goal_wt, "file.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "edited by T-001\n")

        # idempotent re-merge of an already-gone branch is a clean no-op
        rc2, wm2, _, err2 = run_gid(["worktree-merge", "T-001", "--base", goal_wt], cwd=self.repo)
        self.assertEqual(rc2, 0, err2)
        self.assertEqual(wm2.get("skipped"), "already_merged")

    def test_worktree_merge_conflict_reports_conflict_files(self):
        _, ginit, _, err = run_gid(["goal-worktree-init", "--slug", "testgoal"], cwd=self.repo)
        self.assertTrue(ginit["ok"], err)
        goal_wt = ginit["path"]
        self._write_task_queue(goal_wt)

        # Both T-001 and T-002 branch from the same base and edit the same line differently.
        _, wa1, _, err = run_gid(["worktree-add", "T-001", "--base", goal_wt], cwd=self.repo)
        self.assertTrue(wa1["ok"], err)
        _, wa2, _, err = run_gid(["worktree-add", "T-002", "--base", goal_wt], cwd=self.repo)
        self.assertTrue(wa2["ok"], err)

        with open(os.path.join(wa1["path"], "file.txt"), "w") as f:
            f.write("version A\n")
        run_gid(["worktree-commit-wip", "T-001", "--attempt", "1", "--base", goal_wt], cwd=self.repo)

        with open(os.path.join(wa2["path"], "file.txt"), "w") as f:
            f.write("version B\n")
        run_gid(["worktree-commit-wip", "T-002", "--attempt", "1", "--base", goal_wt], cwd=self.repo)

        # T-001 merges cleanly first.
        rc, wm1, _, err = run_gid(["worktree-merge", "T-001", "--base", goal_wt], cwd=self.repo)
        self.assertTrue(wm1["ok"], err)

        # T-002 now conflicts against the goal branch's new content.
        rc, wm2, _, err = run_gid(["worktree-merge", "T-002", "--base", goal_wt], cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertFalse(wm2["ok"])
        self.assertEqual(wm2["reason"], "conflict")
        self.assertIn("file.txt", wm2["files"])

        # The goal worktree must be left clean (no lingering merge state) for the next attempt.
        rc_status, out_status, _ = gid.run_git(["-C", goal_wt, "status", "--porcelain"])
        self.assertEqual(rc_status, 0)
        self.assertEqual(out_status.strip(), "")

    def test_consolidate_milestone_and_goal_reset(self):
        _, ginit, _, err = run_gid(["goal-worktree-init", "--slug", "testgoal"], cwd=self.repo)
        self.assertTrue(ginit["ok"], err)
        goal_wt = ginit["path"]
        self._write_task_queue(goal_wt)

        # Sequential path: goal-commit-task commits directly in the goal worktree.
        with open(os.path.join(goal_wt, "file.txt"), "w") as f:
            f.write("T-001 change\n")
        rc, gc1, _, err = run_gid(["goal-commit-task", "T-001", "--base", goal_wt], cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertTrue(gc1["ok"], gc1)

        with open(os.path.join(goal_wt, "file2.txt"), "w") as f:
            f.write("T-002 change\n")
        rc, gc2, _, err = run_gid(["goal-commit-task", "T-002", "--base", goal_wt], cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertTrue(gc2["ok"], gc2)

        rc, cm, out, err = run_gid(["consolidate-milestone", "M1", "--base", goal_wt], cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertTrue(cm["ok"], cm)
        self.assertIn("commit_sha", cm)

        # goal-reset must not touch the goal worktree itself.
        rc, gr, _, err = run_gid(["goal-reset", "--base", goal_wt], cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertTrue(gr["ok"], gr)
        self.assertTrue(os.path.isdir(goal_wt), "goal-reset must never remove the goal worktree")

    def test_worktree_gc_never_reaps_goal_worktree(self):
        _, ginit, _, err = run_gid(["goal-worktree-init", "--slug", "testgoal"], cwd=self.repo)
        self.assertTrue(ginit["ok"], err)
        goal_wt = ginit["path"]
        self._write_task_queue(goal_wt)

        rc, gc, _, err = run_gid(["worktree-gc", "--base", goal_wt], cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertTrue(os.path.isdir(goal_wt))

    def test_git_preflight_reports_worktree_support(self):
        rc, data, _, err = run_gid(["git-preflight"], cwd=self.repo)
        self.assertEqual(rc, 0, err)
        self.assertTrue(data["is_git"])
        self.assertTrue(data["worktree_supported"])
        self.assertFalse(data["dirty"])

    def test_claim_batch_parallel_then_persist_merge_roundtrip(self):
        """Full scripted round-trip in a real repo: claim-batch assigns two parallel task
        worktrees for two source executors, then persist-return's next_actions (worktree-merge)
        actually merge each task's edit onto the goal branch."""
        _, ginit, _, err = run_gid(["goal-worktree-init", "--slug", "testgoal"], cwd=self.repo)
        self.assertTrue(ginit["ok"], err)
        goal_wt = ginit["path"]
        gid_dir = os.path.join(goal_wt, gid.GID_DIR)
        os.makedirs(gid_dir, exist_ok=True)
        with open(os.path.join(gid_dir, "state.md"), "w") as f:
            f.write(STATE_FIXTURE)
        for fn in ("progress_log.md", "validation_log.md"):
            with open(os.path.join(gid_dir, fn), "w") as f:
                f.write("# log\n")
        tq = ("## Tasks\n"
              + full_task("T-001", type="code", status="pending", touches='["a.txt"]', milestone="M1")
              + full_task("T-002", type="code", status="pending", touches='["b.txt"]', milestone="M1")
              + "\n## Milestones\n" + milestone_block("M1", tasks="[T-001, T-002]"))
        with open(os.path.join(gid_dir, "task_queue.md"), "w") as f:
            f.write(tq)

        # claim-batch: two source executors → parallel task worktrees.
        rc, cb, _, err = run_gid(["claim-batch", "--base", goal_wt], cwd=self.repo, stdin={
            "batch": [
                {"role": "executor", "task_id": "T-001", "scratch": ".get-it-done/workspace/exec-T-001/"},
                {"role": "executor", "task_id": "T-002", "scratch": ".get-it-done/workspace/exec-T-002/"},
            ], "git_mode": "worktree", "max_parallel": 5})
        self.assertEqual(rc, 0, err)
        self.assertTrue(cb["parallel"], cb)
        self.assertIn("T-001", cb["worktrees"])
        self.assertIn("T-002", cb["worktrees"])

        # each executor edits its own file in its own task worktree, then persist-return.
        for tid, fn in (("T-001", "a.txt"), ("T-002", "b.txt")):
            wt = cb["worktrees"][tid]
            self.assertTrue(os.path.isdir(wt))
            with open(os.path.join(wt, fn), "w") as f:
                f.write("edited by %s\n" % tid)
            rc, pe, _, err = run_gid(["persist-return", "--base", goal_wt], cwd=self.repo, stdin={
                "role": "executor", "task_id": tid, "git_mode": "worktree", "worktree_mode": "parallel",
                "return": {"status": "completed", "artifact": ""}})
            self.assertEqual(rc, 0, err)
            self.assertIn("worktree-commit-wip %s --attempt 1" % tid, pe["next_actions"])
            for action in pe["next_actions"]:
                rc, _, _, err = run_gid(action.split() + ["--base", goal_wt], cwd=self.repo)
                self.assertEqual(rc, 0, err)

        # validator passes each task → persist-return emits worktree-merge; run it.
        for tid, fn in (("T-001", "a.txt"), ("T-002", "b.txt")):
            rc, pv, _, err = run_gid(["persist-return", "--base", goal_wt], cwd=self.repo, stdin={
                "role": "validator", "mode": "task", "task_id": tid, "git_mode": "worktree",
                "worktree_mode": "parallel",
                "return": {"verdict": "pass", "escalate_to_blocked": False}})
            self.assertEqual(rc, 0, err)
            self.assertIn("worktree-merge %s" % tid, pv["next_actions"])
            rc, wm, _, err = run_gid(["worktree-merge", tid, "--base", goal_wt], cwd=self.repo)
            self.assertEqual(rc, 0, err)
            self.assertTrue(wm["ok"], wm)

        # both edits are now on the goal branch's working tree.
        for fn in ("a.txt", "b.txt"):
            self.assertTrue(os.path.isfile(os.path.join(goal_wt, fn)), "%s merged onto goal" % fn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
