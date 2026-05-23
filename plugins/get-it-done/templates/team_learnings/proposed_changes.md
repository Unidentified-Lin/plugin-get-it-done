# Proposed Changes to Plugin Source

_Reflector appends entries here when it judges that the get-it-done plugin's own files (`agents/*.md` or `skills/**/*.md` in the plugin source tree) need an instruction-text fix._

_Reflector CANNOT edit the plugin's installed files (they live in the read-only plugin cache `~/.claude/plugins/cache/...` and any change is wiped on the next plugin update). So this file is the channel for proposed diffs that a human (or the plugin maintainer) must apply to the plugin source repo and ship as a new plugin version._

_Behavioral nudges that don't require editing the agent prompt itself go into `${CLAUDE_PLUGIN_DATA}/team_learnings/agent_rules/<name>.md` instead — those are read live every cycle and persist across plugin updates because they live in `${CLAUDE_PLUGIN_DATA}`, not in the read-only plugin cache._

## Format

```markdown
### <ISO timestamp> | <file in plugin source>
**Change**: One-line summary of the proposed edit.
**Why**: VAL-XXX or recurring failure pattern that motivates it.
**Proposed diff**:
- old line
+ new line
**Status**: awaiting human application to plugin source
```

## Entries

_(none yet)_
