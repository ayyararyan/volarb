# Butterfly VolArb Operating Workflow — Engine v2.5

Updated 2026-09-29. The [personal covenant](PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md) overrides generic CARRY eligibility. The [decision algorithm](../skill/butterfly-market-outlook/references/decision-algorithm.md) controls engine ordering.

## 1. Scope and clock

NIFTY, BANKNIFTY and SENSEX; Asia/Kolkata. Intraday only, flat by 15:00 IST, with no entry/recenter thereafter. Earlier broker/expiry cutoffs win. After market close residual exposure is LOCKED_OVERNIGHT, not an executable exit or permission to carry. Reviews are bounded decision windows; no implied monitoring or automatic exit.

## 2. Authenticate on the office Mac

Use [local web-token recovery](../services/dhan-chatgpt-mcp/README.md#office-mac-browser-token-recovery--2026-09-29) before broker access. Reuse a suitable token; recover missing/expired/rejected or short-lived tokens through Dhan Web. Verify identity before atomically updating the private MCP `.env`. No personal-Mac access or TOTP token generation. Revoke expired/superseded Dusty tokens only after replacement verification; preserve unrelated active keys. Human OTP/CAPTCHA challenges remain human steps. Close task-owned browser tabs/windows when finished, preserving cookies and unrelated tabs.

## 3. Establish fresh truth

Read positions AND outstanding orders. Reconcile signed units, contract identity, expiry and partial fills. Account failure is unknown exposure, never verified flatness or HOLD. Obtain one coherent relevant-expiry chain plus timestamped executable-side quotes and actual-leg liquidity. Do not use journals as account truth.

## 4. Run the first-terminal-gate controller

Invoke the news filter once per relevant horizon and reuse the normalized packet. Apply data health and post-close gates before later analysis. For intraday RV/drift, use the child skill's fresh approximately five-minute HF block for the next 15–30-minute horizon; session OHLC/prior-day RV cannot substitute. Discrete RND-mode bucket migration is corroborative only.

A new intraday candidate needs actionable FAVOURABLE RV/drift. For existing positions, medium/high-confidence UNFAVOURABLE is an exit signal; MARGINAL shortens the review window, and missing HF data alone does not force an exit. Hard event/tail/liquidity risk, expiry exit, recenter and optimization follow the canonical algorithm. Generic overnight branches are not permission to override the personal intraday covenant.

## 5. Select and verify margin

Use current-only wide-butterfly selection: executable quotes, theta/adverse gamma and disclosed modelled tail stress. No historical backtest or invented budget. Each exact-sized finalist requires a fresh `dhan_check_butterfly_margin` PASS with `reserveRupees: 1000` and no percentage reserve. Available funds must cover peak wings-first entry-stage requirement plus the reserve, not merely final margin or payoff maximum loss. Candidate geometry, expiry and lots must match the evidence.

The MCP packet is ENTRY_ONLY. An overlapping RECENTRE needs independently verified full close/reopen-transition margin; entry-only evidence cannot authorize it. Margin never overrides an earlier exit gate. Research affordability is not sizing/risk approval.

## 6. Accounting and publication

Maintain one row per butterfly cycle through verified closure using the existing local shared writer, `simple_ledger.csv`, nested `butterfly_reviews.json` and actual broker `tradelog.csv`. Same cycle ID through adjustments; new ID for re-entry. Never invent fills, profit or flatness. Repo trade records are historical evidence, not another live book.

Score prior forecasts and compare actions after costs under the local internal review guide; unvalidated forecasts remain shadow-only. Append each completed check, blocked check, outlook and decision to the daily repository journal, preserve previous entries, push `main` and verify publication. Retry a publication conflict once, then disclose any failure. Keep raw private evidence local.

## 7. Reply and execution boundary

Use one table in [Mode A/B/C](../skill/butterfly-market-outlook/references/output-template.md), with no outside prose unless explanation is requested. State the next decision window before the exit deadline without implying a reminder. Aryan executes; Dhandho never places/modifies/cancels orders. Source publication does not activate the optional executor, a scheduler, or monitoring.

## 8. Software checks

The packaging workflow runs all butterfly regressions, validates RV fixtures and packages all three skills. The service workflow installs locked dependencies and runs synthetic Node tests without Dhan credentials or browser sessions. Deployment and installed-skill refresh are separate explicit operations; GitHub is a source/journal destination, not live account state.
