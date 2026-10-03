# Butterfly Research Laboratory

Research-only, registry-centred **LangGraph** laboratory. No broker execution,
production strategy imports, broker credentials or live-ledger writes. Synthetic examples
are engineering evidence, never historical strategy performance.

This is the retrospective research laboratory, not the reusable
[Execution Engine](../execution-engine/README.md) or its
[Execution Testbed](../execution-testkit/README.md). Its numerical workers simulate
registered research experiments; they cannot submit broker orders. The live
[butterfly decision skill](../skill/butterfly-market-outlook/SKILL.md) has a separate
control plane. `src/butterfly_lab/observed_controller_v26.py` is an intentionally
byte-frozen replay baseline, not a second live controller; never synchronize it
with later skill changes.

## Install and run

Requires Python **3.12** and an enforced numerical sandbox: macOS `sandbox-exec`, or
Linux `bwrap` with permitted user namespaces. `doctor` tests the actual boundary;
protected computation fails closed when unavailable.

From a clean checkout:

```sh
cd agent
uv venv --python 3.12.13 "$HOME/.local/share/butterfly-lab-env"
uv pip sync --python "$HOME/.local/share/butterfly-lab-env/bin/python" --require-hashes requirements.lock
uv pip install --python "$HOME/.local/share/butterfly-lab-env/bin/python" --no-deps .
export PATH="$HOME/.local/share/butterfly-lab-env/bin:$PATH"
cp .env.example .env
chmod 600 .env
# Edit .env once; private runtime defaults outside the checkout.
butterfly-lab config check
butterfly-lab doctor
butterfly-lab demo --kind all
```

The demo runs an actual campaign graph, separate numerical worker processes,
artifact ingestion, robustness, independent reconstruction, evidence grading and
memory. It includes EXP-001, a full four-leg hold/close/recenter comparison, and
blocked hypotheses. No model credentials are needed. Use a new runtime directory
for a fresh demonstration; immutable IDs deliberately reject changed reruns.

For real-model research, install Codex, run `codex` and choose **Sign in with
ChatGPT**, then `butterfly-lab auth status` and the explicitly spending
`butterfly-lab auth test`. The recommended provider is **Codex app-server**, not
an API-key adapter. Configure Lab in **`agent/.env`**; Codex keeps ownership of
its login credentials. [First-time setup, exact campaign command and troubleshooting](docs/providers.md).

## Commands and evidence

- [Operations and recovery](docs/operations.md): campaigns, workers, cancellation,
  confirmation, backup/restore and reports.
- [Scientific contract](docs/scientific-contract.md): exact definitions, F0–F4
  ceilings, inference and baseline provenance.
- [Provider configuration](docs/providers.md) and [security boundary](docs/security.md).
- [Live research lifecycle](docs/live-research-lifecycle.md) and
  [dated Codex acceptance evidence](docs/codex-verification.md).
- [Current verified data capabilities](docs/real-data-capabilities.md),
  [source discovery and limitations](docs/real-data-discovery.md), and
  [first real-data campaign findings](docs/first-real-campaign.md).
- [Requirements → tests](docs/traceability.md),
  [documentation index](docs/README.md), and
  [initial-release archive](../archive/research/laboratory/2026-10-02/README.md).
- [Architecture and diagrams](docs/architecture.md), [configuration reference](docs/configuration.md).

```sh
pytest -q
ruff check .
ruff format --check .
mypy --config-file pyproject.toml
butterfly-lab --root "$HOME/.local/share/lab-scientific" benchmark scientific
butterfly-lab --root "$HOME/.local/share/lab-comparison" benchmark compare
butterfly-lab --root "$HOME/.local/share/lab-load" benchmark load --hypotheses 250 --jobs 2000
```

The last command launches **2,000 real lightweight numerical jobs** and is excluded
from fast CI. Its timings must not be extrapolated to real option-path backtests.
Runtime SQLite databases, private datasets, provider ledgers and large artifacts
stay outside the repository and cloud-synchronised folders.
