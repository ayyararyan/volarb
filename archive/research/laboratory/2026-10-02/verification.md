# Release verification

> Historical initial-release receipt (2026-10-02), not current operating guidance.
> See the [archive index](README.md) for replacements and scope.

Initial laboratory-build evidence. For the subsequent Codex/provider configuration
release, see [Codex migration verification](../../../../agent/docs/codex-verification.md).

Research-only release **0.1.0**. Installation and integrations are distinguished
from market evidence. No broker operation, live risk change, authentication change
or live-ledger write is part of this release.

## Executed acceptance

| Check | Observed result |
|---|---|
| Locked isolated environment | Python 3.12.13; LangGraph 1.2.12; checkpoint-sqlite 3.0.3; 58 hash-locked resolved dependencies |
| Clean package install | Separate non-editable installation, not the development source import |
| Full installed-package tests | **123 passed in 23.72 seconds**, no skips or warnings, after final baseline/availability hardening |
| Lint/format | Ruff passed; 46 Python files consistently formatted; frozen controller excluded from formatting |
| Types | mypy passed for contract/config modules; not claimed as whole-project strict typing |
| Generated consistency | 14 schemas, 2 package resources, 5 Mermaid sources and rendered SVGs checked against hashes |
| Host isolation | macOS denial probes passed: protected reads, evaluator writes, network, credential inheritance |
| Installed CLI demos | Both actual campaign graphs completed with ingested, independently reconstructed results |
| Backup/restore | 32 files verified; manifest SHA256 `2b313d3fa873fd80fc03b2531512e32c6052a9f56f601840cb72f756cb3cb4a3` |
| Protected confirmation | Authorization, consumption, failure closure and raw 30-session four-leg path tested on segregated fixtures |
| Real-source qualification | Both sources DATA_LIMITED; no historical economic backtest executed |

An earlier clean-install run exposed duplicate import paths in the environment
fingerprint: three tests failed and demos produced implementation failures. The
bug was fixed, regression-tested and fresh-runtime demos rerun. Those failed
runs are not counted as successful acceptance.

Final clean evaluator hash:
`d390a0736e97a2100821896d970098d27384854d592ad7c0d0f09fc4e696f4f5`.
Environment hashes bind an actual installed environment, not a universal
cross-platform value. Databases/checkpoints are intentionally uncommitted.

## Controlled findings, not market discoveries

- EXP-001: **INCONCLUSIVE**, computationally reconstructed, F0 synthetic.
- Four-leg hold/close/recenter: **EXPLORATORY_SUPPORTED**, F0 synthetic, with
  full-cycle costs and paths. This is not evidence of a real Indian-index edge.
- Both demos retain a **DATA_LIMITED** question with missing capabilities.
- The frozen null/planted design uses 40 seeds per family. The measured run
  supported 0/40 nulls and recovered 40/40 planted effects. Wilson 95% bounds are
  [0%, 8.76%] and [91.24%, 100%], respectively; zero observed errors does not
  establish zero error rate. [Measured report](../../../../agent/docs/evidence/scientific.json).
- Matched fixture multi-role, single-agent and deterministic workflows each
  completed three numerical experiments under equal evidence/compute budgets,
  reconstructing three results and one informative negative. This exercises the
  harness, not live-model quality or multi-agent superiority. Human review time
  remains unknown, not zero. [Matched report](../../../../agent/docs/evidence/comparison.json).

Reports link prediction, opportunity, exclusion, fills, holding paths, inference
and reconstruction artifacts. Only sanitized summaries are committed, not raw
real data, local account records, databases or private host paths.

## Capacity measurement

Host: Apple M2 Max, 12 logical CPUs, 64 GiB RAM; **two numerical workers**.
Each of the 2,000 actual jobs used eight controlled sessions and 99 bootstrap
samples. The controller was reopened after outbox commit, reconciled before/after,
and every accepted result was duplicate-ingested to check idempotence.

| Measurement | Observed |
|---|---:|
| Hypothesis records | 250 |
| Accepted/ingested jobs | 2,000 / 2,000 |
| Registration | 9.093 s |
| Execution | 774.081 s |
| Throughput | 2.584 jobs/s |
| Numerical CPU | 829.398 CPU-s |
| Largest observed child RSS | 110.828 MiB |
| Artifact bytes | 19,576,076 |
| Unresolved jobs after reconciliation | 0 |

These are toy-job measurements, **not real-backtest throughput**. Capacity
records are not 250 original economic discoveries. [Full receipt](../../../../agent/docs/evidence/load.json).
This measured run includes the final queue/registry/search-budget implementation,
using evaluator hash `429b5452f68f72286168bc525624dfdd63726ac58891b59cff00b36c7364fc11`.
The subsequently hardened non-B0 selection/packet-availability path does not enter
this controlled workload. It was independently covered by the final 123-test
suite, fresh installed demos and a 20-job numerical-service smoke run. Different
load runs varied materially in wall time; these numbers are observed, not a
capacity guarantee or a cherry-picked fastest run.

## Actual research and external limits

The [fresh data audit](data-audit.md) records source hashes and scope. Spot data
has 12 inconsistent OHLC rows and unverified bar-label semantics. Rolling option
lanes lack fixed-contract identity and quantities; they cannot represent held
securities. An additional rich source remained unreadable. No repairs were
fabricated to produce historical P&L.

No genuinely unexamined real confirmation partition was available. Protected
confirmation software is fixture-tested, but real confirmatory research remains
unavailable. The real-provider adapter is implemented and HTTP-contract-tested;
no nonzero live-model budget was configured and no live-provider call was made.
Linux bwrap is implemented with fail-closed checks, but not integration-tested
on this macOS host.

## Reproduce

Use the [clean installation](../../../../agent/README.md), then:

```sh
pytest -q
butterfly-lab doctor
butterfly-lab demo --kind all > "$HOME/.local/share/demo.json"
python examples/check_demo.py "$HOME/.local/share/demo.json"
python examples/check_generated.py
butterfly-lab --root "$HOME/.local/share/lab-null" benchmark scientific
butterfly-lab --root "$HOME/.local/share/lab-compare" benchmark compare
butterfly-lab --root "$HOME/.local/share/lab-capacity" benchmark load --hypotheses 250 --jobs 2000
```

Use fresh private runtime directories. CI runs locked installation, lint/format,
contract typing, the full suite, doctor, both LangGraph demos with outcome
assertions and generated-file checks. Capacity tests are local/manual.

## Repository delivery

Published branch: [feat/butterfly-research-agent](https://github.com/ayyararyan/volarb/tree/feat/butterfly-research-agent).
[Pull request #1](https://github.com/ayyararyan/volarb/pull/1) is the authoritative
final-head CI and merge receipt. Remote tree hashes were compared with local Git;
implementation, tests, configs, documentation and diagrams were verified present.
Changes are restricted to `agent/`, its CI workflow and the housekeeping root
allowlist. The original unrelated dashboard edit remains untouched.

Hosted clean installation, tests, doctor, demos and generated checks passed on
[the baseline-hardening run](https://github.com/ayyararyan/volarb/actions/runs/37016461290).
Final-head checks are required before the normal merge; no administrator bypass
or force push is used. Earlier workflow failures were corrected, not hidden:
runner context was moved to an allocated step, and the unavailable setup-python
macOS patch distribution was replaced with the locally verified pinned uv
installer. See GitHub's [context availability](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability)
and the [setup-uv action](https://github.com/astral-sh/setup-uv).
