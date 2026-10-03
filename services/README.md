# Services

| Service | Ownership and status | Start here |
|---|---|---|
| `dhan-chatgpt-mcp/` | Reusable Dhan Provider + read-only research MCP + retained compatibility executor; live mutations disabled by default | [Provider/service README](dhan-chatgpt-mcp/README.md) |
| `day-workflow/` | Volarb-specific research composition, shadow state machine and explicit shared accounting/read-only adapters | [Workflow README](day-workflow/README.md) |
| `essvi-dashboard/` | Optional read-only eSSVI/HAR research dashboard; external Shaurya and office-Mac integration required | [Dashboard README](essvi-dashboard/README.md) |

The reusable [Execution Engine](../execution-engine/README.md), its
[Execution Testbed](../execution-testkit/README.md), and
[architecture manifests](../architecture/README.md) are separate concerns. No service
is automatically started by source installation or repository publication. Private
credentials, evidence, broker state and financial ledgers remain outside source.
