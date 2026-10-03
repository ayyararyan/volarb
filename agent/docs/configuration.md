# Configuration reference

## Machine, provider and user-secret configuration

The single user-editable file is **`agent/.env`**, copied from
[`.env.example`](../.env.example). Its typed loader is `settings.py`; shell
variables override the selected file, and `BUTTERFLY_ENV_FILE` explicitly selects
an alternative single location. Run `butterfly-lab config check` or the redacted
`butterfly-lab config show`. These commands do not make model requests.

The default real-model provider is Codex app-server with Codex-owned ChatGPT
authentication. No API key or copied OAuth token is needed. See the concise
[provider/setup guide](providers.md) for all runtime fields, bounded usage,
migration from provider JSON, and troubleshooting. Runtime limits are ceilings;
they cannot enlarge immutable scientific approvals.

New campaign-prepared experiments copy `BUTTERFLY_RUN_CPU_SECONDS` (default 30),
`BUTTERFLY_RUN_WALL_SECONDS` (60), `BUTTERFLY_RUN_MEMORY_MB` (1024), and
`BUTTERFLY_RUN_STORAGE_BYTES` (10,000,000) into their immutable `RunResources`
before specification and critic review. CPU/wall settings must be finite and
positive, at most 3,600/7,200 seconds; memory is 128–65,536 MB and storage is
1–1,000,000,000 bytes. Existing campaign aggregate CPU/storage and per-run memory
ceilings remain authoritative. Settings changes do not modify prepared,
checkpointed or running experiments; methodological revision cannot change their
frozen resources. Configure larger limits before preparing a new experiment.

## Immutable scientific configuration

All public scientific contracts are strict, immutable Pydantic schemas with extra
fields forbidden. Generated JSON schemas live in [schemas/](schemas/).

| Contract | Important choices |
|---|---|
| CampaignSpec | approved scope, finite call/compute budget, 1–2 numerical workers, bounded preparation, resolved provider, optional protected dataset |
| DatasetManifest | kind, source hash, provenance, F0–F4, start/end/event labels, availability lag, calendar/session metadata, exposure |
| HypothesisSpec | mechanism, timestamp-observable inputs, comparator, metric, practical effect, risk, finite alternatives, falsification |
| ExperimentSpec | registered hypothesis/trial/data, evaluator, closed DSL, split, inference, seed, relation and reproducibility hashes |
| BudgetSpec | upper-bound runs/CPU/storage/RAM/pending capacity; separately declared model, data and human resources |
| RunManifest | attempt/fence, code/environment/config provenance, aware timestamps, resource measurements and artifact references |
| ValidationReport | explicit tests, immutable subject reference, independent reviewer and evidence ceiling |
| ResearchFinding | outcome, evidence dimensions, scope, limitations and supersession |

`configs/seeds.json` contains all twelve proposed research questions, not discoveries.
`configs/benchmarks.json` freezes controlled benchmark seeds/tolerances before execution.
`examples/make_campaign.py` creates safe data/manifests and a campaign outside Git.
`examples/register_real_data.py` builds manifests from operator-supplied paths; it does
not assume timestamps, fixed contracts, lots or protected status from filenames.
`configs/campaigns/codex.json` supplies a bounded Codex campaign definition, not
provider connectivity/secrets. Codex has no invented API-dollar cost; the optional
OpenAI adapter retains explicit API USD/token budgets.

## Fidelity and outcome semantics

F0 synthetic, F1 theoretical/model, F2 observed bars (spot prediction or identified
option bars), F3 synchronized quotes. F4 is deliberately rejected. A label cannot
supply missing contract identity, size or timing. Unknown monetary inputs need a
reason, never a silent zero. Historical margin proxies are explicit, not max-loss.

Operational states (`QUEUED`, `RUNNING`, `COMPLETED`, `INGESTED`, cancellation,
failure, `LOST_UNRESOLVED`) are distinct from scientific outcomes:
`UNSUPPORTED_HYPOTHESIS`, `DATA_LIMITED`, `IMPLEMENTATION_FAILED`, `INVALID_RESULT`,
`REJECTED_FINDING`, `INCONCLUSIVE`, `EXPLORATORY_SUPPORTED`,
`INDEPENDENTLY_SUPPORTED`, `CANCELLED`, `BUDGET_EXHAUSTED`.

A confidence interval spanning the practical effect is inconclusive. An interval
excluding it on the adverse side supports an informative rejection. Narration cannot
upgrade grades, fix sparse tails, turn association into causation, or erase search.
