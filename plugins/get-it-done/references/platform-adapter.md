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
find "$HOME/.copilot" -type d -name "get-it-done" 2>/dev/null | head -1
```

### GitHub Copilot — Windows (PowerShell)
```powershell
Get-ChildItem -Path "$HOME\.copilot" -Recurse -Directory -Filter "get-it-done" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
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

## 4. Spawn Sub-Agents

### Claude Code
Use the `Agent` tool:
```
Agent(
  subagent_type: "get-it-done:<agent-name>",
  prompt: "<full prompt with absolute paths>",
  description: "<short description>"
)
```

### GitHub Copilot
Use the `task` tool:
```
task(
  agent_type: "get-it-done:<agent-name>",
  prompt: "<full prompt with absolute paths>"
)
```

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

# B — per-project state
robocopy "${PLUGIN_ROOT}\templates\.get-it-done" ".get-it-done" /E /XC /XN /XO /NFL /NDL /NJH /NJS | Out-Null
```

`robocopy` flags: `/E` = include subdirs, `/XC /XN /XO` = skip if dest is same/newer/older (i.e., skip existing), `/NFL /NDL /NJH /NJS` = suppress output.

---

## 8. Quick Decision Table

| Operation | Claude Code | Copilot (macOS/Linux) | Copilot (Windows) |
|-----------|------------|----------------------|-------------------|
| Plugin root | `${CLAUDE_PLUGIN_ROOT}` | `find $HOME/.copilot -name get-it-done` | `Get-ChildItem $HOME\.copilot` |
| Data dir | `${CLAUDE_PLUGIN_DATA}/team_learnings/` | `~/.copilot/data/get-it-done/team_learnings/` | `$HOME\.copilot\data\get-it-done\team_learnings\` |
| Spawn agent | `Agent` tool | `task` tool | `task` tool |
| Ask user | `AskUserQuestion` | `ask_user` | `ask_user` |
| Open in browser | `open "file://..."` | `open "file://..."` | `Start-Process chrome ...` |
| Bootstrap | `rsync -a --ignore-existing` | `rsync -a --ignore-existing` | `robocopy /E /XC /XN /XO` |
