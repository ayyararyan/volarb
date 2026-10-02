# Scientific and numerical contract (evaluator version 1)

This file freezes definitions before real-data outcomes are inspected. Synthetic
fixture outputs establish implementation behavior, not a trading edge.

## Admission and evidence

`data.qualify_dataset` is a separate read-only qualification step. It reports
PASS, DATA_LIMITED, or UNSUPPORTED plus verified capabilities, counts and reasons.
Capabilities are calculated from observations; caller-supplied labels cannot
substitute for required columns. Unknown fees, lot rules, clocks and contract
identity do not become zeros or implied passes.

| Tier | Implemented computation | Interpretation ceiling |
|---|---|---|
| F0 | Controlled session benchmarks and four-leg fixtures | Synthetic engineering evidence |
| F1 | Explicit spot/IV scenario path and Black–Scholes European marks | Model-dependent estimates; risk-neutral pricing is not a physical forecast |
| F2 | Fixed-contract option bars; or spot bars for prediction only | Bar/model execution assumptions; spot bars grant no option execution capability |
| F3 | Fixed contracts, synchronized top-of-book bids/asks, displayed size, receipt and event clocks | Quote simulation with no market-impact/queue-position claim |
| F4 | Explicit rejection | Depth/event queue replay is not implemented or advertised |

CSV, gzip CSV, JSON rows, JSONL, Parquet and ZIP CSVs are read without modifying
sources. ZIPs preferentially use consolidated `yearly/` members so monthly mirrors
are not counted again. Explicit members and member hashes may override selection.
Raw datasets never enter graph state or prompts. Source hashes bind bytes, not
market correctness.

All clocks must be offset-aware, normalized to UTC, and classified in the exchange
timezone. Start-labelled bars end after their registered duration; end-labelled
bars end at their timestamp. Availability cannot precede bar end plus registered
lag or receipt. Future exchange clocks fail qualification. Session overrides
represent dated open/close or closed sessions; default 09:15–15:30 classification
is explicitly not exchange-calendar certification. Rejected/irregular observations
remain in the qualified-source/session accounting rather than being relabelled.

Option identity requires immutable contract ID, underlying, expiry, strike,
CE/PE and positive integral lot units. ATM/WEEK/MONTH lane identifiers fail.
Identity changes for the same contract fail. Exact duplicate rows can collapse;
conflicting observation keys fail. Effective-dated lot specifications must agree
with observed units and may not be known after the decision date. The DAT adapter
can map explicitly supplied identity records and top-of-book arrays; it does not
infer missing lots or depth capacity. Non-book control messages are not fills.

## Frozen EXP-001

One origin per registered eligible session, **10:05 IST**. One-minute bars and a
**60-second availability lag** are mandatory for version 1; the timestamp label
convention must be verified, not guessed. The latest eligible bar ends 10:04
(start label 10:03). Thirty returns use 31 closes ending 09:34 through 10:04.

- Reference `S_a`: close ending 10:04.
- `RV = sum(r_j²)`, `r_j = log(S_j) − log(S_{j−1})`.
- `D = abs(sum(r_j)) / sqrt(RV)`; D=0 if RV=0.
- `M = max(abs(log(S_u/S_a)))` for all 30 closes ending 10:06 through 10:35.
- Response: `log(max(M, 1e-8))`; feature RV floor `1e-16`.
- Baseline: intercept plus log RV. Candidate: same plus D.
- Standardize using **training-only population mean and standard deviation**,
  scale floor `1e-12`. Ridge penalty **0.001** on non-intercept coefficients;
  intercept unpenalized. No grid or outcome-selected feature changes.
- Back-transform by `exp(predicted log M)` **without smearing**. Fixed numerical
  clipping is `[log(1e-8),20]`, not fitted economic winsorization.
- Control: training median of `M/sqrt(max(RV,1e-16))` times current sqrt RV.
- Primary loss: `10,000 * abs(M − prediction)`, **log-relative excursion basis
  points**. It is not rupee P&L or a tradable entry-return forecast.
- Degenerate zero-RV/zero-excursion sessions remain; no forward/back filling.
- Missing any required input/target clock yields a reason-coded session record.
  Outcome magnitude is never an exclusion criterion.

Defaults: train through 2023, diagnostics in 2024, primary later assessment
2025–August 2026. Monthly expanding refits use only complete labels available
strictly before the first evaluation origin of that month. Frozen fitting is an
explicit registered alternative. Minimum training size defaults to 30 sessions.
Fixture tests use the same splits. Historical periods are exploratory unless the
separate confirmation service establishes eligibility and access restrictions.

Independent reconstruction does not call the primary feature/model helpers. It
uses scalar returns/excursions, independently selects training rows, solves an
augmented ridge least-squares problem, and recomputes original-scale losses.
Tolerances: max feature error 1e-8, prediction error 1e-7, loss error 1e-3 bp.
This establishes computational replication on the same market sample, not new
market evidence.

## Baselines

- **B0-simple:** deliberately new one-lot research control, nearest observable
  spot body, nearest eligible expiry, symmetric common-distance protective wings rounded outward to a
  registered minimum width, 30-minute hold clipped at 15:00, no re-entry/recenter.
  It is not described as the user's existing trading strategy.
- **B-policy:** explicit research interpretation of first-terminal data/deadline, loss,
  candidate session-VRP and fresh re-entry, intraday-RV/drift, event/tail/liquidity,
  expiry, recenter-transition margin, and optimizer/entry-margin gates. Missing
  packets block admission. It retains the 15:00 deadline, INR1,000 loss policy
  and INR1,000 reserve. These are rules, not realized-loss guarantees. It is
  separately versioned and tested; it does not silently alter observed defaults.
- **B-as-observed:** executes the byte-identical v2.6 controller snapshot
  `observed_controller_v26.py`, copied from
  `skill/butterfly-market-outlook/scripts/decision_controller.py` at repository
  commit `98cdabea49ca45aa237b51ebe8865351c20d3125`. SHA256
  `d3926a533babca53d022d2b3422fe5cd835e1962c29eb1f01e759b27eb239597`.
  The only substitution is an explicitly supplied frozen decision clock for
  margin freshness. Gate ordering, defaults and missing-loss permissiveness are
  preserved. Inputs are normalized dated research packets; missing historical
  gates are not invented. The live wrapper is never invoked.

Golden fixtures distinguish the three, including observed missing-loss HOLD,
policy missing-loss BLOCKED, loss/reserve boundaries and the intraday deadline.
Frozen source is excluded from automatic formatting to preserve its byte hash.

Non-B0 simulations require dated policy packets and recorded selected legs. They
never silently reuse B0's ATM/width selector. Each `metadata.policy_packets[date]`
entry has a packet-level `available_at` no later than the decision and includes
`entry_selection` (and `recenter_selection` for that comparison):
`selection_policy_id`, offset-aware `available_at`, and four `legs`, each with
`contract_id` and `signed_lots` equal to +1 or -1. Selected contracts must resolve
in the admitted chain with valid geometry and effective lot specifications.
The record freezes which optimizer/overlay selection actually governed the
decision; the evaluator does not choose retrospectively between their widths.
Missing gate packets, missing selection records or future-available selections
are DATA_LIMITED, not zero-P&L opportunities. A complete actual selection record
is necessary before an observed baseline can receive an economic estimate.
Registered hold/close/recenter counterfactuals are separate management policies;
they are not advertised as a replay of every historical live intervention.

## Four-leg execution and accounting

Exactly four contracts, one underlying/expiry: long lower put, short body put,
short body call, long upper call, matched signed units. Lots convert to units
once at construction. Every fill records units, price, INR fees, cycle ID,
decision reason, cash flow and clock:

`cashflow = −signed_units * price − fees`.

Liquidation equity adds long units at bids and short units at asks to cumulative
cash. Premium receipt alone is never profit. Closed P&L requires zero inventory.
Independent decimal accounting rebuilds cash and signed positions from primitive
fills and rejects a reported closed result with remaining exposure.

Entry buys protective wings before shorts; exit buys back shorts before selling
wings. Latency and per-leg spacing advance to the first eligible later observation
within the declared wait bound. They do not retroactively fill old quotes. Size
is consumed per security/observation/side, so repeated simulated fills cannot
reuse identical displayed liquidity. Partial fills stop the leg sequence; a
partial entry is unwound at subsequent observations, retaining its costs and
exposure. Missing unwind/close remains unresolved. This is deterministic partial
fill simulation, not an empirical claim about broker order matching.

F2 requires `bar_fill=available_close_adverse_spread`, explicit assumed spread
and size. Bars are admitted only after their availability time; the resulting
close-mark fills are **model-based bar estimates**, not observed executions.
Intrabar threshold ordering is not inferred. F1 likewise requires explicit
contracts, scenario spot/IV, rate, spread/size assumptions and dated costs.

Fees are effective-dated, separately specifying brokerage, exchange, regulatory,
GST, sell tax and buy stamp; optional exercise tax requires an explicit field.
Rounding is decimal half-up to paise. Fixture fee schedules are intentionally
simplified, never represented as historical Indian charge schedules.

Capital and peak margin/proxy must be provided and labelled. Maximum expiry loss
is never used as broker margin. Entry purchases cannot exceed available cash
after reserve; cumulative closed results affect subsequent admission. Overlapping
opportunities are retained as rejected, not leveraged without bound. An unresolved
position blocks subsequent entries rather than pretending the account is flat.

Hold, close and a single sequential close/reopen recenter comparison start from
the same observable state and opportunity IDs. Recenter retains the original
cycle ID, old losses, close fees, new entry fees and final close costs. Historical
lot rules are revalidated for replacement contracts. Holding marks replay cash
and inventory at observed clocks; missing liquidation quotes are null with
reasons. All fill, holding, opportunity and exclusion artifacts are preserved.

If **any paired opportunity has an unresolved exit**, aggregate paired inference
is withheld as DATA_LIMITED. No favourable complete-case mean is silently
substituted. Diagnostic closed observations remain in the artifacts.

## Inference and registered robustness

Unit of inference is the session: candidate-minus-baseline net INR P&L, or
baseline-minus-candidate forecast loss. Filtering rejects keep zero allocation
in the opportunity set. Relative forecast improvement divides mean paired loss
improvement by mean baseline loss; zero/nonpositive denominator is inconclusive.

Circular moving-block bootstrap, seeded, defaults to length5 and999 draws.
Percentile intervals and a null-centered one-sided test address the registered
practical hurdle (EXP001 default1% relative MAE). Default robustness uses block
lengths1,5,10. Requirements include the registered minimum sample size and at least
four effective blocks/20 sessions; insufficient precision cannot reject a claim
merely because significance is absent. Upper interval below the practical hurdle
supports an informative negative; lower above supports exploratory improvement.
Blocks cannot manufacture absent crises or remove structural breaks.

Four-leg checks include adverse extra INR1/5 per fill. Their economics remain
inside the reserved external job, not unregistered graph-node computation.
Holm family correction is implemented for the protected batch. Development
post-selection intervals remain descriptive. This release independently reconstructs
every admitted numerical result, including every negative result (stronger than a
sampled audit). The tested negative-sampling utility uses sorted IDs and a frozen
seed/fraction for future larger campaigns; it does not currently reduce replication.

Controlled benchmarks are deterministic seeded session panels with known effect
and noise. Synthetic demonstrations, regardless of significance, cannot become
independently supported historical findings. Poor economics returns a terminal
finding; it does not enter an implementation-repair optimization loop.

## Numerical acceptance evidence

Run `pytest tests/test_data.py tests/test_accounting.py tests/test_baselines.py
tests/test_statistics.py tests/test_evaluators.py tests/test_replication.py` from
`agent/`. Tests cover adapters, identity/clock conflicts, immutable source,
temporal perturbations, training membership, degenerate observations, missing
targets/exits, lot/fee transitions, bid/ask signs, latency, capital/overlap,
partial protective fills, all implemented fidelity paths, full recenter costs,
independent reconstruction, planted/null results and deterministic repeats.


### Release hardening

A B0 strike grid without a common symmetric wing distance is rejected rather than
silently converted into an asymmetric structure. B-policy requires session-loss
evidence for new entries as well as held positions; B-as-observed retains the
original permissive behavior for faithful comparison. This distinction is explicit.
When EXP001 has missing eligible sessions, the evidence layer caps its conclusion at
INCONCLUSIVE even if complete-case descriptive estimates look favorable. The entire
eligibility ledger remains available for a new preregistered missingness investigation.
