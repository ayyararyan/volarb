# Offline validation

Run from the repository root unless stated otherwise. These commands use synthetic evidence and isolated temporary storage. They do not start services, call Dhan, alter credentials, create schedules or authorize orders.

## Runtimes and isolation

The portable kit pins Python 3.12.13, Node 26.5.0 and npm 11.17.0. Research laboratory dependencies have their **own** lock and environment; do not merge its NumPy/scientific pins with the root kit lock. Do not source a live `.env` for testing.

```sh
python3.12 -m venv /tmp/volarb-checks
/tmp/volarb-checks/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-dev.lock
npm ci --ignore-scripts --prefix services/dhan-chatgpt-mcp
```

## Source and execution architecture

```sh
python3 -B tools/check_repository.py
python3 -B -m unittest discover -s tests -p 'test_repository_hygiene.py' -v
node --test architecture/lib/*.test.mjs architecture/*.test.mjs
node architecture/validate.mjs
node --test execution-testkit/test/*.test.mjs
npm test --prefix services/dhan-chatgpt-mcp
```

The source-hygiene checker validates local Markdown paths and heading anchors, JSON syntax, relative JS imports and per-directory archive indexes. It does not check remote websites or execute code examples. Architecture checks cover canonical identities, legacy mirrors and composition/manifests; the testbed uses injected simulated dependencies. These tests do not establish a completed execution pipeline.

## Portable kit, SHADOW workflow and research skills

```sh
/tmp/volarb-checks/bin/python -B -m unittest discover -s tests -v
/tmp/volarb-checks/bin/python -B -m unittest discover -s services/day-workflow -p 'test_*.py' -v
/tmp/volarb-checks/bin/python -m pytest -q skill/butterfly-market-outlook/tests
/tmp/volarb-checks/bin/python .github/skill-tools/check_rv_fixtures.py
for skill in butterfly-market-outlook intraday-realized-volatility-forecast market-news-signal-filter; do
  /tmp/volarb-checks/bin/python .github/skill-tools/package_skill.py "skill/$skill" "/tmp/volarb-skill-check/$skill"
done
```

The portable-kit CI also runs setup twice into isolated data/workspace directories, then `doctor` and source packaging. That path intentionally does not restore private state, enable browser login, start services or activate mutation commands. See [kit instructions](AGENT_KIT.md).

## Optional dashboard

The HAR unit tests do not require the external Shaurya packages or a live dashboard:

```sh
python3.12 -m venv /tmp/volarb-dashboard-checks
/tmp/volarb-dashboard-checks/bin/python -m pip install -r services/essvi-dashboard/requirements-test.txt
/tmp/volarb-dashboard-checks/bin/python -B -m unittest discover -s services/essvi-dashboard -p 'test_har.py' -v
```

## Research laboratory

Follow the locked sequence in [research CI](../.github/workflows/test-research-agent.yml), from `agent/`: sync `agent/requirements.lock`, install the package with `--no-deps`, run `ruff check`, `ruff format --check`, `mypy`, `pytest`, the offline config/doctor checks, demo validation and `examples/check_generated.py`. No live Codex/API campaign is required by this audit.

On macOS, invoke an isolated interpreter through its canonical resolved path (`/private/tmp/...`, not the `/tmp` symlink) for sandbox tests. Use a clean test environment rather than inheriting `BUTTERFLY_LAB_HOME` from a live installation; tests deliberately exercise default/override behavior.

## Container import closure

```sh
docker build -f services/dhan-chatgpt-mcp/Dockerfile -t volarb-dhan-check .
```

The context is the **repository root** so the Dhan provider's generic Execution Engine imports exist. The Dockerfile-specific allowlist excludes private state and testkit code. Build/import checks are not container deployment or broker authentication.

## CI interpretation

- Architecture, Execution Testbed, Dhan/provider, portable kit, SHADOW workflow, dashboard, research lab, skill packaging and repository hygiene are separate workflows.
- Path filters include shared runtime dependencies; a contract change must exercise its consumers.
- Record local and hosted CI results separately. A passing source suite is not a live trading-readiness receipt.
