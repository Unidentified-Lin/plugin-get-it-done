#!/usr/bin/env python3
"""Guard tests for plugins/get-it-done/agents/*.agent.md frontmatter.

The plugin ships ONE set of agent definitions for two harnesses (Claude Code and GitHub
Copilot CLI), which only works while the frontmatter stays inside what both accept. These
tests exist because the tempting "fix" — declaring a tools allowlist so each agent gets
least privilege — is exactly what breaks cross-platform loading, and nothing else in the
repo would catch it being added back.

Stdlib-only (unittest), matching the rest of the suite.

Run:
  python3 -m unittest discover -s plugins/get-it-done/skills/continue/scripts/tests -p "test_*.py"
"""
import re
import unittest
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parents[4] / "agents"

# Fields both harnesses understand, or that one ignores harmlessly. Anything outside this set
# is a deliberate decision that belongs in references/platform-adapter.md first.
KNOWN_FIELDS = {"name", "description", "model", "maxTurns", "background"}


def agent_files():
    return sorted(AGENTS_DIR.glob("*.md"))


def frontmatter(path):
    """Top-level `key:` names in the YAML frontmatter block, in order. Deliberately naive —
    it only needs to see column-0 keys, and treating nested/continuation lines as absent is
    the safe direction for a guard test."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    return [k.group(1) for k in
            (re.match(r"^([A-Za-z][A-Za-z0-9_-]*):", ln) for ln in m.group(1).split("\n")) if k]


class TestAgentFrontmatter(unittest.TestCase):
    def test_agents_dir_is_populated(self):
        # Guards against the glob silently matching nothing after a directory move, which
        # would make every other test in this file vacuously pass.
        self.assertGreaterEqual(len(agent_files()), 9, f"no agent files found under {AGENTS_DIR}")

    def test_every_agent_uses_the_agent_md_suffix(self):
        bad = [p.name for p in agent_files() if not p.name.endswith(".agent.md")]
        self.assertEqual(bad, [], "agent files must end in .agent.md — VS Code custom agents "
                                  "require the suffix and Copilot dedupes on the name without it")

    def test_no_agent_declares_a_tools_allowlist(self):
        # Claude Code wants Read/Write/Edit/Bash/Glob/Grep; Copilot CLI's real tool names are
        # view/apply_patch/rg/web_fetch/task/powershell. There is no working intersection, and
        # Copilot's documented alias table is not implemented in the CLI — it rejects even its
        # own primary aliases (github/copilot-cli#1722, #738). Omitting the field is well-defined
        # on both sides: Claude Code inherits every subagent tool, Copilot inherits the session's.
        # Per-agent limits live in each agent's prose instead. See references/platform-adapter.md.
        offenders = [p.name for p in agent_files() if "tools" in (frontmatter(p) or [])]
        self.assertEqual(offenders, [], "agents must NOT declare `tools:` — see "
                                        "references/platform-adapter.md, 'Agent frontmatter'")

    def test_required_fields_present(self):
        for path in agent_files():
            with self.subTest(agent=path.name):
                keys = frontmatter(path)
                self.assertIsNotNone(keys, "missing a YAML frontmatter block")
                self.assertIn("name", keys)
                self.assertIn("description", keys)

    def test_no_unvetted_frontmatter_fields(self):
        for path in agent_files():
            with self.subTest(agent=path.name):
                unknown = sorted(set(frontmatter(path) or []) - KNOWN_FIELDS)
                self.assertEqual(unknown, [], "unvetted frontmatter field(s); confirm both "
                                              "harnesses tolerate them and document in "
                                              "references/platform-adapter.md before adding")

    def test_name_matches_filename(self):
        # Claude Code identifies an agent by its `name:`, Copilot by its filename. They must
        # agree or the same agent answers to two different identifiers across harnesses.
        for path in agent_files():
            with self.subTest(agent=path.name):
                text = path.read_text(encoding="utf-8")
                declared = re.search(r"^name:\s*(\S+)\s*$", text, re.M)
                self.assertIsNotNone(declared, "no `name:` field")
                self.assertEqual(declared.group(1), path.name[: -len(".agent.md")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
