# Research Basis for Butterfly Engine v2

Use these sources as design rationale, not as live market data.

## Option-price curvature and distributions

- Breeden, D. T. & Litzenberger, R. H. (1978), *Prices of State-Contingent Claims Implicit in Option Prices*, Journal of Business 51(4), 621-651. The second strike derivative of European call prices identifies state-contingent prices / a risk-neutral density. A finite-width butterfly is therefore naturally connected to local option-price curvature and probability mass.
- Malz, A. M. (2014), Federal Reserve Bank of New York Staff Report 677, *A Simple and Reliable Way to Compute Option-Based Risk-Neutral Distributions*. Emphasizes robust processing and no-arbitrage restrictions when extracting RNDs.
- Gatheral, J. & Jacquier, A. (2012), *Arbitrage-free SVI volatility surfaces*. Motivates explicit checks for static arbitrage rather than blindly fitting noisy IV quotes.

## Risk-neutral is not physical

- Federal Reserve research on option-implied distributions notes that risk premiums make risk-neutral probabilities differ from real-world probabilities. Treat RNDs as market-priced distributions and keep the real-world event/path overlay separate.

## Near-expiry gamma and event risk

- CME Group (2026), *The Rise of Short-Dated Options*, notes that gamma exposures require more active management as expiry approaches.
- Chan, K. F. & Gray, P. (2018), *Volatility Jumps and Macroeconomic News Announcements*, documents coincidence between scheduled announcements and volatility jumps, with asymmetric responses to surprises.
- Cboe (2026), *Trading Options Around Economic Events*, emphasizes matching option horizon to event windows and distinguishes trading direction, magnitude, or range.

## Risk systems and execution

- Cboe RiskEdge describes professional risk workflows using Greeks, P&L attribution, expiring-option/pin-risk monitoring and custom what-if scenarios. This supports a scenario-first risk layer rather than a single indicator.
- CME Group (2025), *Equity Index Options – A Quick Look at the Current State of Play*, emphasizes that liquidity is multidimensional: spread, depth, replenishment, volatility and execution mechanism all matter. This supports leg-level liquidity and slippage filters rather than OI alone.
- Cboe's Iron Butterfly benchmark/strategy material describes butterflies as range strategies with limited risk, reinforcing that centre alignment and wing geometry—not headline theta alone—define the trade.


## Regime dependence and latent jump risk

The v2.4 regime layer is motivated by time variation in volatility and jump risk rather than a claim that one fixed regime model is structurally correct. Bollerslev and Todorov (2011) document large, time-varying rare-event compensation; Broadie, Chernov and Johannes (2009) emphasize jump-risk premia in market-neutral option returns; and Zhao et al. (2024) document pronounced clustering in overnight volatility across global equity markets. Cboe historical reviews likewise show long calm realized-volatility stretches favorable to short-premium strategies followed by abrupt regime breaks.

Operational implication: classify realized/gap state and exogenous event hazard jointly with implied volatility. Low implied volatility with high external hazard is not a benign regime.

## Intraday HF physical-RV gate (v2.5)

The v2.5 intraday gate delegates short-horizon physical RV forecasting to `intraday-realized-volatility-forecast` before theta/gamma ranking. Its design is motivated by:

- Chen, Mykland and Zhang (2014), *Estimating spot volatility with high-frequency financial data*: estimate the current spot-volatility state with explicit attention to microstructure noise rather than naively using every tick.
- Corsi, Pirino and Reno (2010), *Threshold bipower variation and the impact of jumps on volatility forecasting*: separating continuous and jump variation reveals positive forecasting content of recent jumps for subsequent volatility.
- Marked-Hawkes evidence on high-frequency price/variance jumps: jump activity can self-excite and cluster, motivating a conservative decaying jump-pressure reserve rather than treating jumps as independent noise.

Operational implication: for a fresh intraday butterfly, require a dense local HF state estimate for the next 15-30 minute management horizon. Compare the resulting P-measure RV forecast with Q-measure IV only after the forecast is built, and reject the trade separately when the price/forward/RND centre is migrating.
