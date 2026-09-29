# Research basis

This skill combines established high-frequency volatility measurement results with a conservative operational short-horizon state forecast. Its live decay constants and thresholds are explicit operational priors, not claimed structural estimates.

## High-frequency spot volatility and microstructure noise

Chen, Mykland and Zhang, *Estimating spot volatility with high-frequency financial data*, Journal of Econometrics (2014), develop a nonparametric spot-volatility estimator designed for high-frequency data contaminated by market microstructure noise and relate it to two-scale realized-variance methods.

Operational implication: use dense data to estimate the **current** volatility state, but pre-average/subsample rather than naively summing every tick return.

## Continuous variation versus jumps

Barndorff-Nielsen and Shephard (2004), *Power and Bipower Variation with Stochastic Volatility and Jumps*, motivate bipower variation as a way to separate continuous quadratic variation from infrequent jumps.

Corsi, Pirino and Reno (2010), *Threshold bipower variation and the impact of jumps on volatility forecasting*, Journal of Econometrics 159(2), 276-288, show that once jumps and continuous variation are separated with threshold methods, jumps have positive forecasting content for subsequent volatility and the gains are especially relevant following jumps.

Operational implication: a recent jump should not simply be discarded as an outlier. It raises the conditional short-horizon volatility state, but it should be carried as jump pressure rather than treated as certainty of another jump.

## Jump clustering / self excitation

Recent marked-Hawkes work on high-frequency equities documents self-exciting behavior in price and variance jumps and persistent jump clusters.

Operational implication: multiple threshold jumps in a short observation block deserve a more conservative state than one isolated jump. This skill uses a decaying jump-pressure reserve instead of fitting a full Hawkes model from five minutes of data, because such a tiny sample cannot identify Hawkes parameters reliably.

## Volatility persistence

High-frequency realized-volatility research consistently documents strong volatility persistence/clustering. The skill exploits this only over a deliberately short 15-30 minute horizon: the current local variance state is projected forward with partial mean reversion toward the slower five-minute state.

The skill does not claim that five minutes can predict an entire session or overnight period.

## Implied volatility is informative but not the physical forecast

Option-implied variance contains information about future realized variance, but it is a Q-measure market price that also contains variance/jump risk premia. Carr and Wu (2009), *Variance Risk Premiums*, and Bekaert and Hoerova (2014), *The VIX, the variance premium and stock market volatility*, motivate keeping physical conditional variance separate from option-implied variance.

Operational implication: forecast P-measure RV first; compare it with IV only afterward.

## Design implication for butterflies

For the user's intraday butterfly workflow:

1. observe about five minutes of dense live futures data;
2. estimate fast and slow local continuous variance;
3. separate recent jump variation and propagate a decaying jump-pressure reserve;
4. forecast 15-30 minute integrated variance;
5. reject directional/centre migration separately;
6. apply exogenous event override separately;
7. compare the resulting physical forecast with same-horizon implied variance;
8. only then allow the butterfly engine to evaluate geometry and theta/gamma carry.
