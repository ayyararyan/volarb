# Day workflow — SHADOW simulation and explicit read-only adapters


Status: **strategy-specific research/shadow workflow**, not the reusable
[Execution Engine](../../execution-engine/README.md) or its
[Execution Testbed](../../execution-testkit/README.md). The butterfly v2.6 controller
is a research decision controller, not the generic execution pipeline.

Implemented in [`day_workflow.py`](day_workflow.py), with tests in
[`test_day_workflow.py`](test_day_workflow.py).
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
- Uses the repository v2.6 controller with explicit gate inputs; refuses
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

## Source ownership and entrypoint map

| Area | Entrypoints | Effects |
|---|---|---|
| Shadow state machine | `day_workflow.py`, `policy/master_algorithm.json` | Private synthetic state/outbox; no effect dispatcher |
| Research composition | `master_workflow.py`, `workflow_decision.py` | First-terminal research decision from explicit evidence |
| Observation ingress | `workflow_observation.py`, `volarb_paths.py` | Explicit read-only capture; private evidence, no broker mutation |
| Canonical accounting | `workflow_accounting.py`, `trade_ledger.py`, `review_scorecard.py`, `simple_ledger.py` | Explicit shared-writer commits only; no new alternate ledger |
| Current-only selection | `wide_butterfly_selector.py`, `robust_tail_selection.py` | Pure calculations; no implicit backtest |
| Shadow audit helpers | `decision_table.py`, `forecast_shadow.py` | Forecast/outcome audit; cannot override current controller |

Run the complete synthetic workflow/accounting suite from the repository root:

```sh
python3 -B -m unittest discover -s services/day-workflow -p 'test_*.py'
```

## Research packet compatibility with the current controller

`workflow_decision.compose` consumes normalized, explicitly sourced assessments;
it does not acquire a live dashboard or invent absent accounting evidence.

- Top-level `session_loss` must supply `asof`, nonnegative `rupees` (positive loss),
  and `evidence_ref` for candidate evaluation. Flatness does **not** imply zero
  session loss. The budget comes from the existing ₹1,000 policy. Missing/stale
  evidence is `NEED_EVIDENCE`; a verified breach terminates before VRP, news or HF.
- Each candidate index requires its own `session_vrp_snapshot` envelope containing
  `symbol`, `asof`, `evidence_ref`, and `state`. `state` is the source dashboard or
  equivalent snapshot accepted by
  [`evaluate_session_vrp.py`](../../skill/butterfly-market-outlook/scripts/evaluate_session_vrp.py),
  with a fresh `now` or `health.observation_timestamp`. The adapter recomputes the
  canonical gate; a bare `session_vrp_state: FAVOURABLE` flag is not accepted.
- VRP snapshots must explicitly prove `fit_ok: true` and arbitrage
  `checked: true, passed: true`. Missing/unchecked proof or malformed snapshot
  objects are `UNKNOWN`, never an absent-field approval or an uncaught exception.
- Missing, stale, wrong-index or unfavourable VRP terminates candidate evaluation
  before HF/news. NIFTY evidence is never automatically reused for BANKNIFTY or
  SENSEX. Equivalent per-index feeds must exist; synthetic test fixtures are not
  evidence that those live integrations exist.
- HF input retains `current_asof` for ingress freshness checks. Before invoking the
  RV child, the adapter sets its canonical `asof` to the verified decision clock;
  an unrelated payload timestamp cannot change the child's freshness decision.
- Existing-position review does not require a favourable candidate VRP screen.
  Missing, stale or invalid optional session-loss evidence remains an explicit
  controller warning and cannot mask a separately verified risk/expiry exit;
  candidate loss evidence remains mandatory and fail-closed.
  Existing loss/deadline/expiry protections remain independent of missing later
  research evidence. The normalized SHADOW `gates` packet includes explicit
  `session_vrp_state`, `daily_loss_budget_rupees`, and `session_loss_rupees` for
  candidates; these are synthetic adapter inputs, not live authorization.
