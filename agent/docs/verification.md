# Release verification

Research-only release **0.1.0**. Installation and integrations are distinguished
from market evidence. No broker operation, live risk change, authentication change
or live-ledger write is part of this release.

## Executed acceptance

| Check | Observed result |
|---|---|
| Locked isolated environment | Python 3.12.13; LangGraph 1.2.12; checkpoint-sqlite 3.0.3; 58 hash-locked resolved dependencies |
| Clean package install | Separate non-editable installation, not the development source import |
| Full installed-package tests | **120 passed in 22.96 seconds**, no skips; two enum-construction test warnings subsequently removed and affected 15-test registry suite passed again |
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
`429b5452f68f72286168bc525624dfdd63726ac58891b59cff00b36c7364fc11`.
Environment hashes bind an actual installed environment, not a universal
cross-platform value. Databases/checkpoints are intentionally uncommitted.

## Controlled findings, not market discoveries

- EXP-001: **INCONCLUSIVE**, computationally reconstructed, F0 synthetic.
- Four-leg hold/close/recenter: **EXPLORATORY_SUPPORTED**, F0 synthetic, with
  full-cycle costs and paths. This is not evidence of a real Indian-index edge.
- Both demos retain a **DATA_LIMITED** question with missing capabilities.
- The frozen null/planted design uses 40 seeds per family. A preliminary run
  supported 0/40 nulls and recovered 40/40 planted effects. Finite Monte Carlo
  uncertainty applies; zero observed errors does not establish zero error rate.
- Matched fixture multi-role, single-agent and deterministic workflows each
  completed three numerical experiments under equal evidence/compute budgets,
  reconstructing three results and one informative negative. This exercises the
  harness, not live-model quality or multi-agent superiority. Human review time
  remains unknown, not zero.

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
| Registration | 8.833 s |
| Execution | 562.827 s |
| Throughput | 3.553 jobs/s |
| Numerical CPU | 748.333 CPU-s |
| Largest observed child RSS | 113.797 MiB |
| Artifact bytes | 19,536,540 |
| Unresolved jobs after reconciliation | 0 |

These are toy-job measurements, **not real-backtest throughput**. Capacity
records are not 250 original economic discoveries. The final lineage/search
budget hardening is being re-exercised on the same workload; its receipt will
replace these measurements before delivery.

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

Use the [clean installation](../README.md), then:

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

Branch: `feat/butterfly-research-agent`. Scope: `agent/`, its CI workflow and the
housekeeping root allowlist. Remote SHA, CI and merge receipts are recorded after
publication; a local commit is not asserted to be a successful push or merge.
