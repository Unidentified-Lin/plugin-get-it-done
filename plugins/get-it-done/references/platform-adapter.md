# Platform Adapter — Cross-Platform Reference

> **For**: All agents in the `get-it-done` plugin
> **Load when**: You need to perform platform-specific operations
> **Covers**: Harness detection, sub-agent spawning, user interaction, path resolution, OS commands

---

## 1. Detect Your Runtime Harness

At startup, determine which harness you are running in:

**Claude Code** — the environment variable `${CLAUDE_PLUGIN_ROOT}` is accessible. You can verify with:
```bash
echo "${CLAUDE_PLUGIN_ROOT}"
```
If this prints a non-empty path, you are in Claude Code.

**GitHub Copilot** — `${CLAUDE_PLUGIN_ROOT}` is not set. Locate the plugin root via the OS-appropriate command below.

---

## 2. Locate Plugin Root

### Claude Code
```bash
echo "${CLAUDE_PLUGIN_ROOT}"
# Returns: ~/.claude/plugins/cache/get-it-done@<version>/
```

### GitHub Copilot — macOS / Linux
```bash
# Most recently modified wins — multiple cached plugin versions may coexist
ls -td $(find "$HOME/.copilot" -type d -name "get-it-done" 2>/dev/null) 2>/dev/null | head -1
```

### GitHub Copilot — Windows (PowerShell)
```powershell
# Most recently modified wins — multiple cached plugin versions may coexist
Get-ChildItem -Path "$HOME\.copilot" -Recurse -Directory -Filter "get-it-done" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
```

---

## 3. Plugin Data Directory (Cross-Project Learnings)

The A-side learnings directory is where cross-project agent rules, patterns, and errors are stored.

### Claude Code
```
${CLAUDE_PLUGIN_DATA}/team_learnings/
# Resolves to: ~/.claude/plugins/data/get-it-done-<scope>/team_learnings/
```

### GitHub Copilot — macOS / Linux
```
~/.copilot/data/get-it-done/team_learnings/
```

### GitHub Copilot — Windows
```
$HOME\.copilot\data\get-it-done\team_learnings\
```

---

## 4. Spawn Sub-Agents — must run as **isolated background subagents**, not inline

The dispatcher relay depends on each sub-agent running in its **own context** and returning only its `---agent-return---` block to the foreground agent, which then decides the next step. A sub-agent that runs **inline** in the dispatcher's context (sharing its window, serializing, polluting state) breaks flow control. Get this right per platform.

### Claude Code
Use the `Agent` tool — it always spawns an isolated sub-agent:
```
Agent(
  subagent_type: "get-it-done:<agent-name>",
  prompt: "<full prompt with absolute paths>",
  description: "<short description>"
)
```
Multiple `Agent` calls in ONE assistant message run in parallel and return together.

### GitHub Copilot CLI
Copilot CLI delegates to a **custom subagent** (its own context; result returns to the parent) — but ONLY when the agent is **discoverable as a Copilot custom agent** AND you **delegate to it by name**. If either is missing, Copilot runs the work **inline** (the bug to avoid).

**(a) Make the agents discoverable (one-time, at bootstrap).** Copilot custom agents live in `~/.copilot/agents/` (user) or `.github/agents/` (project) as `*.agent.md`. The plugin ships its agents under `<plugin-root>/agents/`; mirror them into a Copilot agents dir with the `.agent.md` suffix:
```bash
# macOS / Linux — run once per machine (idempotent)
mkdir -p "$HOME/.copilot/agents"
for f in "<plugin-root>"/agents/*.md; do
  base="$(basename "$f" .md)"; base="${base%.agent}"
  ln -sf "$f" "$HOME/.copilot/agents/get-it-done-$base.agent.md"
done
```
```powershell
# Windows
New-Item -ItemType Directory -Force "$HOME\.copilot\agents" | Out-Null
Get-ChildItem "<plugin-root>\agents\*.md" | ForEach-Object {
  $b = $_.BaseName -replace '\.agent$',''
  Copy-Item $_.FullName "$HOME\.copilot\agents\get-it-done-$b.agent.md" -Force
}
```
Verify with `/agent` (the get-it-done agents should be listed).

**(b) Delegate by name (every spawn).** Copilot's delegation is model-driven — request it explicitly so a subagent is spawned rather than the work being done inline. In the spawn message, name the custom agent and instruct delegation, e.g.:
> "Delegate this to the `get-it-done-executor` subagent (it runs in its own context). Pass it the inputs below and return only its final `---agent-return---` block. \<full prompt with absolute paths\>"

The subagent runs isolated; its final response (the `---agent-return---` block) returns to you (the dispatcher) for flow control.

**(c) Parallelism caveat.** Claude Code fans out N `Agent` calls in one message; Copilot's per-spawn delegation may not background N simultaneously. If your Copilot version does not run delegations concurrently, process the batch with fewer concurrent delegations (down to one-at-a-time) — correctness and flow control are unaffected, only wall-clock. `/fleet` is Copilot's explicit parallel-subagent mode if available.

> **Verify against your Copilot CLI version**: the exact delegation phrasing/tooling evolves. The invariant to preserve: each get-it-done agent runs as an **isolated subagent** and returns its `---agent-return---` to the foreground dispatcher. If you see a sub-agent's work appearing inline in the dispatcher's own output, delegation is not happening — re-check (a) discoverability and (b) explicit by-name delegation.

Always pass all reference file **absolute paths** in the agent prompt — agents start with a fresh context and cannot resolve relative paths.

---

## 5. Ask User Questions

### Claude Code
Use the `AskUserQuestion` tool with structured options:
```
AskUserQuestion({
  questions: [{
    question: "...",
    header: "...",
    options: [
      { label: "...", description: "..." },
      ...
    ]
  }]
})
```

### GitHub Copilot
Use `ask_user` with a `choices` array:
```
ask_user("Question text?", choices=["Option A", "Option B", "Option C"])
```

When choices are not enumerable, ask directly in your response and wait for the user to reply.

---

## 6. Open a File in Browser

After creating a planning document, optionally open it in the browser for the user's convenience.

### macOS
```bash
open "file://{absolute-path}"
# Or for a specific browser:
open -a "Google Chrome" "file://{absolute-path}"
```

### Windows (PowerShell)
```powershell
Start-Process "chrome.exe" -ArgumentList "file:///{absolute-path-forward-slashes}"
# Convert backslashes to forward slashes in the path first.
# Example: C:/Users/user/project/docs/plans/my-plan.md
```

### Linux
```bash
xdg-open "file://{absolute-path}"
```

**Detect OS via Bash** (macOS/Linux only):
```bash
uname -s   # Returns "Darwin" (macOS) or "Linux"
```

**Detect OS via PowerShell** (cross-platform check):
```powershell
[System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)
# Returns True on Windows
```

---

## 7. Bootstrap (Copy Template Files)

Bootstrap copies template files to writable destinations, skipping files that already exist.

### macOS / Linux (Claude Code and Copilot)
```bash
# A — cross-project learnings
rsync -a --ignore-existing "${PLUGIN_ROOT}/templates/team_learnings/" "${PLUGIN_DATA}/team_learnings/"

# B — per-project state
rsync -a --ignore-existing "${PLUGIN_ROOT}/templates/.get-it-done/" .get-it-done/
```

### Windows (PowerShell)
```powershell
# A — cross-project learnings
robocopy "${PLUGIN_ROOT}\templates\team_learnings" "${PLUGIN_DATA}\team_learnings" /E /XC /XN /XO /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }

# B — per-project state
robocopy "${PLUGIN_ROOT}\templates\.get-it-done" ".get-it-done" /E /XC /XN /XO /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }
$global:LASTEXITCODE = 0
```

`robocopy` flags: `/E` = include subdirs, `/XC /XN /XO` = skip if dest is same/newer/older (i.e., skip existing), `/NFL /NDL /NJH /NJS` = suppress output.

⚠️ **robocopy exit-code gotcha**: robocopy returns **1–7 on success** (1 = files copied, 2 = extra files, etc.) and ≥8 only on real failure. `| Out-Null` does not reset `$LASTEXITCODE`, so a harness that treats non-zero as failure will mis-read a successful copy. Always follow robocopy with the `-ge 8` check + `$global:LASTEXITCODE = 0` normalization shown above.

---

## 8. Asking the User — sub-agent limitation

`AskUserQuestion` / `ask_user` only reach the user from the **main conversation**. Sub-agents spawned via `Agent` / `task` are non-interactive — their questions are never surfaced; the spawn returns only their final output. Therefore:

- Any step that needs user confirmation (e.g. the /blueprint Requirements Confirmation / Implementation Direction / Task Breakdown loops) must run in the main conversation.
- Sub-agents that hit a decision they cannot make must **return** with the question in their final response and let the orchestrator ask the user.

---

## 9. Invoke Another Skill

### Claude Code
Use the `Skill` tool:
```
Skill(skill: "continue")            # or "get-it-done:continue" on name collision
```

### GitHub Copilot
There is no Skill tool. Read the target skill's `SKILL.md` from the plugin root and execute its instructions inline in the current session:
```
{plugin-root}/skills/<name>/SKILL.md
```

---

## 9.5. Git worktree operations + multi-goal (GID_BASE)

Each goal runs in its **own git worktree** under `<repo>.gid-goals/<slug>/` (grouped sibling of the repo) on branch `gid/goal-<slug>` from the repo's HEAD. That worktree **contains its own real `.get-it-done/`** (hidden from git via the worktree's `info/exclude`). All the goal's source accumulates on `gid/goal-<slug>`; the user's own checkout/branch stays clean. **`GID_BASE` = the active goal's worktree path** — the dispatcher runs at the repo root but targets a goal by passing `--base "$GID_BASE"` to `gid.py` (which `os.chdir`s there). Multiple windows can each set a different `GID_BASE` and drive **concurrent goals** on one repo with no cross-session lock (separate worktrees + per-worktree git indexes; only the shared object/ref store, which is git-safe). `gid.py goals` lists active goals (from `git worktree list`); `gid.py goal-reset` clears one goal's task worktrees without touching others. **Back-compat:** `GID_BASE` unset ⇒ base = repo root ⇒ legacy single-goal `.get-it-done/` at the repo root (a `_goal` worktree under `.get-it-done/worktrees/`).

Parallelism is plan-driven: independent tasks (deps satisfied, non-overlapping `Touches`) run concurrently in **grouped-sibling task worktrees** `<repo>.gid-goals/<slug>-<T>` branched from the goal branch (up to `max_parallel` default 5 / `max_worktrees`); dependent or same-file tasks serialize automatically; a lone eligible task runs directly in the goal worktree. All git work is done by `gid.py` — the only cross-platform difference is the Python invocation (`python3` / `python` on Windows).

A **task** worktree's `.get-it-done/` is a **symlink** to the **goal** worktree's `.get-it-done/` (one shared copy per goal). Dependency dirs (`node_modules`, …) are linked so build/test run without reinstalling:
- **macOS / Linux**: `os.symlink`.
- **Windows**: directory junction `mklink /J` — works on local NTFS **without admin or Developer Mode**. `gid.py` picks the right one automatically. The goal worktree's own `.get-it-done/` is a real dir (no symlink), hidden via `info/exclude`.

Non-git projects (or when `git-preflight` reports git unusable) fall back to direct edits — no worktrees, no rollback — plus a Step-5 scheduling guard that keeps build-running validators out of the same batch as source executors.

## 10. Quick Decision Table

| Operation | Claude Code | Copilot (macOS/Linux) | Copilot (Windows) |
|-----------|------------|----------------------|-------------------|
| Plugin root | `${CLAUDE_PLUGIN_ROOT}` | `ls -td $(find $HOME/.copilot -name get-it-done) \| head -1` | `Get-ChildItem ... \| Sort LastWriteTime -Desc` |
| Data dir | `${CLAUDE_PLUGIN_DATA}/team_learnings/` | `~/.copilot/data/get-it-done/team_learnings/` | `$HOME\.copilot\data\get-it-done\team_learnings\` |
| Spawn agent (isolated subagent) | `Agent` tool | delegate to `get-it-done-<role>` custom agent by name (§4) | delegate to `get-it-done-<role>` custom agent by name (§4) |
| Ask user (main conversation only) | `AskUserQuestion` | `ask_user` | `ask_user` |
| Invoke skill | `Skill` tool | read SKILL.md, run inline | read SKILL.md, run inline |
| Open in browser | `open "file://..."` | `open "file://..."` | `Start-Process chrome ...` |
| Bootstrap | `rsync -a --ignore-existing` | `rsync -a --ignore-existing` | `robocopy /E /XC /XN /XO` + exit-code normalize |
