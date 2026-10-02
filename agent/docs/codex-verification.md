# Codex provider and centralized configuration — verification

Date: 2026-10-02. Branch: `feat/codex-appserver-env`.
Initial implementation commit: `e9f0d64d52c2d58feb306b335eb3b92a43957817`;
the release follow-ups also fix uncached annotation checks and deterministic
source resolution between editable and wheel installations.
This report distinguishes software tests, controlled model transport, real
app-server diagnostics, and actual model usage.

## Post-login compatibility correction — 2026-10-02

The release-time signed-out diagnostics below could not exercise `turn/start`.
After the operator completed ChatGPT sign-in, the first real test exposed a
protocol defect: Codex 0.149.1 rejects the retired `readOnly.access` field. The
earlier mock and documentation audit did not catch that rejection. Their passing
results were not evidence of a successful live model request.

The adapter now uses a unique, process-local named permissions profile and the
required experimental protocol capability. It verifies the effective profile
and thread provenance before generation. Minimal-platform and private-scratch
read access, disabled command network access, and disabled tools/MCP remain in
force. Inline TOML values fix native CLI parsing of quoted/dotted filesystem and
MCP keys; only known null serialization defaults are normalized. User Codex
configuration and credential storage are not modified.

The CLI installed on the host changed to **0.160.0** during verification. Native
initialization, effective-policy validation and thread-profile confirmation all
passed against that version. The subsequent explicit `butterfly-lab auth test`
completed **one real model response**, resolved to **gpt-6-astra**, and validated
the typed payload. Elapsed time was **5.60 seconds**; reported usage was **7,327
input tokens and 35 output tokens**. This used ChatGPT subscription authentication,
not an API key or fallback. Account identifiers, authentication data and raw
provider payloads are not included in this report.

Follow-up verification: **227 tests passed in 43.54 seconds**, including **53
provider/integration tests**. Ruff lint and formatting and uncached mypy for all
six configured modules passed. This is connectivity/contract verification, not
a completed research campaign or a guarantee of remaining subscription quota.

The sections below preserve the original release-time evidence.

## Delivered

- `settings.py`: one cached, typed runtime configuration from **`agent/.env`**;
  deterministic shell overrides, redacted diagnostics, safe template and parsing.
- `codex_provider.py`: managed official stdio app-server, ChatGPT-only account
  admission, restrictive effective configuration verification, fresh role threads,
  strict JSON-envelope output plus authoritative local role validation, bounded
  nonblocking IO, cancellation and child reaping.
- `provider_factory.py`, `agents.py`, `cli.py`: six existing research roles,
  default Codex selection, explicit fixture/replay/API alternatives, configuration
  and no-spend status commands, explicitly requested single-call smoke test.
- Registry/worker manifests: frozen model-call artifact references and resolved
  models at submission. Subscription accounting has **no invented USD price**.
- Durable call reservations and aggregate machine queue limits; backup retains
  generated usage ledgers but excludes `.env`, OAuth and signing material.
- Safe `.env.example`, bounded `configs/campaigns/codex.json`, updated setup,
  operations, generated schemas, narrow CI and regression tests.

The optional OpenAI adapter remains functional through contract tests. It is
never an automatic fallback. Its dollar ceiling remains explicit; its local call
ceiling is campaign-scoped. A narrow controlled-fixture bug found by integration
was corrected: the evaluator now honors the frozen compiled DSL, not just legacy
parameter fields. Historical financial evaluators/accounting were not redesigned.

## Requirements → acceptance evidence

| Requirement | Implementation | Executed acceptance tests |
|---|---|---|
| One `.env`, typed settings, precedence/redaction | settings; template; CLI | `test_settings.py`, `test_secret_hygiene.py`, CLI integration |
| Official managed Codex protocol, ChatGPT-owned authentication | Codex provider | `test_codex_provider.py`; real initialize/config/account diagnostics |
| Structured six-role calls, bounded correction, no grade override | AgentService; provider factory | `test_codex_integration.py`, existing agent tests |
| No silent fixture/API fallback | provider factory; campaign binding | wrong-provider, absent-authentication and zero-budget negative tests |
| Timeout/crash/stalled stdin, MCP/tool rejection, process cleanup | managed transport | fake subprocess protocol/fault tests, process reaping assertions |
| Persistent call limits, explicit subscription accounting | Codex ledger; campaign budget | restart, concurrent reservations, machine/campaign ceilings, backup/restore |
| Resolved model and prompt lineage | registry; RunManifest | hash-verified generation references after graph restart/external execution |
| Normal campaign without provider JSON | settings-driven CLI | complete controlled Codex campaign using `.env`, with provider omitted in spec |
| Numerical/confirmation boundaries unchanged | existing sandbox/evidence services | full accounting, temporal, scientific, worker, confirmation and recovery suite |
| Offline repeatability | fixture/replay; demo | full demos, replay hash checks, clean wheel installation |
| Secret-free CI/repository/backup | tracked-file scanner; allowlisted backup | ignored `.env`, safe template, private-context rejection, artifact/backup scans |

## Test evidence

The development checkout completed **218 tests: all passed**, in **40.35 seconds**.
This includes 30 controlled app-server provider tests and 14 provider/CLI/graph
integration tests, alongside all existing scientific and recovery tests.
Ruff lint and formatting passed; mypy passed for six configured source modules.
A fresh detached checkout, separately hash-locked environment, and non-editable
wheel installation also completed **218 tests: all passed**, in **42.01 seconds**.
Both clean-install offline demos completed and their artifact reports validated.
The fresh uncached type pass exposed six annotation issues; those were fixed
without weakening checks or changing numerical behavior.
Fourteen JSON schemas, two installed resources and five existing rendered
diagrams passed consistency verification. Dependency lock contents were unchanged.

Both offline demos completed through real numerical worker processes and artifact
acceptance, with zero pending experiments:

| Controlled example | Result | Evidence |
|---|---|---|
| EXP-001 spot fixture | INCONCLUSIVE | F0 synthetic |
| Four-leg hold/recenter comparison | EXPLORATORY_SUPPORTED | F0 synthetic |
| Two unavailable-capability examples | DATA_LIMITED | Explicit blocked fixtures |
| Codex protocol planted-effect campaign | EXPLORATORY_SUPPORTED | Fake model transport, real graph/worker; F0 synthetic |

These are **software demonstrations**, not historical strategy discoveries. No
historical research campaign or full live-model campaign was run for this change.
The prior 2,000-job laboratory benchmark was not rerun or re-labelled as new
provider performance evidence.

Version-pinned protocol-source inspection additionally caught strict-schema
forwarding: raw Pydantic schemas with optional defaults/open DSL maps are not
valid provider schemas. The adapter therefore uses a closed `payload_json` wire
envelope and retains the complete original schema for local role validation.
The controlled server checks that strict wire shape, not merely successful JSON.

## Real Codex diagnostic and external limitation

Installed **Codex CLI 0.149.1** successfully started, initialized, returned its
restricted effective configuration, and answered account inspection. Processes
were closed and reaped. The supported `codex login status` returned signed out;
app-server `account/read` likewise reported no ChatGPT authentication.

**Live model requests performed: zero.** The conditional live smoke test was not
run because ChatGPT login was unavailable in the active Codex profile. No API key
was requested, no credential file was opened/copied, and no API fallback was used.
Authenticate with `codex login` (ChatGPT flow), then run `butterfly-lab auth test`
to request exactly one small typed response. CI never depends on that login.

Official protocol/authentication sources and version assumptions are linked in
[provider operations](providers.md). External WebSocket transport is deliberately
unsupported in this release because current official documentation marks it
experimental/unsupported. The app-server exposes no hard upstream output-token
parameter: local usage/byte/deadline checks can interrupt/reject output but cannot
guarantee zero subscription-quota overshoot. Rate-limit snapshots, when exposed,
are numerical observations, not exact subscription-cost accounting.

## Exact setup and daily use

From a clean repository checkout:

```sh
cd agent
uv venv --python 3.12.13 "$HOME/.local/share/butterfly-lab-env"
uv pip sync --python "$HOME/.local/share/butterfly-lab-env/bin/python" --require-hashes requirements.lock
uv pip install --python "$HOME/.local/share/butterfly-lab-env/bin/python" --no-deps .
export PATH="$HOME/.local/share/butterfly-lab-env/bin:$PATH"
cp .env.example .env
chmod 600 .env
codex login
butterfly-lab config check
butterfly-lab doctor
butterfly-lab auth status
butterfly-lab auth test
butterfly-lab demo --kind all
```

**Required `.env` fields to fill for normal Codex use: none.** Defaults use `codex`
on `PATH`, managed stdio, Codex's resolved default model and a private non-cloud
runtime directory. Optionally change `BUTTERFLY_LAB_HOME`,
`BUTTERFLY_CODEX_COMMAND`, `BUTTERFLY_CODEX_MODEL` and local ceilings. Leave
`OPENAI_API_KEY` blank. Do not paste OAuth tokens into Lab configuration.

Everyday campaign invocation, after creating/qualifying the real dataset manifest:

```sh
butterfly-lab campaign run configs/campaigns/codex.json \
  --dataset /path/to/development-dataset.json --wait
butterfly-lab campaign report codex-development-001
```

Use a new immutable campaign ID when changing its scientific specification.
Existing pre-change graph/evaluator fingerprints are not silently migrated:
completed evidence remains readable, but incompatible checkpoint resumption is
refused. Preserve the earlier version for those frozen campaigns or register an
explicit new research lineage.

## Scope and publication

Changes are limited to `agent/` and its existing scoped CI workflow. Operational
trading code, Dhan credentials, production limits, live ledgers and unrelated
checkout edits were not changed. Only `.env.example` is tracked; the actual `.env`
is private and ignored. No raw datasets, OAuth tokens, runtime databases or large
artifacts were committed. Final source revision tested from the clean wheel install:
`fa31f248bbbbc7ee1d8624548c5fef64f7b3a6cd`. Uncached mypy passes against the
checkout sources in both environments; the final schema, fixture and demo checks
also pass. Documentation-only release receipts do not change numerical logic.

- [Published branch](https://github.com/ayyararyan/volarb/tree/feat/codex-appserver-env/agent)
- [PR #2 and current merge/check status](https://github.com/ayyararyan/volarb/pull/2)
- [Tested source commit](https://github.com/ayyararyan/volarb/commit/fa31f248bbbbc7ee1d8624548c5fef64f7b3a6cd)
- [Scoped workflow runs](https://github.com/ayyararyan/volarb/actions/workflows/test-research-agent.yml)
