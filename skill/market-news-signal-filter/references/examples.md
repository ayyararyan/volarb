# Calibration Examples

## Example 1: Dramatic headline, weak new information

Headline: "Markets face historic collapse as war fears explode"
Body: repeats yesterday's confirmed diplomatic dispute, cites no new military action or sanctions, and mainly quotes strategists.

Classification:
- Fundamental information: 0-1
- Attention hazard: 2-3 depending on dissemination
- Uncertainty hazard: 1-2
- Sensationalism penalty: 3
- Primary class: STALE_REPRINT or COMMENTARY_NOISE

Do not apply a geopolitical structural multiplier as if a new operational event occurred. If futures or volatility react, preserve an attention overlay.

## Example 2: Calm official wording, major state change

An official notice immediately closes a major shipping route and gives precise geography and duration.

Classification:
- Fundamental information: 4
- Evidence quality: 4
- Novelty: 4
- Uncertainty hazard: 4
- Channel: OIL_ENERGY + GEOPOLITICAL_OPERATIONAL
- Primary class: HARD_SIGNAL + UNCERTAINTY_SHOCK

Apply the calibrated oil/geopolitical sensitivity and interaction rule. Calm prose does not reduce severity.

## Example 3: Expected Fed move

The Federal Reserve changes rates exactly as consensus expected and its guidance is close to priced expectations.

Classification:
- Evidence quality: 4
- Novelty: 2-3 as a formal state change
- Fundamental information: 1-2 after surprise adjustment
- Channel: GLOBAL_RATES
- Market hazard: usually moderate unless guidance, yields, dollar, or global equities reveal a genuine surprise

A scheduled official event can be factually important and still have limited incremental market information.

## Example 4: Hard trade-policy resolution

India and a major trading partner announce a signed deal resolving a previously material tariff uncertainty.

Classification:
- Evidence: 4
- Novelty: 4
- Fundamental: 4
- Channel: TRADE_TARIFF_POLICY
- Primary class: HARD_SIGNAL

The current calibration assigns high sensitivity because hard trade-policy resolution produced tail-scale opening gaps during the calibration year. Do not extend that response mechanically to vague negotiating rhetoric.

## Example 5: Anonymous but credible policy report

A top financial wire cites two officials saying a central bank is considering an emergency liquidity measure. No official release exists yet; another independent outlet partially corroborates.

Classification:
- Evidence: 2-3
- Novelty: 4
- Fundamental: 2-3
- Attention: 3
- Uncertainty: 3-4
- Primary class: SOFT_SIGNAL + UNCERTAINTY_SHOCK

Map to the appropriate policy/liquidity channel but discount for evidentiary uncertainty.

## Example 6: Viral unverified geopolitical rumor

A social-media post claims an attack. Major outlets cannot verify it. Crude and index futures jump.

Classification:
- Evidence: 0-1
- Fundamental: 0-1
- Attention: 4
- Uncertainty: 4
- Channel: GEOPOLITICAL_OPERATIONAL only as a possible channel, not a confirmed event
- Primary class: RUMOR_HAZARD

Do not apply the full hard-signal geopolitical multiplier. Preserve high attention and volatility hazard because short-gamma risk is real.

## Example 7: Ten outlets, one wire origin

Ten websites publish nearly identical reports, all tracing to one Reuters dispatch.

Classification:
- Independent confirmation: 1
- Article count: irrelevant to confirmation
- Novelty: score the originating factual payload once
- Dissemination: may increase attention hazard

Syndication is dissemination, not independent evidence.

## Example 8: Scheduled inflation release

Headline: "Inflation rises to 4.8%"
Consensus: 5.1%; prior: 4.9%.

The relevant news is softer-than-expected inflation despite a small rise versus prior. Evaluate rates, FX, and equities through surprise rather than raw wording.

## Example 9: Threat versus operational action

Story A: a political leader threatens tariffs without dates or signed orders.
Story B: customs authority publishes a signed tariff schedule effective tomorrow.

Story A: SOFT_SIGNAL or UNCERTAINTY_SHOCK.
Story B: HARD_SIGNAL.

The trade-policy sensitivity multiplier is much more appropriate for Story B.

## Example 10: Multi-channel overnight shock

Overnight developments include a confirmed crude-supply shock, a hawkish US rates repricing, weak global equities, and a new domestic financial-sector rule.

Procedure:
1. Cluster duplicates.
2. Score each event independently.
3. Map channels: OIL_ENERGY, GLOBAL_RATES, GLOBAL_RISK_EQUITIES, BANKING_REGULATION.
4. Apply index-specific multipliers.
5. Apply the aligned multi-channel interaction once, not once per article.
6. Keep directional confidence separate from movement hazard.

For BANKNIFTY, domestic financial regulation can raise the final hazard more than for NIFTY/SENSEX.
