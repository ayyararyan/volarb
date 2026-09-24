# Research Basis

Financial news has multiple channels. Text can contain fundamental information, trigger attention and temporary price pressure, or raise uncertainty even when truth is unresolved. Market sensitivity to those channels is itself time-varying.

## Core findings

### Tetlock (2007), Journal of Finance
Paul C. Tetlock, "Giving Content to Investor Sentiment: The Role of Media in the Stock Market," Journal of Finance 62(3), 1139-1168. DOI: https://doi.org/10.1111/j.1540-6261.2007.01232.x

Media pessimism is related to price pressure and trading volume; not all media tone is new fundamental information. Keep attention/sentiment effects separate from fundamentals.

### Tetlock, Saar-Tsechansky, and Macskassy (2008), Journal of Finance
"More Than Words: Quantifying Language to Measure Firms' Fundamentals," Journal of Finance 63(3), 1437-1467. DOI: https://doi.org/10.1111/j.1540-6261.2008.01362.x

Negative language can contain information about fundamentals, especially when stories focus on concrete fundamentals. Language is not automatically noise.

### Loughran and McDonald (2011), Journal of Finance
"When Is a Liability Not a Liability? Textual Analysis, Dictionaries, and 10-Ks," Journal of Finance 66(1), 35-65. DOI: https://doi.org/10.1111/j.1540-6261.2010.01625.x

Generic dictionaries misclassify financial language. Interpret terms in financial context rather than using generic sentiment counts.

### Tetlock (2011), Review of Financial Studies
"All the News That's Fit to Reprint: Do Investors React to Stale Information?" Review of Financial Studies 24(5), 1481-1512. DOI: https://doi.org/10.1093/rfs/hhq141

Textually stale news receives smaller contemporaneous reactions, but investors can still overreact. Detect novelty separately from attention hazard.

### Engelberg and Parsons (2011), Journal of Finance
"The Causal Impact of Media in Financial Markets," Journal of Finance 66(1), 67-97. DOI: https://doi.org/10.1111/j.1540-6261.2010.01626.x

Media dissemination itself affects trading while holding the underlying information event fixed. Dissemination and salience are separate risk dimensions.

### Fang and Peress (2009), Journal of Finance
"Media Coverage and the Cross-section of Stock Returns," Journal of Finance 64(5), 2023-2052. DOI: https://doi.org/10.1111/j.1540-6261.2009.01493.x

Media coverage can affect pricing through information dissemination even when it does not create genuine new information.

### Da, Engelberg, and Gao (2011), Journal of Finance
"In Search of Attention," Journal of Finance 66(5), 1461-1499. DOI: https://doi.org/10.1111/j.1540-6261.2011.01679.x

Direct measures of investor attention predict trading and short-horizon price effects. Include attention hazard explicitly.

### Ahern and Sosyura (2015), Review of Financial Studies
"Rumor Has It: Sensationalism in Financial Media," Review of Financial Studies 28(7), 2050-2093. DOI: https://doi.org/10.1093/rfs/hhv006

Less accurate rumor stories can use more ambiguous language, while investors may still react. Score evidence, ambiguity, sensationalism, and rumor hazard separately.

### Manela and Moreira (2017), Journal of Financial Economics
"News Implied Volatility and Disaster Concerns," Journal of Financial Economics 123(1), 137-162. DOI: https://doi.org/10.1016/j.jfineco.2016.01.032

Text-based news uncertainty rises around crashes, wars, policy uncertainty, and financial crises. Model an uncertainty/tail-risk channel that is not reducible to directional sentiment.

### Gross-Klussmann and Hautsch (2011), Journal of Empirical Finance
"When Machines Read the News: Using Automated Text Analytics to Quantify High Frequency News-Implied Market Reactions," Journal of Empirical Finance 18(2), 321-340. DOI: https://doi.org/10.1016/j.jempfin.2010.11.009

High-frequency reactions differ with relevance, novelty, and direction. Relevance and novelty are first-class dimensions.

## Calibration principle

The same class of news need not produce the same market response in every regime. Oil news can be nearly irrelevant during a calm supply regime and first-order during a conflict threatening physical supply. A policy headline can be large in wording but small in market effect when fully expected.

Therefore separate:

1. information quality and factual severity;
2. attention and uncertainty;
3. transmission channel;
4. current market sensitivity to that channel.

Outcomes may calibrate items 3-4. They must never rewrite items 1-2 after the fact.

## Practical synthesis for butterflies

A short-gamma butterfly cares about movement distribution. Preserve two cases that a naive noise filter would discard:

1. Low truth confidence plus high attention: can still cause a gap or intraday jump. Use `RUMOR_HAZARD` or `ATTENTION_SHOCK`.
2. Calm wording plus high factual severity: official or wire language may be restrained even when rates, oil supply, sanctions, market plumbing, or tail risk changes materially.

The central question is: what new fact, attention shock, uncertainty shock, and calibrated transmission channel does this event inject into near-term market outcomes?
