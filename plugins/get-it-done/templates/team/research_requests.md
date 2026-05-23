# Research Requests

_Owned by Planner. Read by the dispatcher to fan out Analyst sub-agents (one per request)._

When Planner needs research before it can finalize the PRD or task DAG, it writes one or more research requests here, then emits `next_phase_request: ANALYZING` in its agent-return YAML with `research_request_ids` populated. The dispatcher then spawns one Analyst per request, each writing to `team/findings/<req_id>.md`.

## Request schema

```markdown
### RQ-1
- **Question**: <one or two sentences — the question Analyst must answer>
- **Mode**: free | feature_landscape       # `feature_landscape` triggers the PR-009 protocol in analyst.md
- **Success Criteria**:
  - <bullet of what a satisfying answer must contain>
- **Depth**: shallow | medium | deep
- **Notes for Analyst**: <optional context, scoping hints, sources to prefer>
- **Status**: open                           # open | fulfilled; dispatcher flips to fulfilled when analyst returns
- **Claimed_by**: null                       # analyst-RQ-1 while in-flight; cleared on persist (Stage 4+)
- **Claimed_at**: null
- **Findings path**: team/findings/RQ-1.md   # echo of where the analyst writes
```

## Invariants

- `RQ-` IDs are stable across batches; once Planner has decided RQ-3 exists, it never gets renumbered even if RQ-1 is dropped.
- Each request is independent of every other request in the same batch (this is what permits parallel Analyst spawn — Stage 4 activates it). If two questions are interdependent, sequence them across two planner→analyst rounds rather than batching them. See PR-012.
- Planner re-reads `team/findings/<req_id>.md` for every open request before re-running its decomposition.
- `Claimed_by` is owned by the dispatcher — Planner never writes it. The dispatcher sets it just before spawning the analyst and clears it on persist. A non-null `Claimed_by` with `Status: open` is the crash-recovery signal (see `team/state.md` crash detection contract).

---

_(empty — Planner populates this only when research is needed.)_
