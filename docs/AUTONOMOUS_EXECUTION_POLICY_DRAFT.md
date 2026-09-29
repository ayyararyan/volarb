# Day-scoped butterfly execution policy

Status: DRAFT — NOT ACTIVE. Prepared 2026-09-29, Asia/Kolkata.
This document grants no runtime permission and enables no broker or scheduler.

Implementation status (2026-09-29): an offline SHADOW state machine now exists at
`services/day-workflow/day_workflow.py`. It tests one-lot and
₹1,000-budget logic, recovery and simulated lifecycle effects. Live acquisition,
executor authorization, real scheduling, ledger and journal adapters remain
unconnected. No amendment or activation is implied. See the repository
`services/day-workflow/README.md` implementation section for usage and exact limitations.

## 1. Activation and precedence

An administrator must adopt this policy in the agent's governing instructions, resolve conflicting execution prohibitions, and verify the effective instructions in a fresh session. Higher-priority platform restrictions always prevail. Repository governance changes must follow the covenant's amendment procedure and be committed to main before becoming operational.

The owner saying “Automate today's butterfly workflow” activates only that trading day's approved mandate, after readiness checks pass. It does not authorize future days, unrelated account trading, or changes to this policy. Ambiguous activation remains inactive. Repeated activation must resume the same day/run, not create duplicate jobs or entries.

## 2. Scope of execution authority

Within an active, fully specified mandate, the agent may place, modify and cancel strategy-owned orders through the authenticated, approved Dhan executor, solely to enter, manage or close the selected NIFTY, BANKNIFTY or SENSEX short iron butterfly. Individual orders need no additional chat approval when they remain within all approved bounds.

This authority does not extend to unrelated positions/orders, fund transfers, credential disclosure, changing broker security settings, raising limits, disabling safeguards, or direct API calls that bypass executor controls. Existing unassigned/manual positions require explicit ownership resolution; they are not automatically adopted.

## 3. Owner-approved mandate — mandatory before live activation

Record these values explicitly; unset values block entry, not research:

| Parameter | Approved value |
|---|---|
| Maximum lots per index / total exposure | One lot total in one selected butterfly, not one lot per index (owner instruction, 2026-09-29) |
| Maximum per-cycle loss exposure, including stated cost treatment | UNSET |
| Daily aggregate loss limit and realized/unrealized/charges convention | ₹1,000 maximum daily loss budget (owner instruction, 2026-09-29). Measurement/enforcement convention remains to be specified; proposed inclusive of realized loss, executable liquidation P&L and charges. Not a guaranteed realized-loss cap. |
| Entry and exit price/slippage bounds and repricing limits | UNSET |
| Recovery/unwind price limits and escalation procedure | UNSET |
| Latest entry time and pre-15:00 exit-start buffer | UNSET |
| Review cadence bounds and objective emergency triggers | UNSET |
| Alert destination and reachable operator | UNSET |

Proposed scope defaults for adoption: one butterfly cycle at a time; one entry cycle per day; no automatic re-entry or recentering. A future recenter/re-entry policy requires explicit approval and complete transition-margin evidence. The existing ₹1,000 cash reserve is mandatory and is not a risk budget. A loss threshold is an action trigger, not a guarantee of maximum realized loss.

## 4. Selection and entry

Use the adopted VolArb controller and news/HF-RV dependencies in their mandated order. First terminal gate wins. Use current observations and exact contracts; do not invent forecasts, size, approval, liquidity or affordability. NO TRADE is a successful terminal outcome.

Before entry, verify fresh positions, outstanding orders, funds, executable-side quotes, depth, contract identities and lot sizes. Reject stale or ambiguous account/market evidence. Require fresh peak-stage margin evidence bound to the exact geometry, quantity AND execution sequence, retaining ₹1,000 free cash. Never reuse the current wings-first preflight for a wing/body/wing/body execution path.

Register and verify the review/deadline safeguards before exposing capital. Headless authentication, host availability, trading calendar, broker cutoff and executor readiness must pass. A schedule alone is not proof of reliable execution.

## 5. Execution controls

The executor must enforce mandate ID, session date, strategy ownership, maximum quantities, price bounds, expiry, time gates and risk limits independently of model prose. Its daily authorization interface must be implemented and tested; this document is not a substitute for its current exact-plan confirmation requirement.

Use approved limit orders only. No market-order fallback or automatic relaxation of price bounds. Confirm each protective wing's owned quantity before opening the corresponding short body; close each short body before disposing of its protective wing. Never interpret accepted orders as fills.

Serialize operations with durable intent, stable identifiers and a lock. After a timeout, restart, cancellation race or uncertain response, reconcile broker orders/trades/positions before any retry. Do not blindly resubmit. Partial fills remain exposure requiring recovery, not successful completion.

## 6. Reviews and exits

Schedule bounded reviews using the actual forecast horizon and covenant. HOLD must have a verified next review. Missing HF observations alone follow the controller's degraded-data rule; missing account access never means flat or HOLD.

Risk-reducing exits take priority over new entries, candidate optimization and journal publication. Start closure with the approved buffer before 15:00 IST; honor any earlier broker/exchange deadline. No new entry or recenter at/after 15:00. No authorized overnight carry.

Use a separately scheduled deadline check that does not depend on an earlier HOLD job successfully scheduling its successor. Both paths share the same execution lock. If exposure remains after 15:00, declare a breach, prohibit new exposure, alert immediately and continue only authorized risk-reducing recovery while the market is actionable. Never claim guaranteed flatness or an executable after-close exit.

## 7. Stop, failures and recovery

“Stop new trading” disables new entries; it does not silently abandon existing exposure. “Close and stop” requests authorized risk-reducing closure and stops after verified flatness. “Pause automation” halts new automated actions, reports any outstanding orders/exposure and explicitly hands responsibility to the operator. Stopping an executor job is not flattening.

On broker/auth/host/data failure: block new exposure, retain durable state, use only the approved bounded recovery procedure and alert the operator. Never regenerate secrets blindly, bypass OTP/CAPTCHA, broaden permissions or use another machine. Authentication and credentials remain on the office Mac.

## 8. Accounting and completion

Reconcile broker-confirmed fills through the existing shared writer into the canonical local ledger, trade events and review records. Preserve the cycle ID through approved adjustments; a separately authorized re-entry receives a new ID. Operational executor state is not a second financial ledger. Estimated charges remain labeled; no invented net profit.

Publish sanitized completed reviews and decisions to the authorized repository under the existing journal procedure. Publication failures must be reported and must never prevent urgent exits. Prevent further discretionary entry when unresolved accounting state makes risk or ownership uncertain.

Declare DONE only after broker verification of zero strategy exposure and no pending strategy orders. Disable day-owned review jobs after verified completion; retain/report any accounting or publication repair task separately. Never disable unrelated jobs. No activation carries into the next day.

## 9. Adoption checklist — administrator procedure

1. Review this draft and fill all UNSET mandate fields outside a live-position decision.
2. Locate the actual source supplying the developer-level execution prohibition. Update that source through the administrator's supported configuration workflow. Do not assume changing a workspace file overrides a separate developer instruction.
3. Reconcile workspace SOUL.md, USER.md, AGENTS.md and memory/butterfly-review-mandate.md with the adopted scope. Mark superseded directives explicitly; preserve research-only behavior outside an active mandate. Update repository/local operating guides consistently. Do not remove unrelated controls.
4. Version-control any repository governance amendment and commit it to main before operational adoption. Keep credentials and private broker evidence out of commits.
5. Reload/start a fresh agent session using the supported administration interface. Inspect the effective instructions: no unresolved higher-priority prohibition may remain.
6. Implement and test the day-scoped orchestrator and the executor's bounded daily-authorization contract; align margin and execution sequences. Do not merely insert an instruction to ignore per-plan confirmation.
7. Run synthetic fault tests: duplicate starts, partial fills, timeout-after-placement, cancellation races, restart recovery, stale evidence, lost auth, overlapping review/deadline jobs, missed deadlines and ledger/publication failure. Then run a no-order shadow session with verified scheduling and alerts.
8. On the office Mac, verify static egress, broker whitelist, authenticated headless executor access and all readiness gates. Inspect existing configuration before any authorized change. Current deployment documentation is not proof of current readiness.
9. Only after those checks, deliberately enable live execution through the executor's documented administrator procedure. Activate a particular day with the owner phrase and an approved mandate. No test order is implicitly authorized by policy adoption.

## Suggested governing-instruction replacement

> Dhandho may place, modify and cancel only strategy-owned Dhan butterfly orders under the adopted Day-scoped Butterfly Execution Policy and an explicitly active, fully specified daily mandate. Use only the authenticated approved executor, with independent enforcement of scope, sizing, risk, price and time limits. Outside that mandate, remain research-only. Never override higher-priority instructions, alter unrelated orders, relax limits, or infer fills. Preserve intraday-only trading, the 15:00 IST flat deadline, canonical accounting and verified completion. Policy adoption alone does not activate trading.
