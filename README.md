# volarb

Research, decision logic, automation source and journals for NSE/BSE NIFTY, BANKNIFTY and SENSEX butterflies.

## Current setup

**Butterfly Market Outlook Engine v2.6**, with a session variance-risk-premium gate, a daily loss-budget gate, a same-session re-entry gate, the live high-frequency realized-volatility/drift dependency (now with decision-clock freshness and mandatory news-packet validation), RND-mode bucket correction, and exact-candidate entry-margin verification.

**Start here on a trading day:** [docs/DAILY_OPERATING_ALGORITHM.md](docs/DAILY_OPERATING_ALGORITHM.md).

The personal covenant overrides generic engine carry branches: **intraday only, flat by 15:00 IST, no entry or recenter thereafter**. Dhandho researches; Aryan executes. Publishing source does not enable trading or monitoring.

## Layout

- `skill/butterfly-market-outlook/` — controller, references, scripts and regressions.
- `skill/intraday-realized-volatility-forecast/` — five-minute HF observation model and fixtures.
- `skill/market-news-signal-filter/` — normalized event/news risk filter.
- `services/dhan-chatgpt-mcp/` — office-Mac MCP, browser web-token recovery, margin preflight, optional separately gated execution code and synthetic tests.
- [services/essvi-dashboard/](services/essvi-dashboard/) — dark eSSVI surface, ATM IV, 1/5/22-session HAR forecasts and Q ratio; requires external Shaurya packages and local authentication.
- `services/day-workflow/` — offline SHADOW state machine and lifecycle/failure tests; no live orders or jobs.
- `market-outlook/` — append-only daily research journals.
- `trade-log/` — historical trade records; never fresh broker truth or a second live ledger.
- `docs/DAILY_OPERATING_ALGORITHM.md` — the one-page daily sequence and gate order.
- `docs/WORKFLOW.md` — standing operating rules behind that sequence.
- `docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md` — governing covenant.
- `.github/workflows/` — skill packaging, synthetic service checks and conservative housekeeping.

## Boundaries

Fresh broker positions/orders and executable quotes precede recommendations. First terminal gate wins; attractive theta cannot override missing data or hard risk. Margin checks retain ₹1,000 free cash against peak entry-stage requirement; entry-only packets cannot approve an overlapping recenter. RND is a pricing measure, not a physical forecast.

Live financial accounting remains in the office-Mac VolArb `Trading/ledger/` shared-writer store. Credentials, PIN/mobile configuration, browser cookies, raw broker evidence and runtime logs stay local and are not published. Repository source updates do not automatically deploy to the service or refresh installed skills.

See [operating workflow](docs/WORKFLOW.md) and [service setup](services/dhan-chatgpt-mcp/README.md).

## Portable agent kit

See [setup and diagnostics](docs/AGENT_KIT.md) and the [dependency inventory](docs/DEPENDENCY_INVENTORY.md).
The kit packages source, all three skills, the Dhandho profile, canonical accounting
writers and explicit read-only acquisition. Separate source/workspace/private-data
paths replace machine-specific runtime paths. Hash-locked Python and locked Node
dependencies install through `python3.12 tools/volarb.py setup`. Default SHADOW;
no service start, broker calls, ledger creation, schedules or execution activation.
`doctor` diagnoses gaps; `package` builds a source-only reusable archive.
Existing office-Mac deployment is unchanged; private state restoration is separate.
