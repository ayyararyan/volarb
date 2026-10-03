# Laboratory documentation

The laboratory is research-only. Live strategy decisions, generic broker execution
and this laboratory have separate authorities; begin with the [lab README](../README.md).

| Need | Canonical entrypoint |
|---|---|
| Install and configure providers | [Provider setup](providers.md), [configuration](configuration.md) |
| Operate finite campaigns and recover jobs | [Operations](operations.md), [job recovery](job-recovery.md) |
| Understand implemented orchestration | [Architecture and diagrams](architecture.md), [live lifecycle](live-research-lifecycle.md) |
| Scientific definitions and evidence limits | [Scientific contract](scientific-contract.md), [security and confirmation](security.md) |
| Current historical-data support | [Verified capabilities](real-data-capabilities.md) |
| Source discovery and measured research findings | [Dated discovery](real-data-discovery.md), [first real-data campaign](first-real-campaign.md) |
| Acceptance evidence and coverage | [Traceability](traceability.md), [dated Codex verification](codex-verification.md) |
| Machine-readable contracts and retained receipts | [Schemas](schemas/), [evidence index](evidence/README.md) |
| Superseded initial-release reports | [2026-10-02 archive](../../archive/research/laboratory/2026-10-02/README.md) |

Dated receipts describe the source and environment actually exercised then; their
test counts are not a claim about the current checkout. Generated schemas,
rendered diagrams and installed resource mirrors are intentional maintained
artifacts, verified by `python examples/check_generated.py` from `agent/`.
