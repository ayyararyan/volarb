# Live research lifecycle and methodological review

This is a research-only lifecycle. Synthetic acceptance evidence verifies the
software orchestration, not butterfly profitability or historical strategy edge.

## Root cause of the previous live stop

The source audit began from `main` at
`c59bfc858636f2c6ce571848fd23cd03b7b84c0f`. The local campaign
`codex-live-workflow-health-20261002-001` made five valid subscription-backed
Codex calls, in the order designer → critic → specification → steward → synthesis.
Its critic returned **REVISE**, not UNSUPPORTED. No numerical job was submitted.

The actual critic request was `{campaign_id, hypothesis, capabilities}` plus
the role profile. `hypothesis` was the full HypothesisSpec, including its proposed
DSL, but not the specification agent's output or a constructed ExperimentSpec.
The graph then constructed that experiment and mapped both REVISE and UNSUPPORTED
to UNSUPPORTED_HYPOTHESIS. This was an information-flow and transition defect,
not evidence that the model could not return valid structured output.

| Review input | Previously available to the critic |
|---|---|
| Complete hypothesis, mechanism, horizon, outcome, risks, alternatives | Yes |
| Declared baseline/comparison, primary metric, practical effect | Yes, hypothesis declarations only |
| Proposed DSL, search allocation, parameter domain | Yes, designer proposal only |
| Campaign objective, scope and total resource/call constraints | No |
| Actual specification-agent DSL and executable experiment | No; constructed after critique |
| Evaluator name | Yes; authoritative evaluator contract was absent |
| Dataset identity, qualified fidelity, qualification result and coverage | No |
| Data timing/availability, missingness and known limitations | No |
| Approved source summaries and registry/artifact references | No; sources reached only designer |
| Inference unit, uncertainty method/alpha, dependence and split plan | No |
| Training/evaluation chronology and multiple-testing treatment | No |
| Prior exposure and protected-confirmation availability | No |
| Deterministic methodology admission report | No |

The saved REVISE report specifically asked for the uncertainty method, confidence
level, decision boundaries and generator/noise/seed contract. It also requested
future numerical evidence. The repaired review contract distinguishes a proposed
design from results: numerical proof does not exist at the preparation stage.
Critics still assess and may reject genuinely deficient research.

A separate completion defect was confirmed: campaign synthesis/steward could run
immediately after numerical jobs were queued. A successful worker drain did not
then produce a new post-result synthesis.

## Authority and lifecycle

```text
Campaign → hypothesis generation → deterministic capability qualification
         → specification → bounded typed review context → methodological critic
              REVISE → specification revision → revalidation → critic
              ADMIT  → deterministic admission → immutable experiment freeze
         → numerical execution → ingestion → numerical robustness
         → replication support → independent verification → evidence grading
         → synthesis → campaign steward → terminal campaign report
```

`CriticContext` is a strict, versioned contract assembled from registered inputs.
It contains the complete hypothesis, actual draft, evaluator/comparison semantics,
qualified data summary, source references, inference and resource governance.
Summaries and hashes replace raw datasets and documents. Explicit missing details
remain visible; the assembler does not fabricate unavailable data evidence.

The context excludes filesystem locations, provider settings, `.env`, account
identifiers, credentials and protected confirmation rows. `_safe_context` remains
an independent boundary before provider dispatch. Source claims are research
evidence to assess, not instructions with authority over the evaluator.

The LLM reviews coherence, measurement, comparator, estimand and alternatives.
The deterministic layer checks enforceable capabilities, DSL, comparison,
chronology, permitted inference and budgets. Both reports are retained. Neither
an ADMIT nor optimistic narrative can override a failed deterministic gate.

## Revision semantics

- **ADMIT:** advisory readiness for deterministic admission, not execution authority.
- **REVISE:** a correctable pre-execution specification concern. At most **two**
  critic-driven revisions are allowed (three critic reviews including the initial
  draft). Each consumes ordinary campaign call budget.
- **UNSUPPORTED:** an irreparable conceptual or scope concern; deterministic
  classification records whether it is unsupported, data-limited or another failure.

Every draft version, critic report, context digest and change record is immutable.
Revisions preserve hypothesis identity, lineage, evaluator, scoring and original
parameter/search scope. They cannot inspect numerical outcomes or confirmation
data. A valid negative result is a finding; it never returns to preparation.

Named LangGraph stages expose the lifecycle and checkpoints. Stable logical role
IDs are bound to request digests. Accepted responses replay without another model
call. A persisted validated generation can recover the narrow crash window before
the acceptance receipt. A dispatch with no accepted response remains ambiguous
and blocks automatic replay; the graph does not silently spend again.

## Failure and finding classification

| State | Meaning |
|---|---|
| REVISE | Nonterminal, bounded pre-execution methodological repair |
| UNSUPPORTED_HYPOTHESIS | Unsupported research scope/concept or exhausted methodological revisions |
| DATA_LIMITED | Required qualified data capability is missing |
| IMPLEMENTATION_FAILED | Execution/implementation cannot complete correctly |
| INVALID_RESULT | Numerical contract, artifact integrity or independent verification failed |
| REJECTED_FINDING | Valid numerical result rejects the registered research claim |
| INCONCLUSIVE | Valid evidence lacks required precision or support |
| EXPLORATORY_SUPPORTED | Registered effect supported at its declared fidelity/exposure ceiling |

Synthetic evidence always remains F0 and cannot become protected historical
confirmation. Economic disappointment follows robustness, replication, grading
and synthesis without parameter optimization.

## Normal operation

```sh
cd volarb/agent
butterfly-lab auth status
butterfly-lab campaign run configs/campaigns/codex.json \
  --dataset /path/to/development-dataset.json --wait
```

The user does not invoke roles individually. CI uses controlled/offline providers
and never requires ChatGPT authentication. Real Codex verification is an explicit,
finite manual campaign. See [verification](codex-verification.md) for recorded runs.
