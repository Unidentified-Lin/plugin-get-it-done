# Team State

_Schema version 2 — batch-aware. This file is the **machine state** the dispatcher (main session, via `/continue`) reads and writes every tick: the YAML block below plus the batch-history ledger at the bottom. Sub-agents MUST NOT edit `.get-it-done/state.md`._

_The **specification** — phase/transition rules, batch-lifecycle contract, crash-recovery contract, git-isolation model, and the **agent-return YAML contract** every sub-agent emits — lives in `.get-it-done/STATE_SPEC.md`. Read that for the shapes; this file only carries the live values._

## State Machine

```yaml
schema_version: 2
phase: IDLE                  # IDLE | PLANNING | ANALYZING | EXECUTING | REPORTING | COMPLETE | AWAITING_HUMAN
status: WAITING              # WAITING | RUNNING
batch_id: null               # e.g. "B0007" when a batch is in flight; null otherwise
batch_started_at: null       # ISO timestamp written before dispatcher spawns the batch
batch_ended_at: null         # ISO timestamp written after dispatcher persists batch results
active_agents: []            # see STATE_SPEC.md "active_agents entry schema"; populated while batch_id != null
goal_set: false
last_updated: null           # ISO timestamp — set whenever dispatcher rewrites this block
```

The dispatcher reads this block via `gid.py state` (JSON) and rewrites it via `gid.py claim-batch` / `close-batch` — it does not hand-parse or hand-edit the file in the common path.

## Batch history

Each completed batch appends a `## Batch <id>` block below (written by `gid.py close-batch`; format in `STATE_SPEC.md` "Batch handoff log format"). The dispatcher never reads these back — it derives the next batch from `task_queue.md` state alone — but they are the human- and Reflector-readable ledger of batch dynamics.

---

_(No active batch — team is IDLE.)_
