# News Signal Rubric

## 1. Evidence quality (0-4)

- 4 - Primary/verified: official release, regulator/exchange filing, direct official statement, court document, or multiple independent high-quality confirmations.
- 3 - Strong professional reporting: reputable wire/specialist newsroom with named evidence or highly specific sourcing; no material contradiction.
- 2 - Plausible but incomplete: reputable outlet relying on anonymous sources, partial confirmation, or a claim still being verified.
- 1 - Weak: single secondary outlet, unattributed assertion, aggregation, partisan/advocacy framing, or no traceable evidence.
- 0 - Unsupported: speculation, social-media rumor with no credible provenance, fabricated-looking content, or materially contradicted claim.

Judge the sourcing of the specific claim, not the brand name alone.

## 2. Novelty (0-4)

- 4: genuinely new event/state change not in prior coverage.
- 3: meaningful new detail changing probability, magnitude, timing, or scope.
- 2: useful update but mostly continuation of a known story.
- 1: rephrasing/repackaging of known information.
- 0: duplicate, reprint, retrospective commentary, or old event presented as new.

Novelty concerns factual payload, not publication timestamp alone.

## 3. Independent confirmation (0-4)

- 4: primary source plus multiple independent outlets, or several independent first-hand confirmations.
- 3: two genuinely independent credible confirmations.
- 2: one credible origin plus secondary reporting that adds verification.
- 1: many copies trace back to one origin.
- 0: one unsupported origin or circular citation.

## 4. Factual specificity (0-4)

- 4: concrete action, number, date, location, decision, and named actor.
- 3: clear event with one or two unresolved details.
- 2: general claim but identifiable event.
- 1: vague direction, prediction, or broad characterization.
- 0: rhetoric/opinion without verifiable new fact.

## 5. Ambiguity and hedging (0-4)

This measures uncertainty about what the claim actually establishes.

- 0: unambiguous confirmed fact.
- 1: minor caveat.
- 2: conditional/proposed/developing.
- 3: heavy use of may/could/reportedly/sources say/considering/threatens.
- 4: conflicting reports, unclear actor/action, unverifiable rumor, or material unknowns.

High ambiguity can lower fundamental confidence while raising volatility hazard.

## 6. Linguistic intensity (0-4)

Judge wording, not event severity.

- 0: neutral technical language.
- 1: mildly evaluative.
- 2: clearly negative/positive or urgent.
- 3: strongly emotive, dramatic, superlative, or crisis framing.
- 4: extreme alarmism, absolutes, catastrophe framing, or highly charged rhetoric.

## 7. Sensationalism penalty (0-3)

- 0: headline and body are proportionate; factual framing dominates.
- 1: mild exaggeration or attention-seeking framing.
- 2: headline materially overstates body or uses dramatic wording unsupported by detail.
- 3: clickbait/rumor packaging dominates; factual payload is thin.

Apply this penalty to information interpretation, not automatically to attention hazard.

## 8. Market relevance (0-4)

For Indian index butterfly use:

- 4: direct India-wide/index-heavyweight/RBI/SEBI/exchange/major banking/liquidity event, or global shock with immediate broad risk transmission.
- 3: strong transmission through oil, INR, US rates, global equity futures, major geopolitics, tariffs/sanctions, or large index constituents.
- 2: sector event with plausible index spillover or medium-horizon macro relevance.
- 1: weak/indirect connection.
- 0: no plausible connection to target index/horizon.

## 9. Attention hazard (0-4)

- 4: dominant breaking story, broad cross-outlet coverage, high emotional salience, likely to trigger discretionary/retail/systematic attention.
- 3: widely covered and market-facing.
- 2: noticeable but contained.
- 1: niche.
- 0: essentially no market audience.

## 10. Uncertainty/volatility hazard (0-4)

- 4: materially expands tail states or creates immediate binary/unknown outcomes with large gap potential.
- 3: meaningful uncertainty shock with plausible broad-market volatility.
- 2: moderate uncertainty increase.
- 1: small uncertainty increment.
- 0: resolves uncertainty or is immaterial.

## 11. Fundamental information (0-4)

Judge the combination of novelty, evidence, specificity, and market relevance.

- 4: credible new state-changing fact with direct transmission.
- 3: credible meaningful update.
- 2: partial/conditional information.
- 1: weak incremental information.
- 0: no meaningful new information.

Do not calculate this as a blind arithmetic average.

## Classification logic

### HARD_SIGNAL
Normally require evidence >=3, novelty >=3, factual specificity >=3, and market relevance >=2.

### SOFT_SIGNAL
Use when evidence is credible but novelty, specificity, directness, or completion is moderate.

### ATTENTION_SHOCK
Use when attention hazard >=3 while fundamental information <=2.

### UNCERTAINTY_SHOCK
Use when uncertainty/volatility hazard >=3 and direction remains mixed/unknown or factual outcome is unresolved.

### RUMOR_HAZARD
Use when evidence <=2 but attention hazard >=3 or gap risk is high. Never promote rumor to confirmed fact.

### STALE_REPRINT
Use when novelty <=1 and there is no meaningful new fact. It may still carry an ATTENTION_SHOCK secondary tag.

### COMMENTARY_NOISE
Use when specificity <=1, novelty <=1, and the article is primarily prediction/opinion/framing.

### IRRELEVANT
Use when market relevance =0 or the horizon mismatch makes it unusable.

## Butterfly relevance gate

### CRITICAL
Any credible event with extreme calibrated gap risk; uncertainty hazard 4; or a direct overnight state change with broad index impact.

### MATERIAL
A hard signal with market relevance >=3; or attention/uncertainty hazard >=3 with plausible immediate movement.

### WATCH
A developing soft signal, rumor hazard, or medium-relevance event that could become material with confirmation.

### IGNORE
Stale/duplicate/commentary with low attention, low uncertainty, and low calibrated relevance.

## Market-confirmation overlay

If live market data are available, use them as an overlay, not proof of truth:

- index futures gap/return;
- VIX/implied-volatility jump;
- INR, crude oil, US yields, global equity futures;
- option skew or put demand;
- unusual volume/breadth.

Market reaction can confirm salience and update channel sensitivity. It cannot prove the factual claim.
