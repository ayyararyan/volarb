---
name: market-news-signal-filter
description: Filter financial news for Indian index butterfly decisions. Separates factual information, attention, uncertainty and transmission-channel hazards.
---

# Market News Signal Filter

## Objective

Convert raw news flow into event-level signals for short-horizon Indian index risk. Separate four things that must never be collapsed into one sentiment score:

1. Fundamental information: credible, novel information that changes the economic state.
2. Attention hazard: market-moving salience or dissemination even when fundamentals are weak.
3. Uncertainty and volatility hazard: expansion of near-term outcome dispersion or tail states.
4. Market sensitivity: how strongly NIFTY, SENSEX, or BANKNIFTY currently responds to the event's transmission channel.

The first three describe the information. The fourth describes the market regime. Price reactions may update market sensitivity, but must never retroactively change whether a claim was true, well sourced, novel, or sensational.

## Mandatory calibration load

Before scoring an Indian-index news set, read `references/calibration.md`.

If calibration is older than 45 calendar days, mark it `STALE_CALIBRATION`. Continue using it only as a prior and rely more heavily on live cross-asset confirmation. Do not silently treat stale coefficients as current.

Read `references/monthly-recalibration.md` when performing a calibration refresh.

## Workflow

### Step 1: Define the decision window

For overnight butterfly use, freeze the news window from the prior Indian cash close, normally 15:30 IST, through the next pre-open/open. Preserve publication and event timestamps.

For intraday use, include only information available before the decision timestamp.

Never use later market outcomes when classifying the original information set.

### Step 2: Gather the source set

Browse current sources rather than relying on memory.

For each potentially material event, prefer:

- primary sources: government, regulator, exchange, central bank, company filing, court order, official statement;
- high-quality wires or specialist financial reporting;
- genuinely independent corroboration for major unscheduled claims.

Do not count syndicated copies of one wire story as independent confirmation.

### Step 3: Cluster articles into underlying events

Treat multiple stories about the same development as one event cluster.

Cluster by underlying fact, originating source, timestamp, and factual payload. Mark later stories as `follow-up`, `reprint`, `analysis`, or `new development`.

### Step 4: Extract the fact spine before reading tone

Record:

- who acted or said what;
- what changed versus the prior state;
- quantities, dates, thresholds, locations, and policy terms;
- whether the event is confirmed, proposed, threatened, denied, rumored, or already known;
- what remains unresolved.

Keep facts separate from adjectives, forecasts, commentary, and quoted opinions.

### Step 5: Score information quality

Use `references/rubric.md`.

Assess at least:

- source/evidence quality;
- novelty/staleness;
- independent confirmation;
- factual specificity;
- ambiguity/hedging;
- linguistic intensity;
- sensationalism/headline-body divergence;
- dissemination/attention potential;
- direct market relevance;
- plausible transmission channel;
- time horizon.

Use finance-specific context rather than generic sentiment dictionaries.

### Step 6: Separate language severity from event severity

Ask explicitly:

- If adjectives and dramatic verbs were removed, how serious would the factual event still be?
- If the same facts were written in calm official prose, would the risk assessment change?
- Is the headline materially more alarming than the body?
- Are words such as `may`, `could`, `reportedly`, `sources say`, `considering`, `threatens`, or `unconfirmed` doing important evidentiary work?
- Does the story contain a new state change or mostly interpretation of known facts?

Do not downweight severe events merely because professional reporting uses restrained language.

### Step 7: Classify the event

Assign one primary class:

- `HARD_SIGNAL`: new, specific, credible information with a clear transmission channel.
- `SOFT_SIGNAL`: credible and relevant, but incomplete, indirect, conditional, or still developing.
- `ATTENTION_SHOCK`: limited new fundamental information but high salience/dissemination.
- `UNCERTAINTY_SHOCK`: direction unclear but tail dispersion materially higher.
- `RUMOR_HAZARD`: low or medium truth confidence but enough salience to create short-horizon risk.
- `STALE_REPRINT`: old or repeated information with little new payload.
- `COMMENTARY_NOISE`: opinion, prediction, clickbait, or narrative framing with little verifiable new information.
- `IRRELEVANT`: little plausible transmission to the target index and horizon.

Allow secondary tags such as `HARD_SIGNAL + UNCERTAINTY_SHOCK`.

### Step 8: Map the event to transmission channels

Assign one or more channels from `references/calibration.md`:

- `OIL_ENERGY`
- `GEOPOLITICAL_OPERATIONAL`
- `GLOBAL_RATES`
- `GLOBAL_RISK_EQUITIES`
- `INR_FX`
- `RBI_MONETARY_LIQUIDITY`
- `BANKING_REGULATION`
- `TRADE_TARIFF_POLICY`
- `FISCAL_TAX_MARKET_STRUCTURE`
- `FLOWS_FII_DII`
- `INDEX_HEAVYWEIGHT`
- `OTHER_DOMESTIC_MACRO`

Distinguish rhetoric from operational action. A threat changes probabilities; an implemented sanction, attack, blockade, rate decision, signed rule, or physical supply disruption changes the state.

### Step 9: Apply calibrated market sensitivity

Read the target-index multiplier and regime state from `references/calibration.md`.

Do not interpret the multiplier as an expected return or a causal coefficient. It scales movement hazard conditional on the already-classified event.

For each event:

1. Determine its uncalibrated information/attention/uncertainty severity.
2. Map to one or more transmission channels.
3. Apply the index-specific sensitivity multiplier.
4. Apply interaction rules only when channels are genuinely independent and directionally aligned.
5. Convert the resulting movement hazard to the target index's empirical gap-percentile anchors.

Price reaction must never upgrade `evidence quality`, `novelty`, or `fundamental information` after the fact.

### Step 10: Aggregate multiple events without double counting

Cluster overlapping channels before combining them.

- Do not add two oil stories as two independent shocks.
- Two independent aligned broad channels may amplify movement hazard.
- Three or more independent aligned channels can create nonlinear short-gamma risk.
- Opposing channels should reduce directional conviction but may leave volatility hazard high.
- A low-credibility rumor can be low fundamental information and high attention/volatility hazard at the same time.

Use the interaction rules in `references/calibration.md`.

### Step 11: Translate to butterfly relevance

For an index butterfly, prioritize movement distribution over directional conviction.

Estimate:

- `gap_risk`: none / low / moderate / high / extreme;
- `volatility_impulse`: none / low / moderate / high / extreme;
- `directionality`: risk-on / risk-off / mixed / unknown;
- `persistence`: transient / uncertain / persistent;
- `overnight_relevance`: none / low / moderate / high / extreme;
- `index_scope`: NIFTY / BANKNIFTY / SENSEX / broad India / global spillover / sector-specific.

Use the target-index percentile anchors in `references/calibration.md` rather than arbitrary percentage cutoffs.

### Step 12: Apply the parent-skill gate

Pass an event to the parent butterfly skill when ANY is true:

- fundamental information is high;
- uncertainty/volatility hazard is high;
- attention hazard can plausibly move the underlying;
- calibrated overnight gap relevance is high;
- a credible tail-state development exists even if probability is uncertain.

Suppress or heavily downweight only when ALL are true:

- information is stale or duplicated;
- evidence is weak;
- attention potential is low;
- calibrated market relevance is low;
- no plausible transmission channel exists.

Do not issue HOLD, RECENTRE, SQUARE OFF, or trade-construction decisions. The parent butterfly skill owns those decisions.

## Standard output packet

Return a compact event table followed by one aggregate paragraph.

| Field | Output |
|---|---|
| Event | One-sentence factual description |
| Primary class | Step 7 classification |
| Fundamental information | 0-4 |
| Attention hazard | 0-4 |
| Uncertainty/volatility hazard | 0-4 |
| Evidence quality | 0-4 |
| Novelty | 0-4 |
| Sensationalism penalty | 0-3 |
| Transmission channel(s) | One or more calibrated channels |
| Sensitivity state | DORMANT / NORMAL / HIGH / STRESSED |
| Sensitivity multiplier | Target-index calibrated prior |
| Gap risk | none/low/moderate/high/extreme |
| Direction | risk-on/risk-off/mixed/unknown |
| Persistence | transient/uncertain/persistent |
| Butterfly relevance | ignore/watch/material/critical |
| Why | One or two sentences separating facts, language effects, and market sensitivity |

Then provide:

**Aggregate news state:** `CALM`, `NOISY_BUT_BENIGN`, `EVENTFUL`, `HIGH_UNCERTAINTY`, or `TAIL_RISK_ACTIVE`.

**Calibration freshness:** state the calibration as-of date and whether it is current or stale.

**Net interpretation:** state whether the news set contains genuine state-changing information, attention/noise, ambiguity, or a multi-channel movement hazard.

## Monthly calibration requirement

Treat the calibration as a rolling model, not a permanent truth.

Refresh it after each completed calendar month, preferably on the first analysis run after month-end. Use the protocol in `references/monthly-recalibration.md` with a rolling 252-trading-session window.

Persist only compact calibration parameters, sample metadata, confidence, and the as-of date. Do not bundle or retain the raw one-year article corpus or raw market dataset in the skill.

## Hard rules

- Read beyond headlines whenever possible.
- Do not treat article count as confirmation.
- Do not treat repeated wording as new information.
- Do not use generic sentiment dictionaries as the sole method.
- Do not infer truth from confident prose.
- Do not infer irrelevance from calm prose.
- Separate reported fact, source claim, journalist interpretation, and model inference.
- Attribute disputed or unverified claims.
- Treat anonymous-source claims as lower evidence quality unless independently corroborated.
- Preserve market-moving rumors as `RUMOR_HAZARD` rather than deleting them as noise.
- Use publication/event timestamps and distinguish old event time from new article time.
- For scheduled macro releases, score the surprise versus expectations, not merely the published level.
- For geopolitics, distinguish rhetoric from operational actions such as attacks, mobilization, sanctions, closures, signed orders, or confirmed policy action.
- Never train information quality on subsequent price direction.
- Never treat a market move as proof that a news claim was true.
- Never fit a stable coefficient from a tiny event sample; shrink sparse channels toward neutral sensitivity.
- Recalibrate monthly and flag calibration older than 45 days.

## References

Read `references/rubric.md` for scoring and classification rules.

Read `references/calibration.md` for current empirical parameters, regime states, percentile anchors, and interaction rules.

Read `references/monthly-recalibration.md` when refreshing the calibration.

Read `references/research-basis.md` when explaining why novelty, attention, ambiguity, and market sensitivity are separate.

Read `references/examples.md` for calibration examples.
