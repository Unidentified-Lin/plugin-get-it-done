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


# ==================================================== git integration tests

GIT_AVAILABLE = shutil.which("git") is not None


def run_gid(args, cwd, env=None):
    p = subprocess.run([sys.executable, str(GID_PY)] + args, cwd=cwd,
                       capture_output=True, text=True, env=env)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
