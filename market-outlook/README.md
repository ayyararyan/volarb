# Daily market outlook journal

The Butterfly Market Outlook skill writes **one markdown file per IST trading/calendar day** into this directory.

File naming:

`YYYY-MM-DD.md`

Each file is append-only during the day and may contain NIFTY, BANKNIFTY and SENSEX sections. Every completed candidate search, market outlook and live-position review gets its own timestamped section.

The detailed write contract lives in:

[repository logging contract](../skill/butterfly-market-outlook/references/repo-logging.md)

Do not create separate per-symbol files unless the repository convention is explicitly changed later.

These are dated research/decision records, not fresh broker truth. Source cleanup preserves their contents and chronology. Raw private evidence and live accounting stay outside this repository.
