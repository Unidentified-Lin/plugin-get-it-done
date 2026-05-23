# Cross-Project Patterns

_The unified store for cross-project agent-team learnings. Reflector writes here; all worker agents read at run-start._
_Entries have two lifecycle states:_
- **`provisional`** — observed once or twice; useful but not yet trusted as universal. New learnings start here.
- **`promoted`** — observed 3+ times across different cycles and projects; treated as durable behavioral guidance.

_Reflector flips the status from `provisional` → `promoted` once a learning has supporting evidence from 3+ distinct cycles, and records the source learning IDs in `Observed in`._
_When the active count of provisional entries exceeds 20, Reflector prunes the lowest-impact ones._

## Promoted Patterns

### P-001 | Scope: all | Status: promoted
**Pattern**: Path-and-line-number citations (e.g., `executor.md:18`) are the floor for evidence quality, not the ceiling. Every claim in a research/audit/inventory deliverable must include both.
**Action**: Treat line-level evidence as a hard pass criterion at 4/5; bare file-name citations cost a full point. Planner encodes this in metrics; Executor produces it; Analyst mirrors it; Validator spot-checks.
**Observed in**: (initial seed — promoted at plugin v0.1)

### P-002 | Scope: executor + analyst | Status: promoted
**Pattern**: Cross-file triangulation — a finding that requires reading 3+ files to discover — is the 5/5-defining differentiator on audit/analysis tasks. Single-file observations are baseline.
**Action**: When producing analysis artifacts, actively look for inter-file contradictions (field written by A, ignored by B, absent from C's schema). Tag triangulated findings explicitly.
**Observed in**: (initial seed — promoted at plugin v0.1)

## Provisional Patterns

_(none yet — new observations land here)_

## Format

```
### P-XXX | Scope: [all | planner | analyst | executor | validator] | Status: provisional | promoted
**Pattern**: Clear statement of the pattern.
**Action**: What agents should do differently based on this pattern.
**Observed in**: <cycle/project refs — fill in when promoting>
```
