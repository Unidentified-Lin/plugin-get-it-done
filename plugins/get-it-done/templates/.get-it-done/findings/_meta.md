# Findings directory

_One file per research request: `.get-it-done/findings/<req_id>.md`._

Owned by individual Analyst sub-agents. Each Analyst writes exactly one file matching the `req_id` it was assigned in its spawn prompt. No file in this directory is shared between Analysts — there is no cross-Analyst write contention by design.

Planner reads every `.get-it-done/findings/RQ-*.md` whose corresponding entry in `.get-it-done/research_requests.md` is still `Status: open`. Stale findings (older `RQ-` IDs from a previous goal) are cleared by `/objective` when a new goal is set.

## Per-finding schema

```markdown
# Findings — RQ-1

## Question (echoed from research_requests.md)
<one or two sentences>

## Findings

### <Area / Subtopic>
**Finding**: <clear statement>
**Confidence**: high | medium | low
**Sources**: <URLs or file:line references>
**Implication for project**: <what Planner should change>

## Key recommendations to Planner
1. <most important>
2. <second>

## Risks and unknowns
- <risk>: <mitigation suggestion>

## Completed at
<ISO timestamp>
```

## Feature Landscape Research mode

When the matching `research_requests.md` entry has `Mode: feature_landscape`, the Analyst follows the PR-009 protocol from `agents/analyst.md` — ≥3 comparable products, ≥10 features each with cited URLs, plus intersection (Must-Have candidates) and union-minus-intersection (Should/Nice-to-Have candidates).
