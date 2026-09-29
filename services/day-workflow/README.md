# Day workflow — SHADOW ONLY


Implemented in `day_workflow.py`, with tests in `test_day_workflow.py`.
This is an offline, evidence-packet-driven state machine, **not the completed live
automation**. It has no network client, order dispatcher, Gateway scheduler client,
or production-ledger writer. Its `SIMULATE_*`, `SCHEDULE_SIMULATION`,
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

**Remaining work before any live capability:** real read-only account/contract/
news/HF acquisition and packet binding; authenticated day-scoped executor bridge
with independently enforced limits (not auto-confirming its current manual plan
contract); verified OpenClaw job registration/delivery and missed-run recovery;
broker-evidence-to-shared-writer accounting; sanitized GitHub journal publisher;
adopted timing/price/cost policy; administrator-resolved instruction boundary and
broker readiness. These adapters are not supplied by the shadow runner. Do not
activate the executor just because its source tests pass. The MCP sequence patch
is source-only until deliberately deployed/restarted and rediscovered.

## Source and publication boundary

Copied from the office-Mac `Trading/code/day_workflow.py` and its unittest suite. The only source adaptation is repository-relative controller resolution so tests use the checked-out controller in Linux CI. No live deployment files, credentials, synthetic state output or financial ledger were copied. The [execution policy draft](../../docs/AUTONOMOUS_EXECUTION_POLICY_DRAFT.md) is inactive and grants no authority.
