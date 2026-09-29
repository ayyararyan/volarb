# volarb

Research, decision logic, automation source and journals for NSE/BSE NIFTY, BANKNIFTY and SENSEX butterflies.

## Current setup

**Butterfly Market Outlook Engine v2.5**, with the live high-frequency realized-volatility/drift dependency, RND-mode bucket correction, and exact-candidate entry-margin verification.

The personal covenant overrides generic engine carry branches: **intraday only, flat by 15:00 IST, no entry or recenter thereafter**. Dhandho researches; Aryan executes. Publishing source does not enable trading or monitoring.

## Layout

- `skill/butterfly-market-outlook/` — controller, references, scripts and regressions.
- `skill/intraday-realized-volatility-forecast/` — five-minute HF observation model and fixtures.
- `skill/market-news-signal-filter/` — normalized event/news risk filter.
- `services/dhan-chatgpt-mcp/` — office-Mac MCP, browser web-token recovery, margin preflight, optional separately gated execution code and synthetic tests.
- `services/day-workflow/` — offline SHADOW state machine and lifecycle/failure tests; no live orders or jobs.
- `market-outlook/` — append-only daily research journals.
- `trade-log/` — historical trade records; never fresh broker truth or a second live ledger.
- `docs/WORKFLOW.md` — active personal operating workflow.
- `docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md` — governing covenant.
- `.github/workflows/` — skill packaging, synthetic service checks and conservative housekeeping.

## Boundaries

Fresh broker positions/orders and executable quotes precede recommendations. First terminal gate wins; attractive theta cannot override missing data or hard risk. Margin checks retain ₹1,000 free cash against peak entry-stage requirement; entry-only packets cannot approve an overlapping recenter. RND is a pricing measure, not a physical forecast.

Live financial accounting remains in the office-Mac VolArb `Trading/ledger/` shared-writer store. Credentials, PIN/mobile configuration, browser cookies, raw broker evidence and runtime logs stay local and are not published. Repository source updates do not automatically deploy to the service or refresh installed skills.

See [operating workflow](docs/WORKFLOW.md) and [service setup](services/dhan-chatgpt-mcp/README.md).
