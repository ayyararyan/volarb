# Superseded — former Dhan-specific Box 5 design

This file is retained only as a historical pointer.

The architecture was corrected on 2026-10-03:

- `[5,0,0,0,0]` is now the **Broker-Neutral Optimal Execution Layer**.
- Dhan is an external provider plug-in beneath the broker execution port and has no Volarb Box number / VID.
- Broker-neutral execution optimization must not be duplicated separately for Dhan, Kotak, ICICI Securities, or future brokers.

Active documents:

- [Box 5 — Broker-Neutral Optimal Execution](05-optimal-execution.md)
- [Dhan Execution Provider Plug-in](../providers/dhan-execution.md)

The earlier Dhan-specific Box 5 concept is superseded and must not be used for new architectural work.
