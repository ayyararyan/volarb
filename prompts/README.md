# Prompt library — butterfly workflow

Copy-paste prompts for Aryan to send to Dhandho. Each file is one prompt for one step of
[docs/DAILY_OPERATING_ALGORITHM.md](../docs/DAILY_OPERATING_ALGORITHM.md). The prompts do not loosen any gate:
Dhandho still runs the full first-terminal-gate controller, publishes the journal entry, and replies with one table.
Aryan executes; nothing here places orders or starts monitoring.

Added 2026-09-30.

## Morning sequence (trading day)

| ID | When (IST) | Prompt | Reply |
|---|---|---|---|
| [PR01](PR01-morning-session-vrp-screen.md) | before 09:30 | Session VRP screen | one row: FAVOURABLE / UNFAVOURABLE / UNKNOWN |
| [PR02](PR02-candidate-search.md) | 09:45–09:55, only if PR01 was FAVOURABLE | Candidate search | Mode C table: up to three candidates or NO TRADE |
| [PR03](PR03-confirm-entry.md) | right after fills | Confirm entry, record trade | trade ID row |

## During an open position

| ID | When (IST) | Prompt | Reply |
|---|---|---|---|
| [PR04](PR04-open-position-review.md) | every 30 min (15–20 min when MARGINAL) | Review open butterfly | Mode A row: HOLD / SQUARE OFF |
| [PR05](PR05-square-off-and-closure.md) | after squaring off | Closure record | closure row with gross P&L and commit hash |
| [PR06](PR06-re-entry-fresh-pass.md) | after a same-session square-off, before 15:00 | Re-entry fresh pass | Mode C table, inherits day's loss |

## Other bounded checks

| ID | When (IST) | Prompt | Reply |
|---|---|---|---|
| [PR07](PR07-anytime-status-check.md) | authorized review window / objective emergency | Status check: positions, orders, loss vs budget, gate health | status row, no trade decision |
| [PR08](PR08-market-closed-outlook.md) | pre-open or after 15:30 | Market-closed outlook | Mode C with `pre-open watchlist` or NO TRADE / LOCKED OVERNIGHT |
| [PR09](PR09-end-of-day-summary.md) | after 15:00 | End-of-day summary and journal | summary table and commit hash |
| [PR10](PR10-tooling-readiness-check.md) | before PR01, or when a gate keeps failing | Tooling readiness: token, MCP, dashboard, sampler | one row per component |

## How to use

1. Open the file, copy the block under **Prompt**, paste it to Dhandho.
2. Fill in anything in `<angle brackets>` before sending; session loss must be verified, and user-provided fills/prices remain subject to broker reconciliation.
3. Read the single table. NO TRADE means no trade. A blocked gate is NO TRADE.
4. Run the next prompt in sequence only when its precondition holds (listed in each file).

## What the prompts never do

- They do not authorize orders, monitoring, schedulers or the optional executor.
- They do not substitute journals or trade logs for fresh Dhan positions and orders.
- They do not skip the ₹1,000 daily loss budget, the ₹1,000 free-cash margin reserve, or the 15:00 IST flat deadline.
