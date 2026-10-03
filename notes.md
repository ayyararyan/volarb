# Current architecture notes

Updated 2026-10-03. This is a navigation and decision summary, not a second specification or an execution mandate.

## Current decisions

- Execution Engine is reusable and strategy-agnostic: `component.execution_engine`, immutable `[5,0,...]`. `component.internal_execution` is a legacy alias only.
- Strategy → optional Strategy Execution Adapter → Execution Engine → Broker Execution Port → Dhan Provider (or another broker).
- Normal execution: Margin Optimization → Execution Slicing → Optimal Execution → Execution Recovery / Command Commit Guard → Broker Execution Port. State Integrity, Recovery and Interrupt Control apply across that path.
- Canonical component identities belong in [architecture/](architecture/README.md); Volarb owns its [composition](architecture/strategies/volarb/composition.json), not the engine or Dhan.
- Runtime ports/contracts, Dhan mechanics, simulator and test harness are implemented. The complete generic execution pipeline and live strategy orchestration are not.
- The same future pipeline must run with injected test/replay/shadow/production dependencies. Production must not depend on the testkit.
- The [current manual workflow](docs/DAILY_OPERATING_ALGORITHM.md) and [covenant](docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md) remain in force. Autonomous diagrams and inactive policy drafts do not enlarge trading authority.

## Canonical design and outstanding work

Start with the [repository map](docs/REPOSITORY_MAP.md), [Volarb strategy design](docs/autonomous-butterfly-workflow.md), [Execution Engine design](docs/workflows/execution-engine.md) and [open tasks](tasks.md). Methodology, latency budgets, concrete persistence/scheduling, strategy-to-execution integration and production rollout remain explicit development work, not broker readiness claims.

## Preserved evolution

The complete 1,432-line 2026-10-03 brainstorming/design notebook was moved intact (apart from an archival notice and relocated links) to [architecture design history](archive/architecture/design-notes/2026-10-03-autonomous-butterfly-notes.md). It records intermediate assumptions that were corrected later, including Dhan/strategy ownership of execution. Its old TODOs and commands are not current instructions.

The repository cleanup and verification record lives in [development history](docs/DEVELOPMENT_HISTORY.md) and the [audit report](docs/audits/2026-10-03-repository-cleanup.md). Historical personal journals, account records and trade results are preserved only in verified private storage after public-release preparation. The public source contains navigation notices and schemas, not those records. Future market/trade recordkeeping uses the [private journal contract](skill/butterfly-market-outlook/references/repo-logging.md), never public GitHub.
