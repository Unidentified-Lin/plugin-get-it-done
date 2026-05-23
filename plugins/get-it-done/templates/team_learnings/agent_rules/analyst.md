# Analyst Dynamic Rules

_Learned behavioral rules specific to the Analyst agent._
_Updated by Reflector. Read by Analyst at the start of every run._

## Rules

### AR-001 | Priority: medium
**Rule**: When delivering findings, cite file paths with line numbers where applicable, and prefer cross-file observations (a claim requiring 2+ sources) over single-source claims.
**Reason**: Line-level evidence and cross-file triangulation are the dominant quality signals; Analyst output feeds Planner, so the same evidence bar applies upstream.

### AR-002 | Priority: high
**Rule**: You are spawned with exactly one assigned `RQ-X`. Answer ONLY that request. Do NOT expand scope to adjacent questions you happen to notice — even if you think they'd be useful to Planner. If you genuinely think a follow-up question is necessary, note it in your `notes` agent-return field; Planner decides whether to open another RQ.
**Reason**: Stage 4 runs analysts in parallel (up to N=5). Scope creep in one analyst means its answer to its own RQ is incomplete (token budget spent on side quests), and the planner's eventual aggregation gets cross-contaminated by half-answers to neighboring questions.

### AR-003 | Priority: high
**Rule**: Write to EXACTLY ONE file: `team/findings/RQ-<your-assigned-id>.md`. Do NOT write to other `team/findings/RQ-*.md` files even when you think they're related; they belong to peer analysts who may be running concurrently in this same batch.
**Reason**: Per-analyst file isolation is the entire reason parallel Analyst spawn is safe. Cross-writes corrupt peer findings non-deterministically (whichever analyst writes last wins) and break Planner's per-RQ aggregation.

### AR-004 | Priority: medium
**Rule**: Always write your `RQ-X.md` with a full-file overwrite (Write tool against the path, not Edit against a partial existing file). A previous attempt's file may exist on the path when you are re-spawned via crash recovery, and your run must replace it cleanly rather than append to it.
**Reason**: Crash recovery and BAD_RETURN paths re-spawn analysts onto the same RQ. Append-style writes from sequential attempts would silently merge stale content into your final findings.

### AR-005 | Priority: medium
**Rule**: When you cannot find reliable information for some part of the question, write the partial finding with `Confidence: low` and state the gap explicitly. Do NOT invent answers, do NOT extrapolate from weak sources, and do NOT silently scope the question down to what you can answer. Planner needs to know when to commission follow-up research (a new RQ in the next planning round).
**Reason**: Hidden gaps surface as planning errors downstream — Planner builds tasks on a phantom finding, executors implement those tasks, validators pass the implementations, and the gap only becomes visible at integration or milestone time. Explicit gaps are cheap to fix; phantom findings cascade.

## Format

```
### AR-XXX | Priority: high | medium | low
**Rule**: Specific behavioral instruction.
**Reason**: Why this rule exists (what failure it prevents).
```
