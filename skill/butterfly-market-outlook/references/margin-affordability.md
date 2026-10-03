# Dhan entry-margin affordability

Use after higher-priority strategy/data/event gates, before returning executable candidates. This is a feasibility gate, not a risk budget or order authorization.

## Live tools

- `dhan_check_butterfly_margin`: symbol, expiry, lower, center, upper, exact lots; optional explicit `reserveRupees` and/or `reservePercent` (percentage of available funds; larger reserve wins). No implicit reserve default and no invented capital. Use an already-approved policy; if unavailable, report UNVERIFIED rather than routinely asking during every review.
- `dhan_calculate_basket_margin`: exact legs, unit quantities, prices and INTRADAY product. Raw indicative requirement only; cannot establish affordability.
- Repository adapter: [`services/dhan-chatgpt-mcp/src/margin-preflight.mjs`](https://github.com/ayyararyan/volarb/blob/main/services/dhan-chatgpt-mcp/src/margin-preflight.mjs); both tools on the research `/mcp` endpoint. Deployment checkout locations are host configuration, not package paths. These tools cannot place, modify or cancel orders. REST calculator uses `POST /v2/margincalculator/multi` with `scripList`, `includePosition: true`, `includeOrder: true`. Funds use `GET /v2/fundlimit`. The official SDK and a live read-only probe verified this payload on 2026-09-29; do not use conflicting `scripts/includeOrders` examples blindly.

## Algorithm and interpretation

1. Refresh funds, positions AND outstanding orders. Access failure is not flatness. Outstanding or unknown-status orders make this preflight UNVERIFIED: pending wings are not filled hedges.
2. Resolve each exact contract and its own current lot size from Dhan's master. Check freeze limit. Use unit quantities once, not lots multiplied twice.
3. Fetch the actual legs' quotes. BUY at ask, SELL at bid; require enough top-level size and a trade timestamp no older than 30 seconds. Missing/degraded quotes block approval.
4. Simulate the specified **put wing BUY, call wing BUY, put body SELL, call body SELL** sequence via each cumulative prefix. Every protective wing must be filled before relying on it. Compute peak of those broker totals, separately retain final margin. This is an indicative completed-stage estimate, not an RMS guarantee for partial fills or a different order sequence.
5. Compare account-inclusive totals **directly to free available funds**, conservatively, with no subtraction of `utilizedAmount`. Existing positions can make this over-conservative; do not claim it is the exact incremental margin. Do not add option premiums again to a total already returned by Dhan; the live long-only probe included premium. Ambiguous results are UNVERIFIED, not zero.
6. Refresh account again; changes invalidate the check. Require completion within 30 seconds. Only PASS with nonnegative remaining headroom after the explicit reserve can qualify. No entry PASS outside the intraday entry window. A PASS remains indicative and expires 30 seconds after acquisition; price/size/sequence/account changes invalidate it immediately. Recheck before manual execution.

## Controller binding and output

Map each full MCP packet under its exact finalist ID: `candidate_margin_checks[id]`. Supply `candidate_ids` in ranking order and `candidate_count`. Only return IDs in the controller's `margin_eligible_candidate_ids`; omit rejected/unverified candidates from executable recommendations. Keep geometry, expiry, lots, sequence, quote time and packet bound together in local evidence. The controller requires PASS, timestamps, no blockers and coherent funds/peak/reserve/headroom arithmetic, not a bare supplied status flag.

Within the existing single output table, include lots, peak requirement, available funds and headroom in the candidate explanation when useful. API failure, stale data or missing policy -> no executable candidate, clearly state why. Estimates after close are diagnostic only. Never use maximum payoff loss as margin, and do not narrow wide wings or resize without renewed evaluation.

## Recenter and exits

The MCP preflight is ENTRY_ONLY: it does not simulate closing old positions or shared-leg rotations. Never label its packet RECENTRE. A recenter needs separately verified full transition evidence (scope RECENTRE, same normalized funds/peak/reserve/time fields); otherwise the controller blocks recenter and independently retains earlier exit/risk decisions. Once old positions are verified closed, a permitted re-entry can use a fresh entry preflight. Missing entry margin never blocks a risk-reducing SQUARE OFF or proves that HOLD is safe.

## Sources

- https://dhanhq.co/docs/v2/funds/
- https://github.com/dhan-oss/DhanHQ-py/blob/main/src/dhanhq/_funds.py
- https://dhan.co/support/orders-and-positions/order-types/what-is-the-difference-between-original-margin-and-final-margin-in-basket-order/

Exact candidate binding: supply `candidate_specs[id]` with exactly `symbol`, `expiry`, `lower`, `center`, `upper`, `lots`; it must equal the MCP packet's `candidate` object. A missing or mismatched binding is not eligible, even if the packet says PASS.
