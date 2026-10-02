# Providers and bounded research roles

`agents.py` defines designer, methodological critic, constrained specification,
replication-support, evidence-synthesis and campaign-steward profiles. These are
bounded calls, not permanently running agents. Deterministic gates remain
authoritative: a model's `ADMIT` cannot supply missing data, change a numerical
result, spend more money, or upgrade an evidence grade.

## Three distinct provenance labels

| Provider | Output label | Behaviour |
|---|---|---|
| `FixtureProvider` | `synthetic_fixture` | Deterministic registered responses; no model call |
| `ReplayProvider` | `recorded_replay` | Exact role/input/schema hash must match a recorded response hash |
| `OpenAIProvider` | `real_model` | Configurable HTTPS OpenAI-compatible chat-completions request |

Provider contract tests use an injected HTTP transport. They verify request and
response semantics, not connectivity to a real service. No nonzero live-provider budget was configured during this implementation, so no
live-provider request was made. Passing offline tests do not verify connectivity
or imply provider spending.

## Optional real-provider configuration

Create a private JSON configuration outside the repository; choose a compatible
model and **explicit price ceilings**, checked against your provider's current
pricing. Example values below are illustrative limits, not asserted prices:

```json
{
  "kind": "openai",
  "model": "YOUR_JSON_MODE_COMPATIBLE_MODEL",
  "base_url": "https://api.openai.com/v1",
  "api_key_env": "OPENAI_API_KEY",
  "approved": true,
  "max_calls": 1,
  "max_cost_usd": 0.10,
  "input_usd_per_million": 1.0,
  "output_usd_per_million": 2.0,
  "max_output_tokens": 2048,
  "max_input_bytes": 16384,
  "timeout_seconds": 60
}
```

Set `OPENAI_API_KEY` in the invoking environment without putting it in the
configuration, shell history, logs or Git. Pass `--provider-config` to campaign
execution. The CLI places the persistent provider reservation ledger under the
private runtime root, not the repository. Campaign provider and currency budgets
must also permit the operation. Start with one hypothesis and one call; the full
multi-role lifecycle needs its own finite role-call allocation.

The working CLI form is:

```sh
butterfly-lab --root "$BUTTERFLY_LAB_HOME" campaign run /path/to/private-campaign.json \
  --dataset /path/to/development-manifest.json \
  --provider-config /path/to/private-provider.json --wait
```

The campaign must declare `provider: "openai"`, `approved: true`,
`budget.currency: "USD"`, positive `budget.llm_currency` and `budget.llm_tokens`.
The one-call example above deliberately stops at its call limit; for a complete
one-hypothesis multi-role run authorize a finite larger call/token allocation
(normally at least seven calls, plus any single malformed-output correction).
Both the provider-wide and campaign-specific persisted reservations apply.
Using INR without an explicit conversion is rejected rather than silently
equating it to USD. A live-provider campaign cannot silently use fixture output.

The adapter reserves a conservative text-token upper bound before sending. A
failed, refused, malformed or timed-out response does **not** release that
reservation because the remote service may have billed it. The ledger is
interprocess locked and survives a fresh adapter instance. No implicit retries,
redirects, zero-price assumptions or automatic budget top-ups occur.
Malformed schema output permits at most one bounded format-correction call, also
reserved and logged. Economic disappointment never causes a correction loop.

The request uses JSON mode plus local strict Pydantic role validation; it does not
claim that server-side JSON mode itself enforces the full scientific schema.
Provider tools/function calling and generated Python execution are disabled.
Official API references used for the implementation:
[Chat Completions](https://developers.openai.com/api/reference/resources/chat),
[structured outputs and JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs).

## Inputs and review

Generation receives the campaign objective, verified capabilities, approved
source records, development-only diagnostics, evidence-linked prior findings and
a finite search count. Confirmation diagnostics and protected-confirmation prior
findings are rejected by the generator. Data paths, raw datasets and credential
fields are rejected from every role context. Literature and repository content
are evidence, never executable instructions.

`configs/seeds.json` contains all twelve proposal questions as complete validated
specifications. `load_seeds` namespaces IDs by campaign. Required capabilities are
real constraints: missing option identity, high-frequency observations or
multi-index synchronization does not get synthesized to make a seed runnable.

Deduplication distinguishes exact scientific identity, parameter/policy variants,
semantic-review candidates and new questions. Canonical hashes, token-set semantic
similarity, feature overlap and optional development-only behaviour comparisons
are deterministic. All aliases and variants retain registry lineage. Semantic
similarity alone never silently merges a hypothesis.

## Offline verification

```sh
python -m pytest tests/test_providers.py tests/test_agents.py tests/test_dedup.py -q
```

These commands run from `agent/` after installing its locked environment. They
make no real-provider requests and spend no API budget.
