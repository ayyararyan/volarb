# Historical archive — not operational

This archive preserves superseded designs and dated implementation snapshots. It is **not a source of current trading authority, broker truth, runnable production code or deployment configuration**. Active entrypoints are in the [repository map](../docs/REPOSITORY_MAP.md).

| Generation | Why preserved | Current replacement |
|---|---|---|
| [Architecture](architecture/README.md) | Original single-owner VID assumptions and the 2026-10-03 evolving design notebook | [Architecture index](../architecture/README.md), [current notes](../notes.md) |
| [Research](research/README.md) | Initial laboratory audit/verification snapshots superseded by later implemented capabilities | [Research laboratory](../agent/README.md) |
| [Deployment](deployment/README.md) | Policy for the retired automated housekeeping workflow | [.github workflows](../.github/workflows), [validation guide](../docs/VALIDATION.md) |

## Preservation rules

- Archive by conceptual owner and historical generation, not a single miscellaneous dump.
- Each archived directory states its active period, replacement and execution status.
- Keep historical assertions as history; do not silently rewrite old designs into modern ones. Add a notice and repair relocated navigational links when needed.
- Preserve working compatibility imports, aliases and entrypoints in their active locations with explicit replacement pointers.
- Keep dated market/trade records in their established journal paths. They were not rewritten or relocated by this cleanup.
- Never archive credentials or private runtime state. No archived configuration should be enabled as part of setup.
