# Development history

This is a conversation-derived history of how the butterfly workflow evolved into Engine v2.

## 2026-09-20 — Front-end discipline and wide-fly optimization

The workflow was tightened so that a live review returns one small decision table only. Alternate actions and long scenario dumps were deliberately removed from the user-facing layer.

Candidate selection was reframed around **wide** butterflies rather than narrow flies. The optimization objective became a trade-off among:

- high theta / carry efficiency;
- low carry burden;
- low tail risk based on the *distribution* of losses, not simply maximum loss;
- adequate OI, bid/ask and execution liquidity.

The idea of reading the full exchange option surface and deriving skew, curvature and the terminal pricing distribution became part of the backend.

## 2026-09-21 — Live Dhan integration and near-expiry logic

The Dhan connector became the preferred source for live position truth and structured full-chain data.

During the carried NIFTY butterfly review, the exit rule was refined. A fixed percentage of original maximum theta was recognized as insufficient because the attainable profit changes as spot drifts.

The workflow therefore moved to **Dynamic Harvest Saturation**: compare the amount already bankable with what is still realistically harvestable from the current state, while explicitly accounting for gamma/path risk and break-even buffer.

The recenter engine was also tightened so that spot drift alone is never sufficient. A new fly must materially improve the risk/carry state after closing and reopening friction.

## 2026-09-21 to 2026-09-22 — Engine v2 architecture

The workflow was reorganized into a canonical MarketState architecture with explicit separation between:

- option-implied risk-neutral information;
- real-world event/path judgment;
- execution and liquidity;
- existing-position economics;
- candidate-search economics;
- follow-up state changes.

Data health and tail/event gates were moved ahead of theta optimization.

A promotion-gate concept was introduced to compare the more sophisticated v2 engine with the earlier simpler workflow before treating v2 as the production process. The emphasis was on deterministic checks, consistency, risk-sensitivity and decision quality rather than waiting for a long live P&L sample.

## 2026-09-22 — Repository capture

The complete live Butterfly Market Outlook v2 skill source, references and scripts were copied into this repository. Trade/review history is stored with explicit provenance so missing historical broker fields are left unknown rather than reverse-engineered.
