# Global Provider Error Contract

Status: **active**.

VID: **[0,0,1,7,1] Provider Error Envelope**

Canonical executable definitions live in
[`execution-engine/contracts/provider-error.mjs`](../../execution-engine/contracts/provider-error.mjs).
The Dhan [`src/provider-error.mjs`](../../services/dhan-chatgpt-mcp/src/provider-error.mjs)
path is a compatibility re-export, not a second contract. Provider-specific mapping
remains in [`dhan-error-mapper.mjs`](../../services/dhan-chatgpt-mcp/src/dhan-error-mapper.mjs).

This is a Volarb-global data contract. It is intentionally broker-neutral and may be consumed by any box that calls an external provider.

## Invariant

**No provider-native error may cross into a Volarb box unnormalized.**

Every provider implementation must map every failure into the Provider Error Envelope before returning control to its caller.

Known broker codes receive explicit mappings. New, undocumented or otherwise unmapped provider failures map to the global `UNKNOWN` category while retaining provider-native provenance. Therefore an unknown broker code is still a mapped Volarb error; raw provider exceptions are never the public contract.

## Stable categories

| Category | Meaning |
|---|---|
| `CONFIGURATION` | Provider is not configured or required provider-side mutation configuration is not ready |
| `AUTHENTICATION` | Credentials/token/client identity invalid, expired or unavailable |
| `AUTHORIZATION` | Authenticated but not permitted/subscribed/entitled |
| `ACCOUNT_STATE` | Account/segment/control state prevents the operation |
| `RATE_LIMIT` | Provider request/connection rate limit reached |
| `INVALID_REQUEST` | Invalid/missing/oversized/unsupported request parameters |
| `ORDER_REJECTED` | Broker/exchange definitively rejected an order operation |
| `DATA_UNAVAILABLE` | Requested provider data cannot be supplied |
| `RESOURCE_NOT_FOUND` | Requested provider resource/order/reference is not found |
| `PROVIDER_INTERNAL` | Provider/backend internal failure |
| `NETWORK` | Transport/network communication failure |
| `TIMEOUT` | Provider call exceeded its deadline |
| `PROTOCOL` | Provider response cannot be parsed/validated as the documented protocol |
| `UNSUPPORTED` | Provider lacks the requested capability |
| `UNKNOWN` | Catch-all for any failure not yet explicitly classified |

The category set is deliberately small and semantic. Provider-specific detail belongs in provenance, not in global control flow.

The global configuration codes currently include:

- `PROVIDER.NOT_CONFIGURED` — minimum provider identity/credential configuration is absent;
- `PROVIDER.MUTATION_NOT_READY` — a requested mutation is blocked before transmission because provider-side mutation readiness is not satisfied (for example Dhan static-IP readiness).

Both are broker-neutral codes. Another broker may reach the same codes through different native configuration requirements.

## Envelope

Serialized errors carry:

```text
contractVersion
category
code
message
operation
kind = COMMAND | QUERY | STREAM
outcome = NOT_APPLICABLE | KNOWN_NOT_APPLIED | UNKNOWN
observedAt
provider {
    key
    nativeCode
    nativeType
    nativeMessage
    httpStatus
    omsCode
    omsDescription
    path
}
```

The provider block is diagnostic provenance. Caller behavior must key off the global fields, not a Dhan/ICICI/Kotak code.

## Command-outcome certainty

Error class and mutation certainty are separate concepts.

- `NOT_APPLICABLE`: the failed operation was a query/stream rather than a mutation.
- `KNOWN_NOT_APPLIED`: the provider definitively rejected/refused the command before the requested economic mutation was applied.
- `UNKNOWN`: the command may have been transmitted/applied but acknowledgement is insufficient, such as transport loss, timeout, unreadable response or uncertain provider/internal failure.

`UNKNOWN` is not permission to retry. It is information for the caller's recovery/reconciliation policy.

## Provider implementation rule

Each broker adapter owns exactly one mapping layer:

```text
native broker failure
        |
        v
broker-specific mapper
        |
        v
[0,0,1,7,1] Provider Error Envelope
        |
        v
any Volarb caller
```

Adding ICICI Securities, Kotak, or another provider therefore means implementing that provider's native-code mapping into this same contract. Callers do not change.

## Dhan mapping

The Dhan mapper is exhaustive over currently documented DhanHQ v2 Trading API and Data API codes, plus transport/HTTP fallbacks. Any future Dhan code automatically falls into `UNKNOWN` until explicitly promoted to a more precise mapping.
