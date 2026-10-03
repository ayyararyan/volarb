# Configure Butterfly Lab: Codex and one `.env`

**Configure Butterfly Lab in `agent/.env`.** Copy the committed
[template](../.env.example); do not create provider/secret JSON files. Codex is the
recommended real-model provider. API keys are not required for this path.

## First-time setup

After the [locked Python installation](../README.md), from `volarb/agent`:

```sh
cp .env.example .env
chmod 600 .env
# Edit .env once. No field is required for the default Codex configuration.
codex
# Select Sign in with ChatGPT if not already authenticated.
butterfly-lab config check
butterfly-lab config show
butterfly-lab doctor
butterfly-lab auth status
butterfly-lab auth test
```

Install Codex first if necessary, using the [official CLI instructions](https://developers.openai.com/codex/cli/).
Codex owns login and refresh, using its configured credential store. Lab never
reads, duplicates, exports, or asks you to paste its OAuth tokens. ChatGPT login
and API-key login are different authentication modes; this provider requires the
former. [Official authentication documentation](https://developers.openai.com/codex/auth/).

`config show` redacts secrets. `doctor`, `auth status`, and `provider status` do
**not** submit a model turn. Status distinguishes executable availability,
ChatGPT authentication, app-server handshake, and model availability. Only
`auth test` / `provider test` explicitly request one tiny structured model turn;
this uses subscription capacity. A reported status is not proof that a later
request will fit the account's remaining quota.

## Offline demo and everyday campaign

```sh
butterfly-lab demo --kind all
```

This always uses deterministic fixtures, including when `.env` selects Codex. It
needs neither Codex installation/login nor an API key. Synthetic output is never
reported as historical economic evidence.

For actual research, create and qualify your dataset manifest, then use:

```sh
butterfly-lab data validate /path/to/development-dataset.json
butterfly-lab campaign validate configs/campaigns/codex.json
butterfly-lab campaign run configs/campaigns/codex.json \
  --dataset /path/to/development-dataset.json --wait
butterfly-lab campaign report codex-development-001
```

The [example campaign](../configs/campaigns/codex.json) explicitly approves a finite
Codex scope: two hypotheses and at most 20 model calls. Change its objective,
approvals, and ID deliberately before registering a new research campaign.
A manifest must point to your verified development data; paths above are
placeholders, not claims that those datasets exist. No `--provider-config` is
needed. Omitted campaign provider binds the selected `.env` provider at
registration; an explicit campaign provider must match the configured adapter.
Registered campaign specifications remain immutable.

`--provider-config` is a rejected legacy migration path, not a second preferred
configuration system. Move its user-provided endpoint/model/key/budget settings to
`.env` using the reference below. Existing provider accounting ledgers are
application state, not editable configuration. Do not delete them to reset usage.

## Runtime settings and ownership

[`.env.example`](../.env.example) lists every accepted setting. Shell variables
override the selected file. Blank optional fields select defaults. No `$VAR`,
command substitution, shell evaluation, or multiline values are supported.
Unknown `BUTTERFLY_*` fields and duplicate file assignments fail closed.
Relative paths are resolved against the selected `.env` directory.

The loader finds the nearest Butterfly Lab `pyproject.toml`, then its `.env`, with
an editable-checkout fallback. It never loads an unrelated parent project's
`.env`. For an installed package launched elsewhere, set `BUTTERFLY_ENV_FILE` to
the one authoritative file; this selects a file rather than merging several.
Configuration is loaded once per process. Restart the command after editing it.

| Settings | Default / purpose |
|---|---|
| `BUTTERFLY_LAB_HOME` | Blank: `~/.local/share/butterfly-lab`; private non-Git, non-cloud runtime |
| `BUTTERFLY_LLM_PROVIDER` | `codex`; alternatives `fixture`, `replay`, explicit `openai` |
| `BUTTERFLY_CODEX_MODE` | `managed`; no external listener in this release |
| `BUTTERFLY_CODEX_COMMAND` | `codex`; one executable name/path, not a shell command |
| `BUTTERFLY_CODEX_MODEL` | Blank: Codex resolves its default; no stale hard-coded model |
| `BUTTERFLY_CODEX_STARTUP_TIMEOUT_SECONDS` / `BUTTERFLY_CODEX_REQUEST_TIMEOUT_SECONDS` | `30` / `120` |
| `BUTTERFLY_LLM_MAX_CONCURRENT_CALLS` / `BUTTERFLY_LLM_MAX_CALLS_PER_CAMPAIGN` | `2` / `40`; campaign ceilings may be tighter |
| `BUTTERFLY_LLM_MAX_OUTPUT_TOKENS` / `BUTTERFLY_LLM_MAX_INPUT_BYTES` | `4096` / `65536`; output semantics below |
| `BUTTERFLY_NUMERICAL_WORKERS` / `BUTTERFLY_PENDING_JOB_LIMIT` | `2` / `20`; cannot enlarge registered campaign limits |
| `BUTTERFLY_RUN_CPU_SECONDS` / `BUTTERFLY_RUN_WALL_SECONDS` | `30` / `60`; finite positive values ≤3,600 / ≤7,200, frozen before critic review |
| `BUTTERFLY_RUN_MEMORY_MB` / `BUTTERFLY_RUN_STORAGE_BYTES` | `1024` / `10000000`; bounds 128–65,536 MB / 1–1,000,000,000 bytes; campaign ceilings still apply |
| `BUTTERFLY_LOG_LEVEL` | `INFO`; no credentials or raw provider transcript logging |
| `BUTTERFLY_REPLAY_PATH` | Exact recorded-response evidence file, required only for replay |
| `OPENAI_API_KEY`, `BUTTERFLY_OPENAI_MODEL` | Blank; required only when explicitly selecting `openai` |
| `BUTTERFLY_OPENAI_BASE_URL` | `https://api.openai.com/v1`; credential-free HTTPS |
| `BUTTERFLY_OPENAI_MAX_COST_USD` | `0`; API spending disabled until deliberately configured |
| `BUTTERFLY_OPENAI_INPUT_USD_PER_MILLION` / `BUTTERFLY_OPENAI_OUTPUT_USD_PER_MILLION` | `0`; supply current conservative API price ceilings for API fallback |

**Not stored in `.env`:** campaign/experiment/dataset specifications, source data,
results, checkpoints, registry databases, provider ledgers, or Codex-owned OAuth
credentials. Generated confirmation signing/authorization keys remain private
application-managed runtime state. They are not user-supplied secrets to copy into
`.env`. The file is ignored by Git, excluded from shareable application backups,
and must never be attached to a research artifact. Keep permissions `0600`.

## Provider contract, lifecycle and accounting

| Provider | Provenance | Network/model use |
|---|---|---|
| `FixtureProvider` | `synthetic_fixture` | None; deterministic bounded fixtures |
| `ReplayProvider` | `recorded_replay` | None; exact role/input/schema and response hashes |
| `CodexAppServerProvider` | `real_model` | Managed local app-server with Codex-owned ChatGPT login |
| `OpenAIProvider` | `real_model` | Explicit optional HTTPS API-key adapter |

The six roles remain designer, critic, constrained specification, independent
replication support, synthesizer, and steward. Inputs contain approved literature,
verified capabilities, development-only diagnostics, and evidence-linked findings,
not raw protected data. Strict local Pydantic validation and the existing single
malformed-output correction remain authoritative. A correction consumes another
reserved call. Model prose cannot grant capabilities, change numerical results,
upgrade grades, or expand permissions/budgets.

The adapter uses the supported stdio JSON-RPC transport: `initialize`,
`initialized`, account/model inspection, a fresh thread per role call, and
`turn/start` with a strict `outputSchema` envelope (`payload_json: string`).
The original role schema stays in the prompt; Lab decodes the JSON string and
validates it locally. This is deliberate: Codex forwards schemas with strict
validation, whereas open-ended DSL maps and defaulted Pydantic fields are not
in the provider’s strict schema subset. The envelope does not weaken the local
research contract or permit an extra economic repair loop.
It consumes stream notifications until terminal
completion; it is not a scraper for interactive CLI output. Official WebSocket
transport is experimental/unsupported, so `external` mode is rejected. The
interface was checked against **Codex CLI 0.149.1** and the official documentation
on **2026-10-02**. [App-server reference](https://developers.openai.com/codex/app-server/).

Managed processes have bounded startup/request waits, sanitized errors, explicit
shutdown and child reaping. A crashed or timed-out ambiguous turn is not silently
replayed. A new permitted call may establish a new process, subject to the same
persistent reservations. Numerical workers and graph checkpoints are independent
of app-server lifetime. Lab disables Codex tools, applications, hooks, skills,
shell execution and discovered MCP integrations for bounded role turns; its
scratch workspace is separate from market data. This is not a claim that a prompt
alone supplies OS isolation, nor a reason to relax numerical/confirmation
sandboxes.

Restricted reads use a unique, process-local named permission profile. It grants
read access only to Codex's platform-minimum paths and the empty private scratch
directory, with command network access disabled. The adapter opts into the beta
permission-profile protocol, verifies the effective profile definition and the
thread's active profile, and refuses a mismatch. It does not change the user's
Codex configuration or credential store. Codex 0.149.1 rejects the retired
`sandboxPolicy.readOnly.access` representation; merely removing that field would
restore broad filesystem reads and is not a supported workaround.
[Permission-profile reference](https://learn.chatgpt.com/docs/permissions).

Codex-plan reservations enforce local call/concurrency/input limits. There is no
API-dollar conversion for subscription usage. Token and rate-limit metadata are
recorded when supplied; unknown consumption stays unknown. The current app-server
turn interface has no documented hard output-token parameter: the configured
output ceiling is an observation/interruption and acceptance limit, **not a
promise that the server cannot generate or charge beyond it**. Do not interpret
`budget.llm_tokens=0` in the Codex example as unlimited local calls or measured
subscription quota. It means no fictitious aggregate token quota was approved.
The actual resolved model, prompt/response hashes, reported usage and unavailable
metadata reasons remain part of agent-call provenance and linked research records.
[App-server usage events](https://developers.openai.com/codex/app-server/).

The strict-schema behavior was checked against the installed-version
[app-server forwarding implementation](https://github.com/openai/codex/blob/rust-v0.149.1/codex-rs/app-server/src/request_processors/turn_processor.rs#L561),
[session strict-mode selection](https://github.com/openai/codex/blob/rust-v0.149.1/codex-rs/core/src/session/turn.rs#L1325),
and [request serialization](https://github.com/openai/codex/blob/rust-v0.149.1/codex-rs/codex-api/src/common.rs#L372).

Optional OpenAI usage retains positive configured API-price ceilings plus campaign
USD/token authorization. Failed or ambiguous requests retain their reservation.
It uses JSON mode and strict local validation, not a claim that JSON mode enforces
all scientific rules. No provider ever falls back automatically to API-key or
fixture output. [OpenAI JSON-mode documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

## Troubleshooting

| Symptom | Action |
|---|---|
| Codex executable missing | Install the official CLI; set `BUTTERFLY_CODEX_COMMAND` only if it is outside `PATH` |
| Not signed into ChatGPT / API-key mode | Run `codex`, select **Sign in with ChatGPT**, then `butterfly-lab auth status`; do not paste OAuth tokens |
| App-server unavailable/crashed | Check `codex --version`, command path and startup timeout; rerun status; an ambiguous model call is not automatically retried |
| Requested model unavailable | Clear `BUTTERFLY_CODEX_MODEL` for the Codex default, or choose an available model in Codex and rerun provider status |
| Subscription/usage limit reached | Wait for the reported reset or resolve the account limit in Codex; there is no automatic API spend fallback |
| Invalid `.env` | Run `butterfly-lab config check`; fix the named field, duplicate, quote, or unsupported setting; errors do not echo values |
| Numerical sandbox unavailable | Follow `doctor`'s macOS/Linux sandbox result; no model configuration disables the required boundary |
| Old private provider JSON | Migrate runtime fields to `.env`; retain immutable research definitions and replay evidence separately |

## Verification

Offline CI uses controlled protocol servers, never your ChatGPT login. Run the
full locked-environment `pytest -q` suite for configuration, provider protocol,
LangGraph, scientific, recovery and security coverage. A live status check and a
live model test are different evidence; see the release verification report for
what was actually executed on the release host.
