# Codebase Map

_Project-specific landmarks: where things live, where the landmines are, what's surprising._
_Read by: Executor (mainly), Validator (for spot-checks)._
_Updated by: Reflector when Executor or Validator hits a non-obvious path-finding cost that shouldn't be re-paid next cycle._

## Active Knowledge

_(empty — populated as the codebase's non-obvious structure becomes visible)_

## Format

```
### CM-XXX | Type: landmark | landmine | convention | dead-code
**Where**: File path or path glob.
**What**: One sentence — what's there, what's surprising.
**Don't**: Specific anti-action ("don't import from `legacy/`", "don't edit generated code in `dist/`", etc.) — only if there's a clear "don't".
```

## What belongs here vs not

✅ **Belongs**: "auth logic is split across `auth/`, `middleware/`, AND `lib/session.ts` — touching one without the others breaks login", "`utils/legacy.ts` is dead code waiting for cleanup", "the i18n keys live in `locales/` but get inlined at build time — edits need a rebuild".

❌ **Does NOT belong**:
- Architectural choices → `decisions.md`
- Tech-stack-wide patterns → `tech_stack.md`
- General code-quality rules → `${CLAUDE_PLUGIN_DATA}/team_learnings/agent_rules/executor.md`
