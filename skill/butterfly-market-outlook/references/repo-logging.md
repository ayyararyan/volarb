# Private recordkeeping workflow

Use this workflow after every completed Butterfly Market Outlook run. The source
repository `ayyararyan/volarb` is not a destination for market reviews, account data
or personal financial records.

Configure an authorized **private journal root outside the source checkout**. All
`market-outlook/` and `trade-log/` paths below are relative to that private root.
Use the existing private store when available; do not create a remote repository,
change access controls or schedule work implicitly. If no private destination is
configured, report recordkeeping as blocked; never fall back to public GitHub.

Use Asia/Kolkata timestamps throughout.

## Accounting and authority boundary

This is the **private research and lifecycle recordkeeping workflow**, not the live accounting writer. The sole live book is the external configured `Trading/ledger/` shared-writer store (`simple_ledger.csv`, `butterfly_reviews.json`, `tradelog.csv`). Journal records are historical research projections, never fresh positions, order state or an alternate live ledger.

Use one stable butterfly **cycle ID through adjustments/recenters**. A verified fully closed cycle followed by a fresh entry gets a new ID. Reconcile actual fills and accounting through the local shared writer before recording the corresponding private lifecycle facts. Preserve historical records in private storage; do not restore them into public source during maintenance.

Generic CARRY fields below preserve schema/history; the adopted personal covenant prohibits overnight carry. Unchanged and blocked checks are journal-worthy. Recordkeeping must never delay a time-sensitive risk decision.

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
   - all relevant option legs have verified zero remaining units and no pending strategy orders; reconcile broker-confirmed fills rather than infer closure from disappearing positions;
   - finalize gross realized P&L when available and distinguish it from net-after-charges P&L.

## 2. One market-outlook markdown file per day

Path relative to the configured private journal root:

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
| Intraday HF RV state | when used: horizon, HF quality, continuous/jump-adjusted/upper RV, IV anchor, jump state, drift state, short-gamma state |
| News filter | calibration status/as-of, aggregate state, dominant channels, max gap risk/latency when material |
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
- Record only compact Market News Signal Filter outputs; never dump the raw article corpus or headline list.
- When the intraday HF RV gate is used, persist its compact packet and later append the realized variance over the exact forecast horizon when available; do not store raw tick data in GitHub.
- When the overnight gate is active, record next-actionable-exit horizon, broker feasibility/warning status, child-filter latency severity, same-state open harvest, 1.5S/2.0S stress P&L and OCR_1_5 when available.
```

Do not dump the entire raw chain or every web headline into the daily file. Capture the decision-relevant state.

For a candidate search, list the returned candidate(s) or NO TRADE reason inside the section.

## 3. Safe append procedure

Before modifying a daily file:

1. Resolve the authorized private journal root and verify it is outside the source checkout.
2. Read the latest file from that store; create it only if absent.
3. Use the store's existing lock/version checks and atomic-write procedure.
4. Append the new timestamped section; preserve earlier entries and avoid duplicate events.
5. If concurrent updates conflict, reread once, append only the missing section and retry once.
6. Verify persistence and record a private receipt (event ID or content hash).

Never claim a record was saved unless the private write succeeds. Do not push the
record, a financial excerpt or its private storage path to public GitHub.

## 4. Private historical trade summary

Private journal summary (not the live ledger), relative to its root:

`trade-log/trades.csv`

Use one summary row per confirmed butterfly cycle, retaining the same ID through adjustments.

Existing columns are:

`trade_id,instrument,strategy,opened_at_ist,closed_at_ist,status,expiry,lower_strike,body_strike,upper_strike,quantity,entry_credit_points,exit_cost_points,realized_pnl_inr,provenance,notes`

### Trade ID

Use:

`YYYY-MM-DD-SYMBOL-NNN`

where NNN increments for a new cycle after verified closure/re-entry in the same symbol on the same date. It does not increment merely because the current cycle changes geometry.

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

For each executed trade, maintain within the private journal root:

`trade-log/trades/<trade_id>.md`

Create it on confirmed entry. If an older trade already has its detailed history elsewhere, preserve that file and do not duplicate history unless migrating intentionally.

Recommended structure:

```markdown
# <trade_id> — SYMBOL butterfly

## Entry
- timestamp
- entry regime / BE-to-straddle / centre alignment when available
- compact intraday HF RV packet when used
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
2. retain the same cycle/trade ID and row; record the changed geometry and realized adjustment effects through the shared writer;
3. append the geometry transition and cumulative cycle context to that ID's `notes` and trade markdown;
4. record the execution in that day's market-outlook file.

A separately verified full closure followed by a fresh entry is re-entry and receives a new cycle ID. Never turn a RECENTRE recommendation or temporary geometry change into an invented closure/re-entry. Do not backfill execution merely because the model recommended it.

## 7. Post-trade episode

Private calibration file, relative to the private journal root:

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

Never publish to the source repository, Git history, issues, pull requests or release assets:

- tokens, API secrets, passwords, cookies or authentication artifacts;
- account/client identifiers, private infrastructure endpoints or workstation paths;
- personal position geometry, fills, trade P&L, financial ledgers or account snapshots;
- private market reviews, raw broker evidence or market datasets without publication rights.

The private journal may retain necessary confirmed trading facts under its existing
access controls. Sanitizing account IDs alone does not make financial records
public-safe. Source changes and deliberately synthetic fixtures may be published
through normal review; this workflow never authorizes public financial disclosure.

## 9. Ordering relative to the user-facing answer

For each run:

1. complete market/position analysis;
2. determine the final action;
3. persist the relevant daily/trade records;
4. emit the normal minimal one-table answer.

The private persistence receipt records the completed decision; it is not an
input that should distort the decision. No GitHub commit is required for a market
review, and no private record is a source-code contribution.

If logging fails after one conflict-safe retry, do not delay or suppress a time-sensitive risk decision. Return the normal decision and add one concise logging-failure note after the table.
