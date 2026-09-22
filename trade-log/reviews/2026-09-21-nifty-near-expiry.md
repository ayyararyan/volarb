# NIFTY carried butterfly — 2026-09-18 to 2026-09-21

Type: **executed trade / live position review**

Trade ID: `2026-09-18-NIFTY-001`

Provenance: **conversation-reconstructed, with user-supplied final realized P&L and leg geometry**

## Final trade summary

- Instrument: **NIFTY**
- Strategy: **wide symmetric iron butterfly**
- Geometry: **22,650 PE / 23,350 PE + 23,350 CE / 24,050 CE**
- Body: **23,350**
- Wing width: **700 points**
- Opened: **Friday afternoon, 2026-09-18**
- Closed: **Monday, 2026-09-21**
- Final position state: **all four legs closed; net quantity = 0**
- Gross realized P&L: **+₹5,313.75**
- P&L basis: **before brokerage, exchange charges, GST, STT and other transaction costs**

### Leg-level realized P&L

| Leg | Role in iron fly | Realized P&L |
|---|---|---:|
| 22,650 PE | Lower put wing | -₹143.00 |
| 23,350 PE | Put at body | +₹5,710.25 |
| 23,350 CE | Call at body | -₹198.25 |
| 24,050 CE | Upper call wing | -₹55.25 |
| **Total** |  | **+₹5,313.75** |

The leg P&Ls sum exactly to the reported gross realized P&L.

## Trade chronology

### Friday, 2026-09-18 — entry

- The NIFTY butterfly was opened on **Friday afternoon, 2026-09-18**.
- The executed geometry is now known as a **23,350-centered symmetric iron butterfly with 700-point wings**:
  - 22,650 PE lower wing;
  - 23,350 PE and 23,350 CE body;
  - 24,050 CE upper wing.
- The position was intentionally carried over the weekend rather than treated as an intraday trade.
- Exact entry time, expiry, quantity and entry fill prices are still not available in the currently recoverable data.

### Monday, 2026-09-21 — active management

- The same carried NIFTY butterfly was still open and being actively managed on Monday.
- The trade was already in the **near-expiry regime**, with the discussion explicitly noting that there was only about **one trading day left to expiry**.
- Several fresh reviews were requested during the session rather than relying on the prior decision.
- Specific review checkpoints requested in the working session included approximately **14:20 IST** and **14:40 IST**.
- As the session approached the late-afternoon gate, the decision problem shifted from ordinary HOLD logic toward the explicit **overnight CARRY / RECENTRE / SQUARE OFF** framework used after 14:45 IST.
- Fresh market/news context was treated as relevant because an overnight shock could dominate the remaining theta harvest.
- The user explicitly revisited whether **recentring** made sense with only one day remaining and asked whether a sufficiently clear NIFTY next-24-hour trend could justify moving the body.

## Exit-rule change triggered during this trade

The original working rule was roughly: exit once about **75% of the available theta / maximum harvest** had been captured.

During this trade it became clear that this denominator is not static. As NIFTY moves relative to the butterfly body, the maximum profit still attainable from the *current* state changes materially. Comparing current P&L only with the original theoretical maximum can therefore give the wrong exit signal.

The rule was changed to a **dynamic harvest saturation** concept:

1. estimate the profit that can be banked immediately;
2. estimate the realistically attainable remaining harvest from the *current* spot/surface/geometry;
3. compare the incremental harvest with the gamma/path risk of continuing to hold;
4. include the break-even buffer and event risk;
5. near expiry, allow gamma/path risk to dominate even when instantaneous theta remains high.

This trade directly motivated the production Engine v2 expiry-exit layer.

## Recentring lesson from the trade

The discussion also sharpened the recenter rule:

- **spot drift alone is not enough** to justify RECENTRE;
- the range-bound/choppy thesis must still survive;
- the new body must materially improve alignment and/or tail risk;
- closing the old structure and reopening the new one must still make sense after friction;
- with only about one trading day remaining, the hurdle for recentering becomes much higher because there is little time to re-harvest carry.

This became the basis of the explicit Engine v2 recenter gate.

## Closure and outcome

- The position was fully closed on **Monday, 2026-09-21**.
- All four legs ended with **net quantity = 0**.
- Final **gross realized P&L was +₹5,313.75** before transaction costs.
- The largest positive contribution came from the **23,350 PE: +₹5,710.25**.
- The other three legs together contributed **-₹396.50**, leaving the final gross profit at **₹5,313.75**.
- The profitability of the trade was discussed specifically in the context that it had been opened on **Friday afternoon**, i.e. as a multi-session carry rather than a same-day trade.

## What is known vs unknown

### Known

- Instrument: **NIFTY**
- Strategy family: **wide symmetric iron butterfly**
- Lower strike: **22,650 PE**
- Body strike: **23,350 PE + 23,350 CE**
- Upper strike: **24,050 CE**
- Wing width: **700 points**
- Open date: **Friday, 2026-09-18**
- Open period: **afternoon**
- Holding period: **carried across the weekend into Monday**
- Close date: **Monday, 2026-09-21**
- Status: **closed**
- Final net quantity: **0**
- Gross realized P&L: **+₹5,313.75**
- Near-expiry state on Monday: **approximately one trading day remaining**
- Management included repeated intraday state reviews, overnight-carry analysis and explicit recenter consideration.
- This trade drove the move from static theta capture to dynamic harvest saturation.

### Still unknown / not safely reconstructable

- exact expiry date;
- lot quantity;
- precise entry time;
- individual entry fills / total entry credit;
- precise exit time;
- individual exit fills / total close cost;
- brokerage, exchange charges, GST, STT and other transaction costs;
- net P&L after all charges.

These fields remain blank rather than being inferred. If a historical Dhan tradebook, contract note or screenshot containing them becomes available, backfill the matching ledger row while preserving this decision-history note.
