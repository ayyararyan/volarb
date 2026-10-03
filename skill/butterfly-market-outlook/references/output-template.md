# Decision-Layer Output

The analysis may be extensive; the user-facing answer must be minimal. Unless the user explicitly asks for explanation, output **one markdown table only** and no prose before or after it.

This file formats an already-determined action; it does not own decision policy.
Run [decision-algorithm.md](decision-algorithm.md) first and preserve its dominant
terminal gate. The [personal covenant](https://github.com/ayyararyan/volarb/blob/main/docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md)
overrides all generic overnight examples: intraday only, flat by 15:00 IST, and no
entry/recenter thereafter. A review time is a recommendation, not scheduled monitoring.

## Mode A — open butterfly, before 14:45 IST

Use exactly one row:

| Decision | Why | Next review |
|---|---|---|
| HOLD / RECENTRE / SQUARE OFF | One short, concrete reason | Time or `—` |

Render the controller action:
- **HOLD** = no action, only after all applicable earlier gates survive.
- **RECENTRE** = only when the controller allows the adjustment, including fresh verified full-transition margin.
- **SQUARE OFF** = preserve the first terminal exit reason, including loss budget, HF RV/drift, hard risk, expiry or the personal deadline; a later favourable metric cannot overturn it.

Give only one decision. Never add an alternative action, hedge suggestion, or "if X then Y" branch in the table.

The `Why` cell must be short and concrete, e.g. `Oil shock has worsened; downside gap risk is now material.` Avoid long macro summaries.

### Next-review timing algorithm

Populate `Next review` only when the decision is **HOLD**. Choose the earliest useful re-evaluation point from current conditions:
- **Calm / no catalyst / stable cross-asset picture:** the next controller-required review, no later than the personal 15:00 IST flat deadline; never defer to the exchange close.
- **Mild uncertainty or a scheduled catalyst later in the session:** approximately `60–120 min` or just after that catalyst, whichever comes first.
- **Elevated but not yet action-worthy risk, fast-moving news, or spot approaching a break-even:** approximately `15–30 min`.
- **Acute risk:** do not use HOLD; choose RECENTRE or SQUARE OFF instead.

When `references/expiry-exit-algorithm.md` is active, override the generic cadence with the tighter expiry cadence: about **30–60 min** before noon on expiry day, **20–30 min** from 12:00–13:30, and **10–20 min** from 13:30–14:45 while still open. At/after 14:45 on expiry day, default to SQUARE OFF rather than scheduling another HOLD review.

Use an actual clock time in IST whenever practical, not merely the interval.
Apply the tighter cadence whenever another gate requires it, including approximately
10–20 minutes for a `MARGINAL` HF state. Never schedule continued holding past the covenant deadline.

## Mode B — open butterfly, 14:45 IST or later

For the generic reusable policy this is the carry gate. In this repository's
personal deployment it remains an intraday wind-down: the covenant disallows
overnight carry and requires flat by 15:00 IST. Use exactly one row for the
covenant-compliant action. The following generic template is retained only for
contexts with a separately applicable overnight policy:

| Decision | Why | Next review |
|---|---|---|
| CARRY / RECENTRE / SQUARE OFF | One short, concrete reason | Time or `—` |

Generic labels are still controller outputs, not new rules: **CARRY** requires all
applicable overnight gates, **RECENTRE** additionally requires full-transition
margin, and **SQUARE OFF** preserves the first exit-level result. No generic label
can override Aryan's intraday-only covenant.

Give only one decision. For **CARRY**, set `Next review` to the next meaningful price-discovery point, normally pre-open/GIFT/early Asia or immediately after a known overnight catalyst. For RECENTRE/SQUARE OFF, use `—` unless another review is explicitly requested.

## Mode C — no butterfly open / candidate evaluation

Render candidates only after the complete canonical candidate pass, including
data health, loss-budget evidence, session VRP, fresh re-entry when applicable,
HF RV/drift, event/path gates, optimization and exact-candidate margin validation.
A range-bound outlook or successful optimizer alone is insufficient. Return only
the controller's `margin_eligible_candidate_ids` in their ranked order.

When candidates are allowed, return exactly one short table with up to three ranked rows:

| Rank | Butterfly | Why |
|---:|---|---|
| 1 | [expiry] [lower / body / upper] | Short reason tied to centre alignment, theta/carry/tail risk and liquidity |
| 2 | ... | ... |
| 3 | ... | ... |

Do not append alternative strategy ideas or narrative commentary. These are the three recommendations, not "one pick plus alternatives."

When any required gate rejects or cannot validate entry, return **one explicit NO TRADE row**. Never return headers with zero rows:

| Rank | Butterfly | Why |
|---:|---|---|
| — | **NO TRADE** | [Dominant terminal-gate reason]. [Optional: next useful evidence refresh.] |

The `Why` cell must identify the actual dominant blocker, not a generic tail-risk
label. Examples: `Session premium is unfavourable; do not begin HF candidate work.`
or `Live chain/liquidity data are insufficient to validate an executable fly.`

Closed-market or stale observations cannot validate executable candidates. Use
the **NO TRADE** row for an executable-candidate request. If the user explicitly
asks for indicative research/watchlists, label them `pre-open watchlist — not
entry-validated`; they do not substitute for a fresh complete candidate pass.

## What stays internal

Unless the user asks for detail, do not surface:
- carry-state labels such as Comfortable/Manageable/Fragile/Poor;
- the full scenario tree or stress grid;
- macro dashboards;
- detailed OI/IV/skew commentary;
- formulas or sigma arithmetic;
- alternate decisions;
- hedge ideas;
- multiple conditional branches.

All live-data citations or source references should be attached compactly to the factual reason they support without expanding the table.


## Post-close operational state

If the home option market is closed and the position cannot be changed, do not present a fresh CARRY recommendation. Use a one-row status table with `LOCKED OVERNIGHT` and the next actionable exit/review.
