# Decision-Layer Output

The analysis may be extensive; the user-facing answer must be minimal. Unless the user explicitly asks for explanation, output **one markdown table only** and no prose before or after it.

## Mode A — open butterfly, before 14:45 IST

Use exactly one row:

| Decision | Why | Next review |
|---|---|---|
| HOLD / RECENTRE / SQUARE OFF | One short, concrete reason | Time or `—` |

Decision rules:
- **HOLD** = no action. Use when the butterfly remains acceptably aligned with the expected path and no material tail-risk exception is active.
- **RECENTRE** = use only when the expected distribution/spot has shifted materially away from the body but the thesis remains range-bound and adjustment remains feasible.
- **SQUARE OFF** = use when credible tail/jump risk, directional follow-through, break-even/wing threat, or execution/liquidity deterioration makes holding the current fly unattractive.

Give only one decision. Never add an alternative action, hedge suggestion, or "if X then Y" branch in the table.

The `Why` cell must be short and concrete, e.g. `Oil shock has worsened; downside gap risk is now material.` Avoid long macro summaries.

### Next-review timing algorithm

Populate `Next review` only when the decision is **HOLD**. Choose the earliest useful re-evaluation point from current conditions:
- **Calm / no catalyst / stable cross-asset picture:** `At close`.
- **Mild uncertainty or a scheduled catalyst later in the session:** approximately `60–120 min` or just after that catalyst, whichever comes first.
- **Elevated but not yet action-worthy risk, fast-moving news, or spot approaching a break-even:** approximately `15–30 min`.
- **Acute risk:** do not use HOLD; choose RECENTRE or SQUARE OFF instead.

When `references/expiry-exit-algorithm.md` is active, override the generic cadence with the tighter expiry cadence: about **30–60 min** before noon on expiry day, **20–30 min** from 12:00–13:30, and **10–20 min** from 13:30–14:45 while still open. At/after 14:45 on expiry day, default to SQUARE OFF rather than scheduling another HOLD review.

Use an actual clock time in IST whenever practical, not merely the interval.

## Mode B — open butterfly, 14:45 IST or later

The decision is primarily whether to carry the position overnight/weekend. Use exactly one row:

| Decision | Why | Next review |
|---|---|---|
| CARRY / RECENTRE / SQUARE OFF | One short, concrete reason | Time or `—` |

Decision rules:
- **CARRY** when the expected overnight path is stable enough for the fly geometry and no material tail-risk exception is active.
- **RECENTRE** when range-bound carry still makes sense but the body is materially misaligned before the close and adjustment is realistically executable.
- **SQUARE OFF** when overnight/weekend jump risk, event risk, or directional stress is too large relative to the fly.

Give only one decision. For **CARRY**, set `Next review` to the next meaningful price-discovery point, normally pre-open/GIFT/early Asia or immediately after a known overnight catalyst. For RECENTRE/SQUARE OFF, use `—` unless another review is explicitly requested.

## Mode C — no butterfly open / candidate evaluation

First apply a tail-risk gate:
- **Default:** if the underlying is expected to be stable/range-bound/choppy and no exceptional tail-risk condition dominates, evaluate wide butterflies and return recommendations.
- **Exception:** if credible tail/jump risk is material enough that the terminal/path distribution is unreliable or likely to overwhelm the chosen wings, recommend no butterfly.

When candidates are allowed, return exactly one short table with up to three ranked rows:

| Rank | Butterfly | Why |
|---:|---|---|
| 1 | [expiry] [lower / body / upper] | Short reason tied to centre alignment, theta/carry/tail risk and liquidity |
| 2 | ... | ... |
| 3 | ... | ... |

Do not append alternative strategy ideas or narrative commentary. These are the three recommendations, not "one pick plus alternatives."

When the tail-risk gate rejects the trade, return **one explicit NO TRADE row**. Never return headers with zero rows:

| Rank | Butterfly | Why |
|---:|---|---|
| — | **NO TRADE** | Tail-risk gate failed: [short concrete reason]. [Optional: re-run at the next meaningful price-discovery point.] |

The `Why` cell must identify the actual dominant risk, not merely repeat `tail-risk gate failed`. Examples: `Weekend oil/geopolitical jump risk is not yet priced; re-run Monday pre-open.` or `Live chain/liquidity data are insufficient to validate an executable fly; re-run after quotes refresh.`

If the market is closed and the gate **passes**, include `pre-open watchlist` briefly inside each recommended row's `Why` cell rather than adding prose outside the table. If the gate fails, use the single **NO TRADE** row instead.

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


## v2.4 post-close operational state

If the home option market is closed and the position cannot be changed, do not present a fresh CARRY recommendation. Use a one-row status table with `LOCKED OVERNIGHT` and the next actionable exit/review.
