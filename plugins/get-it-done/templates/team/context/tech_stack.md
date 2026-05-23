# Tech Stack & Conventions

_Project-specific technology choices and coding conventions._
_Read by: Analyst, Executor, Validator._
_Updated by: Reflector when a tech-stack convention surfaces that future cycles should know._

## Active Knowledge

_(empty — populated as conventions become explicit)_

## Format

```
### TS-XXX | Category: language | framework | library | tooling | style | testing
**Choice**: What is used (specific version or version range if relevant).
**Preferred**: Yes / Yes (with caveats) / No, but legacy code uses it
**Notes**: Anti-patterns to avoid, preferred alternatives, version pinning rationale.
```

## What belongs here vs not

✅ **Belongs**: "TypeScript strict mode is required", "use React Query for server state, never bare useEffect+fetch", "tests live next to source as `*.test.ts`, not in a separate `__tests__/` dir", "Tailwind for styling, no styled-components".

❌ **Does NOT belong**:
- Why a choice was made → cross-link to `decisions.md`
- Cross-project code style preferences → `${CLAUDE_PLUGIN_DATA}/team_learnings/agent_rules/executor.md`
- Domain-level rules → `domain_knowledge.md`
