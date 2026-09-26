# Personal Butterfly Trading Governance Covenant
## Self-Imposed Trading License and Operating Notice

**Status:** Binding personal operating policy  
**Scope:** Personal butterfly trading in Indian index options  
**Timezone:** Asia/Kolkata (IST)  
**Effective:** Upon adoption and commitment to the `main` branch of this repository  
**Version:** 1.0

---

## 1. Nature and Purpose

This document is a private self-governance instrument governing the conduct of my personal butterfly trading.

Its purpose is not to maximize the number of trades, maximize time spent observing markets, or require participation in every trading session. Its purpose is to permit trading only within a deliberately bounded decision process that protects capital, attention, research time, and psychological bandwidth.

Accordingly, the governing principle is:

> **Trading is permitted only when a decision is actually required. Outside an authorized decision window, the trading task is closed mentally and operationally.**

This document constitutes a **self-imposed trading license**: permission to trade is conditional upon compliance with the rules below.

### Legal and operational notice

This document is not a statutory, regulatory, exchange, broker, advisory, portfolio-management, or investment-management license. It creates no rights or obligations for any third party and is not intended to constitute legal, tax, investment, or regulatory advice.

Its force is personal and procedural: it defines the conditions under which I authorize myself to engage in this trading activity.

---

## 2. Definitions

For purposes of this Covenant:

- **Trading Day** means a session in which Indian index options are available for trading.
- **Butterfly** includes the butterfly or iron-butterfly structures governed by the volarb / Butterfly Market Outlook workflow.
- **Review Window** means a deliberately scheduled period in which the position, market state, and required decision are examined.
- **Emergency Review** means an unscheduled review activated only by an objective material-risk trigger defined below.
- **Flat** means that all butterfly exposure governed by this Covenant has been closed and no residual position remains.
- **HOLD** means a deliberate decision to retain an existing position until a specified next review.
- **Rulebook** means this Covenant and any later version validly adopted under the amendment provisions below.

---

# Part I — Conditions of the Trading License

## Rule 1 — Intraday Trading Only

Until this Covenant is deliberately amended:

> **No butterfly position may be carried overnight.**

Every butterfly position must be closed during the same trading session in which it is opened or, if an existing position is encountered under a prior policy, during the current session at the first appropriate execution opportunity consistent with risk management.

This rule exists because:

1. overnight positions impose disproportionate psychological and attentional costs; and
2. gap, event, and discontinuous-price risk make overnight short-gamma exposure undesirable under the present policy.

No discretionary exception is permitted merely because a particular trade appears unusually attractive, inexpensive to carry, or likely to benefit from additional theta.

Any future authorization for overnight carry must result from a deliberate amendment to this Covenant made outside the pressure of a live position.

---

## Rule 2 — Hard Flat-Position Deadline

> **All butterfly positions must be fully closed no later than 3:00 PM IST.**

After 3:00 PM IST:

- no butterfly position may remain open;
- no recentering may be initiated;
- no fresh entry may be initiated;
- no "one last trade" is permitted;
- no position may be extended because remaining theta appears attractive.

At 3:00 PM IST, the trading day is operationally complete for purposes of this strategy.

The purpose of this deadline is to create a genuine closing bell before the exchange itself closes and to eliminate end-of-day bargaining with the rulebook.

---

## Rule 3 — Continuous Market Watching Is Prohibited

The trading terminal, option chain, live P&L, and equivalent market-monitoring interfaces must not remain continuously visible merely because a position exists.

Trading may be reviewed only:

1. during a scheduled Review Window; or
2. pursuant to a valid Emergency Review trigger under Rule 6.

If the next review is scheduled for 10:30 AM, ordinary market movement at 9:47, 9:53, 10:04, 10:11, or similar intermediate times does not create a new decision obligation.

Between Review Windows:

> **The trading task is closed.**

A change in mark-to-market P&L, standing alone, is not permission to reopen the task.

---

## Rule 4 — Every Review Must Resolve the Next Decision Point

The first formal review of the day may ordinarily occur around **9:20 AM IST**, after initial price discovery has begun.

Every completed Butterfly Market Outlook review must terminate in one of the following states:

- a next review scheduled for a specific time;
- a next review tied to a specific decision-relevant event;
- SQUARE OFF;
- NO TRADE.

An undefined state such as:

> "I will keep watching and see what happens"

is not an authorized outcome.

If the decision is HOLD, the next review point must be explicitly established before the Review Window ends.

---

## Rule 5 — Review Windows Must Remain Short

A normal scheduled Review Window should ordinarily last approximately **5–15 minutes**.

Within that window, the required sequence is:

1. obtain the current position and market state;
2. run the Butterfly Market Outlook workflow;
3. make the required decision;
4. execute only if necessary;
5. record the review;
6. schedule the next review when applicable;
7. close the trading screens.

The Review Window ends when the decision has been made and operational actions have been completed.

Continuing to stare at P&L after the decision is made is outside the authorized trading process.

---

## Rule 6 — Emergency Reviews Require Objective Triggers

A review may occur before its scheduled time only upon a predefined material trigger, including:

- a broker or RMS warning;
- an execution, fill, margin, or position anomaly;
- a material price movement threatening a butterfly break-even or wing;
- a significant volatility-surface or liquidity dislocation;
- a genuinely material scheduled or unscheduled market event;
- another hard risk trigger recognized by the Butterfly Market Outlook workflow.

The following are expressly **not** Emergency Review triggers:

- anxiety;
- curiosity;
- boredom;
- discomfort with not knowing the current P&L;
- an urge to "just check once";
- a desire to confirm that the earlier decision still feels comfortable.

---

## Rule 7 — P&L Is an Output, Not an Independent Signal

Current rupee P&L must not independently determine whether a butterfly is held, recentered, or exited.

Decisions must arise from the trading framework, including as relevant:

- market state;
- position geometry;
- executable economics;
- Greeks;
- gamma and path risk;
- liquidity;
- expiry conditions;
- event risk;
- predefined exit and recenter rules.

Accordingly:

> **"I am down ₹X" and "I am up ₹Y" are observations, not trading theses.**

P&L may describe the consequence of the position. It does not, by itself, authorize a decision.

---

## Rule 8 — Unscheduled Strategy Research During Market Hours Is Prohibited

Market hours are for executing an already defined process.

They are not an authorized period for spontaneously developing or investigating:

- a new butterfly construction;
- a new volatility model;
- a new arbitrage idea;
- a new Greek or carry ratio;
- an entirely different options strategy;
- a material redesign of the live decision framework.

An interesting observation may be captured in one sentence for later investigation.

Research belongs outside live trading Review Windows.

---

## Rule 9 — Every Material Decision Must Be Recorded

Every completed:

- market outlook;
- candidate search;
- scheduled position review;
- NO TRADE decision;
- confirmed entry;
- confirmed recenter;
- confirmed closure

must be recorded through the existing **volarb GitHub workflow**.

The daily record should preserve, where applicable:

- timestamp;
- position;
- decision;
- important market state;
- reason;
- next review.

Confirmed executions must additionally update the relevant durable trade records.

The journal exists so that trading knowledge accumulates in a persistent system rather than remaining dependent on memory.

---

## Rule 10 — Closing the Position Closes the Cognitive Loop

When the final butterfly position for the day is closed:

1. confirm that the position is flat;
2. record the closure;
3. record realized P&L when available;
4. note any immediate factual observation worth preserving;
5. stop.

Repeated post-mortem analysis during the remainder of the working day is not part of the live trading process.

Detailed research, attribution, model revision, and post-trade analysis belong to a separate scheduled calibration or research session.

---

## Rule 11 — Weekends Are Trading-Free

Saturday and Sunday are protected from live-position anxiety.

Because overnight carry is prohibited, every weekend must begin with:

> **Zero open butterfly positions.**

Weekend trading work, if any, is limited to deliberate research, calibration, coding, record maintenance, or periodic strategy review.

There is no obligation to monitor markets merely to speculate about Monday.

---

## Rule 12 — Trading Does Not Outrank the Rest of Life Outside Its Window

During an authorized Review Window, trading receives full attention.

Outside that window, it loses priority completely.

The fact that an exchange is open does not grant trading a claim on the entire 9:15 AM–3:30 PM period.

Between scheduled reviews, attention may return normally to:

- FIR work;
- PhD applications;
- Queue Priority research;
- other pre-existing work and life commitments.

An open market is not an open-ended attentional mandate.

---

## Rule 13 — Review Frequency May Not Be Increased Because of Anxiety

If repeated checking begins to reappear, the remedy is not to create additional scheduled checks.

Review frequency may increase only because the trading framework identifies a genuine decision-relevant reason, such as:

- approaching expiry;
- a threatened break-even;
- a scheduled event;
- an abnormal market state;
- materially increased gamma or path risk.

In the absence of such a reason, the existing review schedule remains in force.

---

## Rule 14 — No Spontaneous Re-entry After Deliberate Closure

Once the day's butterfly has been deliberately closed, another entry is not automatically authorized merely because a new opportunity appears.

Any subsequent entry requires a fresh candidate evaluation under the full Butterfly Market Outlook workflow.

After **3:00 PM IST**, re-entry is prohibited without exception under the current Covenant.

---

## Rule 15 — The Default State Is NO POSITION

Being flat is not a deficiency, missed opportunity, or inactivity requiring correction.

There is no requirement to trade every day.

If no candidate survives the Butterfly Market Outlook gates:

> **NO TRADE is a successful trading decision.**

The burden of proof rests on taking risk, not on remaining flat.

---

# Part II — Daily Operating Protocol

## A. Before Market

Do not compulsively monitor global markets, pre-market indications, option prices, or hypothetical P&L.

Perform only the preparation required for the day's first formal review.

## B. Initial Review — Approximately 9:20 AM IST

Run the initial Butterfly Market Outlook workflow.

The review must end in an explicit state:

> **NO TRADE / candidate / existing-position decision**

If a position exists or is entered, establish the next review point immediately.

## C. Between Reviews

Close trading screens.

Return to the broader priority system, including as applicable:

1. FIR;
2. PhD applications;
3. Queue Priority research.

No trading activity is required until the next authorized decision point unless a valid Emergency Review trigger occurs.

## D. At Each Scheduled Review

Run the workflow, decide, execute if required, log the outcome, establish the next review when applicable, and leave the trading environment.

## E. By 3:00 PM IST

Be completely flat.

## F. After 3:00 PM IST

Trading is closed for the day.

No further P&L monitoring, overnight-market anxiety, re-entry, or reconsideration of the closed position is part of the authorized process.

---

# Part III — Governance, Amendment, and Enforcement

## 16. No Intraday Waiver

No live trade, market move, profit opportunity, loss, instinct, or change of mood may temporarily waive any provision of this Covenant.

A rule that can be suspended merely because the present trade feels exceptional is not a rule.

---

## 17. Amendment Procedure

This Covenant may be changed only deliberately.

A valid amendment must:

1. be considered outside the pressure of an active live-position decision;
2. be written explicitly;
3. state the rule being changed and the intended replacement;
4. be version-controlled in this repository;
5. be committed to the `main` branch before the amended rule becomes operational.

A change invented during a live trade does not become valid merely because it appears reasonable at that moment.

---

## 18. Breach Handling

A breach of this Covenant is to be treated as a process failure, not as permission for further discretionary trading.

If a breach is identified:

1. protect against any immediate trading risk;
2. return to compliance as soon as operationally possible;
3. record the factual breach without rationalization;
4. do not attempt to "earn back" a loss or justify the breach through another trade;
5. defer any rule change or post-mortem to a later non-live review.

The objective is restoration of process, not punishment.

---

## 19. Precedence

Where discretionary preference conflicts with this Covenant, this Covenant governs.

Where this Covenant and the formal Butterfly Market Outlook risk engine address the same decision, the stricter applicable constraint governs unless this Covenant has been deliberately amended.

In particular, the **3:00 PM IST flat-position deadline** and **no-overnight-carry rule** are personal hard limits under the present version even if another analytical framework would otherwise permit carry.

---

## 20. Duration

This Covenant remains in force until expressly superseded by a later version adopted under Rule 17.

Silence, non-use, a profitable exception, or failure to follow a rule on one occasion does not repeal or amend it.

---

# Personal Authorization

I authorize myself to engage in butterfly trading only on the conditions stated in this Covenant.

The permission to trade is therefore conditional, bounded, and revocable by the rules themselves.

The central operating principle is:

> **If I am not currently at a scheduled decision point, there is nothing for me to do about the market.**

---

**Adopted for personal use.**  
**Repository of record:** `ayyararyan/volarb`  
**Branch of record:** `main`
