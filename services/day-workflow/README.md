# Day workflow — SHADOW simulation and explicit read-only adapters


Implemented in `day_workflow.py`, with tests in `test_day_workflow.py`.
This is an offline, evidence-packet-driven state machine, **not the completed live
automation**. The SHADOW branch has no network client or effects dispatcher. Separately invoked
read-only capture and canonical accounting adapters are now packaged alongside it. Its `SIMULATE_*`, `SCHEDULE_SIMULATION`,
`JOURNAL_SIMULATION` and `ACCOUNTING_SIMULATION` outbox entries are inert test
artifacts. They must never be reported as placed orders, installed reminders,
published journals, actual trades or protective monitoring.

Implemented behavior:

- One selected butterfly, one lot total, no automatic recenter or re-entry.
- Owner's ₹1,000 daily loss budget, separate from the ₹1,000 cash reserve.
- Conservative admission: loss at exact worst permitted entry prices plus supplied
  round-trip cost bound must fit ₹1,000. This is an implementation choice for
  shadow testing, not a guarantee against legging, execution, cost or gap losses.
- Net liquidation P&L from deduplicated cycle fill cash flows, signed remaining
  quantities, executable-side closing quotes, incurred charges and remaining
  exit-cost bound. The ₹1,000 threshold emits an exit simulation request.
- Uses the repository v2.5 controller with explicit gate inputs; refuses
  missing defaults, stale margin, mismatched geometry/sequence, missing costs or
  unverified account state. Cross-index selection consumes the existing research
  layer's evidence-backed global candidate order; it does not invent a new ranking
  model or acquire news/HF observations itself.
- Margin sequence must be put wing → put body → call wing → call body, matching the
  executor. The separate MCP source now accepts `entrySequence: PAIRED_HEDGES`;
  its default remains `WINGS_FIRST` for compatibility. Always pass
  `reserveRupees: 1000`. Existing cached WINGS_FIRST passes cannot be reused.
- Simulated review/deadline/flat-check registration precedes simulated entry.
  Shadow timing defaults are 15-minute reviews (10 when RV is marginal), last
  entry before 14:30, exit initiation at 14:45, and a 15:00 flatness check. These
  conservative test defaults have not been adopted as live scheduling policy.
- Atomic private state replacement, directory fsync, nonblocking process lock,
  exact duplicate event/fill detection and persistent entry/exit intent.
- Partial/unknown execution and pending orders produce recovery alerts; account
  access failure is never flatness. Deadline exit does not depend on news, margin
  refresh or journal success. After-close residual exposure is LOCKED_OVERNIGHT.
- Pause explicitly hands off responsibility; it does not flatten. Only explicit
  resume or close-and-stop resumes action. Confirmed flatness plus zero pending
  orders stops day-owned simulated jobs. Expired mandates never enter next day.

Verification (no broker calls):

```sh
cd services/day-workflow
python3 -B -m unittest -v test_day_workflow.py
```

Run one prepared synthetic event packet (the tests document its exact schema):

```sh
python3 -B services/day-workflow/day_workflow.py \
  --state-dir /tmp/volarb-shadow-example \
  --input /absolute/path/to/synthetic-event.json
```

Input requires `mode: SHADOW`, mandate `day`, unique `event_id`, timezone-aware
`asof`, a synthetic account packet and stage-specific normalized evidence. LIVE
mode is rejected unconditionally. Never use actual broker receipts as synthetic
fixtures. No `risk_limits.json` or alternate financial ledger is created.

## Packaged read-only/accounting adapters

`master_workflow.py`, `workflow_decision.py` and `workflow_observation.py` compose
verified account, HF, news and candidate evidence. `workflow_accounting.py` uses
`trade_ledger.py`, `review_scorecard.py` and `simple_ledger.py` for explicit canonical
fill/cycle commits; evaluating decisions alone never writes the financial ledger.
`--capture account|market|position` is a separate read-only operation, disabled
unless `VOLARB_OBSERVE_ENABLED=true`. No credentials are included.

`volarb_paths.py` binds source to the checkout and all private data to
`VOLARB_DATA_DIR` (default `~/.local/share/volarb`). Do not substitute historical
repository trade logs for the authoritative `Trading/ledger` store. Existing
financial state must be restored separately; setup does not initialize it.

Pure wide-selection/tail-stress helpers and shadow forecast/audit helpers are also
packaged. They do not activate historical research or override the first-terminal
controller. The [agent kit guide](../../docs/AGENT_KIT.md) explains setup and use.

**Still not implemented/activated by this kit:** agent-driven end-to-end current
news/candidate acquisition, automatic scheduler/delivery and deadline recovery,
live order dispatch authorization, automated journal publication, encrypted
state restoration and a real second-device migration rehearsal. The executor
source remains disabled and the execution policy draft remains inactive.

Source provenance is in `agent-kit/source-inventory.json`. Synthetic tests use
temporary accounting stores; no live financial records or credentials were copied.
