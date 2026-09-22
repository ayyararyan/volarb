# Repository logging workflow

Use this workflow as a backend side effect of every completed Butterfly Market Outlook run when the GitHub connector is writable.

Canonical repository: `ayyararyan/volarb`

Canonical branch: `main`

Use Asia/Kolkata timestamps throughout.

## 1. Event classes

Treat these as journal-worthy events:

1. **Market outlook / candidate search**
   - no live position is required;
   - includes NO TRADE decisions and ranked candidate searches.

2. **Open-position review**
   - includes HOLD, RECENTRE, SQUARE OFF, CARRY and any check of a live carried butterfly;
   - includes scheduled/manual rechecks even when the decision is unchanged.

3. **Confirmed trade entry**
   - Dhan shows a new live structure, or the user explicitly confirms that the trade was executed;
   - do not treat a recommendation as an executed trade.

4. **Confirmed recenter**
   - only after Dhan/user evidence shows the old geometry was closed/changed and the new geometry was actually opened;
   - a RECENTRE recommendation by itself is not an execution event.

5. **Confirmed closure**
   - all relevant option legs are closed / net quantity is zero, or the user provides broker-confirmed closure;
   - finalize gross realized P&L when available and distinguish it from net-after-charges P&L.

## 2. One market-outlook markdown file per day

Path:

`market-outlook/YYYY-MM-DD.md`

There is exactly **one file per IST calendar day**, shared across NIFTY, BANKNIFTY and SENSEX.

### First write of the day

If the file does not exist, create it with:

```markdown
# Butterfly Market Outlook — YYYY-MM-DD

Timezone: Asia/Kolkata

This file is appended throughout the trading day. Each section records the market state and decision as it was known at that timestamp.
```

### Every completed outlook/review

Append one section in chronological order:

```markdown
## HH:MM IST — SYMBOL — EVENT TYPE

| Field | Value |
|---|---|
| Decision | HOLD / RECENTRE / SQUARE OFF / CARRY / NO TRADE / candidate |
| Expiry | YYYY-MM-DD or unknown |
| Position | concise geometry or none |
| Trade ID | active trade ID if one exists, otherwise — |
| Spot / forward | values if available |
| Data health | HEALTHY / DEGRADED / STALE / INVALID |
| Key surface state | short skew/IV/RND description |
| Key path/event state | short real-world risk description |
| Position economics | bankable P&L, dynamic harvest, Greeks or other decision-critical metrics when available |
| Why | the concrete reason behind the final decision |
| Next review | IST timestamp/event/close or — |
| Provenance | Dhan / exchange / web / user-supplied / mixed |

### State change since prior review
- Only list material changes.
- If this is the first review of the day or no comparable prior state exists, write `Initial snapshot`.

### Notes
- Record only details useful for later research/calibration.
- Keep risk-neutral and real-world probabilities conceptually separate.
```

Do not dump the entire raw chain or every web headline into the daily file. Capture the decision-relevant state.

For a candidate search, list the returned candidate(s) or NO TRADE reason inside the section.

## 3. Safe append procedure

Before modifying a daily file:

1. Fetch the latest file from `main`.
2. If absent, create it.
3. If present, use its current blob SHA for the update.
4. Append the new section; do not replace earlier entries.
5. Use a commit message such as:
   - `Log 2026-09-22 11:20 IST NIFTY outlook`
   - `Log 2026-09-22 14:40 IST NIFTY position review`
6. If a SHA conflict occurs, refetch once, merge by appending the missing section, and retry once.

Never claim a log was written unless the GitHub write succeeds.

## 4. Trade ledger

Canonical ledger:

`trade-log/trades.csv`

Use one row per executed butterfly episode.

Existing columns are:

`trade_id,instrument,strategy,opened_at_ist,closed_at_ist,status,expiry,lower_strike,body_strike,upper_strike,quantity,entry_credit_points,exit_cost_points,realized_pnl_inr,provenance,notes`

### Trade ID

Use:

`YYYY-MM-DD-SYMBOL-NNN`

where NNN increments if more than one distinct butterfly is opened in the same symbol on the same date.

### On confirmed entry

Create or update the row with every known field.

Use broker/Dhan truth when available. Otherwise use explicit user-supplied fills/geometry.

Unknown fields stay blank.

Do not infer:
- quantity;
- entry credit;
- fills;
- realized P&L;
- exact expiry;
- strikes that are unreadable or unconfirmed.

### On a position check

Do not rewrite the ledger row merely because mark-to-market changed. The ledger is for durable trade facts.

Instead:
- log the review in the daily market-outlook file;
- update the trade-specific markdown record when a material decision/state transition occurs.

### On closure

Set:
- `status=closed`;
- `closed_at_ist`;
- `exit_cost_points` if known;
- `realized_pnl_inr` if known.

Clearly state whether P&L is gross or net of charges in `notes`.

## 5. Trade-specific markdown record

For each executed trade, maintain:

`trade-log/trades/<trade_id>.md`

Create it on confirmed entry. If an older trade already has its detailed history elsewhere, preserve that file and do not duplicate history unless migrating intentionally.

Recommended structure:

```markdown
# <trade_id> — SYMBOL butterfly

## Entry
- timestamp
- expiry
- geometry
- quantity
- fills / credit
- data provenance
- entry thesis

## Review history
### YYYY-MM-DD HH:MM IST
- Decision:
- Market-state change:
- Position-state change:
- Key risk/carry metrics:
- Next review:

## Recenter history
- Only confirmed executions, never recommendations.

## Closure
- timestamp
- leg-level realized P&L when known
- gross realized P&L
- costs / net P&L when known
- final net quantity
```

For an active trade, append only material position-state/decision changes; the daily outlook remains the complete chronological review stream.

## 6. Recenter handling

A RECENTRE recommendation is recorded only as a decision in the daily file.

If the recenter is actually executed:

1. finalize the old geometry's close facts if known;
2. create a new trade row for the newly opened geometry unless the user explicitly wants the recentered structure treated as one accounting episode;
3. link the two IDs in each row's `notes` and in the trade markdown;
4. record the execution in that day's market-outlook file.

Do not backfill execution merely because the model recommended it.

## 7. Post-trade episode

Canonical calibration file:

`trade-log/episodes.jsonl`

After full closure, create or update one JSON object for the completed trade.

Include, when known:
- trade ID;
- geometry;
- opening and closing timestamps;
- holding profile;
- gross/net realized P&L;
- leg-level realized P&L;
- decision sequence;
- material MarketState changes;
- recenter history;
- model changes/lessons;
- provenance;
- unknown fields.

Do not create numerical calibration fields from guessed fills.

Avoid duplicate JSONL objects for the same `episode_id`. Fetch first and replace/update the matching object if it already exists.

## 8. Sensitive-data rule

Never commit:
- Dhan access tokens;
- API secrets;
- passwords;
- full account/client identifiers;
- private authentication URLs;
- unrelated personal financial information.

Position geometry, fills, trade P&L, option analytics and market research are allowed when they are part of this trading journal.

## 9. Ordering relative to the user-facing answer

For each run:

1. complete market/position analysis;
2. determine the final action;
3. persist the relevant daily/trade records;
4. emit the normal minimal one-table answer.

The GitHub commit is a record of the completed decision, not an input that should distort the decision.

If logging fails after one conflict-safe retry, do not delay or suppress a time-sensitive risk decision. Return the normal decision and add one concise logging-failure note after the table.
