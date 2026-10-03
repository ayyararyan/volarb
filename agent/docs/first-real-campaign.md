# First real-data research program — 3 October 2026

This program uses existing local historical observations, not synthetic prices.
It does not authorize trading. All history is previously exposed and all findings
are exploratory. Original data, full source paths and numerical artifacts remain
in the private local runtime. See [discovery](real-data-discovery.md) and
[capabilities](real-data-capabilities.md).

## Pre-result research contract

The spot smoke tests the existing EXP-001 question: does adding normalized,
past-only directional displacement to realized variance improve prediction of
the next 30-minute excursion? The baseline uses realized variance; the candidate
adds drift. A frozen ten-session January training sample precedes ten January
diagnostic sessions and eighteen available February assessment sessions. The
practical relative-MAE improvement is 1%; minimum inference sample is 30 sessions.
No model was refit after observing the economic result.

Options tests compare fixed 10:00 one-lot B0-simple entries, holding for 30 minutes
versus closing after a registered shorter horizon. Entry spot is a fixed
construction input, not a dynamic underlying feed. Only supported widths and
review times may be evaluated. Recentring and alternative entries are rejected
both at admission and inside protected numerical evaluation. The pre-result
practical hurdle is INR50 candidate-minus-baseline net P&L per session.

The options estimand concerns a captured-feed, fail-closed allocation policy.
Contract selection uses the captured file universe, not a verified complete
point-in-time exchange listing. Missing entry data means no allocation under that
policy; its zero must not be interpreted as an observed zero market return.
Unresolved inventory cannot be converted to a profitable or zero outcome.

## Completed spot smoke

| Field | Result |
|---|---|
| Campaign | `real-spot-smoke-20261003-001` |
| Dataset | `local-nifty-ticks-minute-20260102-v1` |
| Run | `run-51ce7394ab5a1b5c361c2b65f03082d4` — INGESTED |
| Fidelity | F2, identified historical index bars |
| Coverage | January–February 2026; 38 observed / 41 official sessions; v1 catalog originally 39 |
| Assessment | 18 / 21 official February sessions; v1 catalog originally 19 |
| Baseline / candidate MAE | 6.4229 / 7.6330 excursion basis points |
| Relative MAE improvement | −18.8404% (point estimate deteriorates) |
| Primary descriptive block-5 interval | [−36.7804%, −2.5905%] |
| Registered outcome | **INCONCLUSIVE**, insufficient precision |
| Robustness | Block lengths 1, 5, 10; 999 resamples each; estimate sign stable |
| Independent reconstruction | PASS; maximum loss discrepancy 6.04e-14 bp |
| Codex | 8 real subscription calls, `gpt-6-astra`; 85,829 input / 6,054 output tokens |
| Numerical resources | 1.3954 CPU seconds; 1.6882 wall seconds; 53,357 artifact bytes |
| Workflow | Live design, specification, REVISE → changed specification → ADMIT, worker, reconstruction, grading, synthesis and steward completed |

The negative point estimate is useful counter-evidence to the proposed drift
benefit, not a powered rejection. The block-1 interval crosses zero. Eighteen
assessment sessions are below the registered minimum of thirty; no favourable
interval may override that gate. This is spot prediction, not butterfly P&L.

The original manifest's catalog denominator remains preserved in evidence. A later official
calendar audit identifies 41 scheduled sessions and two entirely absent source
directories, February 1 (Budget trading) and February 10. Corrected source coverage
is 38/41 overall and 18/21 in February. The original finding is not overwritten;
missing event-day observations are an additional limitation, not imputed data.

The first immutable result contains an inaccurate descriptive `refitting` string
("expanding monthly"). Its accepted specification, actual implementation and
independent reconstruction all used frozen training. A subsequent metadata-only
fix makes this label conditional on the registered split; the original result
and its evaluator hash are preserved, and economics were not rerun or changed.

## Options accounting smoke and bounded campaign

Results are recorded here only after their live workflow and numerical evidence
complete. The registered program is bounded at two twelve-hypothesis waves, with
six supported hold-versus-close comparisons across two fixed wing widths. The
other questions remain explicitly capability-limited rather than being silently
translated into a different executable strategy. There is no winner-only report
or result-conditioned specification revision.

The first options preparation (`real-options-smoke-20261003-001`) ended
`UNSUPPORTED_HYPOTHESIS` at its two-revision limit, with **zero numerical jobs**.
Its bounded reviewer context did not supply exact registered cost coefficients,
cost-stress semantics or the fact that the iron evaluator does not use SplitPlan.
Nine live calls and the terminal synthesis/steward record remain in the registry.
A source-brief-only retry preserves the same hypothesis, quote bytes, parameters,
family and parent lineage; it does not reset search history or optimize an outcome.

### Preserved first fixed-contract accounting smoke (pre-IPFT correction)

The bounded retry `real-options-smoke-20261003-002` received ADMIT and completed
the normal numerical, replication, synthesis and steward workflow. It reused the
first accepted hypothesis with explicit parent lineage instead of buying another
designer call. Run `run-bf388fbdf38abb916098dca858246fb2` is INGESTED.

| Policy | Gross cashflows | Modelled charges | Net INR P&L | Fills / final inventory |
|---|---:|---:|---:|---|
| Hold 30 minutes | 61.75 | 211.04 | −149.29 | 8 / flat |
| Close 15 minutes | −6.50 | 211.20 | −217.70 | 8 / flat |

These first fees omit IPFT and are retained only as superseded audit evidence.
The corrected v3 results below are authoritative for reported economics.
The original paired difference is −INR68.41 on January 2. Both policies share the same
fixed four-contract entry, one historical 65-unit lot and 200-point wings. Entry
fills occur sequentially at 10:00:01–04 IST; respective exits at 10:15:01–04 and
10:30:01–04. No rejected entry, unresolved exit or artificial zero allocation
contributes to this smoke.

Independent operator reconstruction checked all sixteen fills, exact contract
identity, recorded bid/ask sides and sizes, dated lots, component charges, rounded
fees, protective ordering, cash flows and 248 inventory/cash path observations:
**PASS, zero disagreements**. Full per-leg prices and source rows stay private.
The worker's separate Decimal reconstruction also passes.

The registered outcome is **F3, independently reconstructed, INCONCLUSIVE**:
one observed session is not economic precision. Block robustness and registered
cost sensitivity completed. The existing cost sensitivity subtracts INR1/5 per
candidate fill from its total, yielding −INR225.70 / −INR257.70; it does **not**
stress the baseline or establish relative-policy superiority under stressed costs.
Zero added slippage still crosses observed bid/ask; actual queue position, impact
and broker contract-note charges are not established.

This retry used five live Codex calls (52,071 input / 3,638 output tokens), 0.798
numerical CPU seconds and 1.078 worker wall seconds. Together with the preserved
blocked preparation, the options smoke consumed fourteen calls, not five.

### Dated-charge correction and authoritative smoke

The final source audit found an omitted NSE IPFT contribution. The January–February
schedule must use combined exchange/IPFT premium rate **0.0003553**, not 0.0003503.
SEBI is separate; GST applies to these service charges and modelled brokerage.
See the dated [cost sources](real-data-capabilities.md#clock-and-cost-provenance).
This is an external fee-data correction, not a response to weak performance.
New v3 manifests bind identical quote bytes, calendars and policies. Original
manifests, findings and failed preparation attempts remain immutable.

`real-options-cost-smoke-20261003-001` completed the real provider workflow.
Run `run-e95544dc2cb57c9bedc44457f524c2de` is the corrected accounting smoke:

| Policy | Gross INR | Corrected modelled charges | Net INR | Inventory |
|---|---:|---:|---:|---|
| Hold 30 | 61.75 | 211.18 | −149.43 | Flat |
| Close 15 | −6.50 | 211.34 | −217.84 | Flat |

The corrected difference remains −INR68.41; **F3 INCONCLUSIVE, n=1**. Independent
operator reduction reconciles all 16 fills and 248 cash/inventory checks with zero
disagreements. The same bid/ask sides, quantities, lot65, chronology and paired
entry remain fixed. Gross positive hold cashflow becomes negative after charges;
this one accounting example is not an estimate of a durable economic edge.

## Bounded first campaign

The falsifiable mechanism is that earlier closure avoids further short-gamma/path
exposure but forfeits theta. Improvement requires avoided losses to exceed
forgone carry and registered friction by INR50 per decision session. The principal
alternatives are subsequent theta, bid/ask costs, quote capture and fill timing;
without a dynamic underlying path, no gamma-related causal attribution is made.

Two finite waves generated twelve hypotheses each using the live Codex designer:
`real-options-wave1-20261003-001` (200-point wings) and
`real-options-wave2-20261003-001` (500-point wings). Both completed synthesis and
steward review. All 24 are in the registry and research memory, including the
18 capability-limited questions. No protected confirmation was accessed.

| Program field | Result |
|---|---|
| Instrument / period | NIFTY, January 1–February 27, 2026 |
| Fidelity | F3 historical captured-feed quote simulation |
| Hypotheses generated | 24; two live designer calls |
| Admitted economic comparisons | 6: widths200/500 × close10/15/20 versus hold30 |
| Capability-limited before economics | 18 |
| Original numerical comparisons | 6 runs; one additional technical worker attempt |
| Original findings | 2 REJECTED_FINDING; 22 DATA_LIMITED (18 capability + 4 incomplete exits) |
| Supported / inconclusive program findings | 0 / 0; smoke outcomes reported separately |
| Original campaign Codex calls | 20, `gpt-6-astra` via ChatGPT subscription |
| Expansion to a larger search | Not launched: incomplete exits and missing capabilities remain |

The conditional-entry questions need joined past-only RV/drift/range/gap/trend
states and an executable eligibility policy. Other blocked questions need verified
IV/skew/term surfaces, matched expiry opportunities, threshold exits, event records
or exact margin. Presence of spot bars alone does not implement those contracts.
The blocked hypotheses were not translated into unrequested generic strategies.

### Corrected complete comparisons

| Fixed wings | Completed paired cycles / calendar decisions | Hold30 mean INR | Close10 mean INR | Paired effect INR | Descriptive block5 interval | Result |
|---|---:|---:|---:|---:|---|---|
| 200 points | 34 / 41 | −242.28 | −278.98 | −36.70 | [−92.11, 9.92] | REJECTED_FINDING versus +50 hurdle |
| 500 points | 21 / 41 | −120.94 | −177.44 | −56.50 | [−132.66, 16.11] | REJECTED_FINDING versus +50 hurdle |

These means use all registered allocation decisions, not only filled cycles.
The remaining 7 / 20 decisions are ineligible no-allocations. The upper interval
bounds are below the registered +INR50 hurdle but **both intervals include zero**.
Thus the precise practical-improvement prediction is rejected under this
captured-feed policy; universal economic inferiority is not established.
The 500-point result has only 21 actually executed paired cycles despite 41
calendar decisions. It is not 41 complete market observations or powered evidence
about a fully observed opportunity population. Do not rank widths by these means:
quote eligibility produces different executed samples.

Block lengths1/5/10 with999 resamples retain the rejected hurdle result and
negative point estimates. Candidate-only INR1/5-per-fill stress is a sensitivity
check, not paired-policy friction robustness. Both successful corrected findings
are F3 / verified / exposed_temporal / independently_reconstructed; their
informative precision tag is conditional on the registered allocation estimand,
not broader market coverage or familywise confirmation.

Authoritative cost-repair campaigns are
`real-options-cost-repair-w200-20261003-003` and
`real-options-cost-repair-w500-20261003-001`. Runs are respectively
`run-ca48e4570cad8acd50720c7b39a2ab84` and
`run-e739780d1ebe96f0fdd10113ea6cfac5`. No original result is overwritten.

### Unresolved exits are not negative strategy results

All four close15/20 comparisons reach an unresolved exit on February23. The first
required call quote at the close15 window has a feed timestamp 57 seconds before
availability; at close20 it is 72 seconds. Receipt/component freshness does not
repair stale feed timing. No eligible replacement appears within the registered
60-second fill wait and 5-second quote-age constraint. An incomplete position
also prevents later opportunities from being treated as fresh flat entries.

The evaluator correctly withholds aggregate P&L and inference. No complete-case
subset, favourable later price, erased session or relaxed freshness rule is used.
A separate independent fee-only audit of 1,632 recorded fills confirms the IPFT
correction cannot supply missing exits or bind the ample declared capital proxy;
its conservative residual cushions exceed INR666,000. These audits are not new
strategy tests, and corrected aggregate P&L is deliberately **not** reported for
unclosed positions. Worker primitive cash/inventory reductions pass, but these
findings retain **insufficient precision / absent inferential replication**.

### Interpretation constraints

The estimand includes 41 registered calendar allocation decisions, including
zero allocations when captured entry data fail. Quote-bearing sessions, completed
paired cycles and calendar decisions are different denominators. Missing the
February1 Budget session particularly limits event-risk interpretation. Neither
zero allocation nor an unclosed position is an observed zero market return.

The six parameter combinations share one preserved search family. All intervals
are exploratory per-comparison, not familywise-adjusted confirmation. Prior
exposure is explicit; these are neither causal estimates nor independently
sourced market replications. Reconstructing primitive accounting cannot certify
exchange clocks, quote executability, queue priority or realistic market impact.

No recentering, winner-conditioned parameter tuning or trading deployment follows.
The next justified work is to resolve source timing/completeness and qualify
past-only state joins, then preregister conditional economics against this fixed
baseline. The richer BANKNIFTY bar archive also needs bar-label and dated-lot
qualification before it can expand the sample.

### Preserved technical failures and search lineage

The first 200-point fee-repair preparation exhausted its two-revision bound because
its source brief named the parent hypothesis/finding but did not explicitly bind
the original executable experiment and trial. It starts no numerical job and
remains UNSUPPORTED_HYPOTHESIS. An immutable mapping now names original and child
experiment/trial IDs and the unchanged family; both trials remain counted.
A separate retry-input campaign-ID mismatch was rejected before any model call.
Its failed checkpoint and both CLI invocations are retained; a fresh correctly
bound campaign is used, not a rewritten checkpoint. No scientific gate is relaxed.

One original numerical worker died before publishing its result. The existing
recovery protocol retried the same registered run; original attempt evidence is
preserved. Successful-attempt CPU is measured; the failed attempt's CPU is unknown,
not zero. Subsequent work uses one explicitly bounded shared worker supervisor.
All prior source-build failures and parser retries remain private evidence and
are not miscounted as new economic experiments.

## Complete usage and verification record

The [machine-readable aggregate receipts](evidence/first-real-campaign.json) bind
campaigns, findings, immutable result hashes, metrics, uncertainty, robustness,
resource meters and typed evidence grades. They contain no private source paths,
raw quotes, per-fill market prices, runtime databases or authentication material.

| Whole-task accounting | Observed total |
|---|---:|
| Live Codex calls | 65, all accepted; model `gpt-6-astra`, subscription authentication |
| Input / output tokens | 749,764 / 69,032 |
| Sum of call wall durations | 3,177.13 seconds; concurrent durations are not task elapsed time |
| Registered hypothesis/trial records | 31, including original/reused smoke and explicit cost-repair lineage |
| Real numerical runs / attempts | 11 ingested / 12 attempts; one failed worker attempt |
| Successful numerical CPU / wall | 369.41 / 372.61 seconds |
| Failed worker elapsed / CPU | 85.47 seconds / unknown, not zero |
| Successful numerical artifacts | 1,139,349 bytes |
| Actual peak numerical attempt concurrency | 1; configured ceilings at most2 |
| Sum first-dispatch waits | 666.04 seconds, including deliberate batching; not a utilization benchmark |
| Active jobs or model calls at completion | 0 / 0 |
| Finding-linked memory / additional fee diagnostics | 31 / 4 |
| Operator corrected-options checks | 896 fills; 20,054 cash/inventory checks; PASS, no disagreements |
| Local tests | 413 passed; source unchanged during checks |
| Other local verification | Ruff, formatting, uncached mypy, config/doctor, both offline demos, 15 schemas |

Original two-wave economics account for20 calls and6 runs. Fee repair adds two
complete economic reruns; the accounting smoke also has its own corrected rerun.
The65-call total includes both bounded preparation blocks, smoke work and every
cost-repair call, rather than counting only successful final paths. A preflight
input failure made zero model calls and ran no numerical job. One failed campaign
checkpoint is explicitly PREFLIGHT_FAILED; all nine model-driven campaigns have
terminal synthesis/steward reports. Offline CI fixtures are not real-data runs.

Runtime and derivations occupy approximately386MiB locally, of which the main
registry/artifact runtime is about25MiB; these are approximate filesystem
allocations, not source archive size or metered acquisition. No market data were
acquired or originals altered. Full inventories, hashes, manifests, source-build
logs, reconciliation rows and private reports remain in the local task runtime.
An immutable operating catalog selects the six active dataset manifests and
explicit cost-supersession map; prior versions are retained, not silently reused.

All code changes are confined to `agent/`: read-only data adapters and builders,
fixed-scope enforcement, explicit calendar input, correctly dated costs and
pre-critique resource limits. The research architecture, numerical safeguards
and operational trading system were not replaced. Source and sanitized findings
are published through [PR #5](https://github.com/ayyararyan/volarb/pull/5).
