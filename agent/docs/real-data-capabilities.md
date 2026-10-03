# Verified real-data capabilities

Fidelity follows the existing laboratory contract, not filenames. F4 remains
unsupported. F3 denotes bounded quote simulation, never an executable-fill claim.

| Capability | Source | Status |
|---|---|---|
| NIFTY one-minute spot OHLC with explicit start labels | Own aggregation of actual index updates | VERIFIED; F2; missing observations retained |
| Past-only RV and normalized drift | Qualified NIFTY spot bars | VERIFIED for fixed EXP-001 |
| Fixed historical NIFTY/BANKNIFTY/SENSEX identities | External raw archive samples; BANKNIFTY download metadata | YES; source/contract-specific qualification still required |
| Exact expiry / strike / CE-PE | Numeric weekly symbols; fixed BANKNIFTY request metadata | VERIFIED for selected weekly contracts; monthly calendars not guessed |
| Bid/ask and displayed quantity | External sparse top-of-book fields | PRESENT; requires prior-state reconstruction and clocks |
| Deeper order book | External levels 1–5 | PRESENT in samples; F4 replay NOT IMPLEMENTED |
| Fixed-contract OHLC / volume / OI | BANKNIFTY native active history | PRESENT; bar convention and gap qualification unresolved |
| OI | Raw derivative events and BANKNIFTY bars | PRESENT; not an IV or execution proxy |
| Historical IV / Greeks | Selected raw quote sources | NOT VERIFIED; model-derived values must remain distinct |
| Historical lot units | Selected January–February NIFTY quote records `ls=65` | Source-observed and corroborated by dated NSE circular |
| Exact historical broker margin | All discovered sources | UNKNOWN; any numerical reference must be labelled a research proxy |
| Full live-policy replay / historical news gates | Selected sources | NOT SUPPORTED; missing gate packets not invented |
| Rolling ATM lane held-position P&L | Reduced NIFTY option exports | INVALID; contract continuity absent |

## Registered manifests

| Dataset ID | Partition | Fidelity / qualification |
|---|---|---|
| `local-nifty-ticks-minute-20260102-v1` | Combined numerical input, explicit chronological split | F2 PASS; 38 observed / 41 official sessions; original v1 catalog 39 |
| `local-nifty-minute-2026-january-v1` | Development | F2 PASS; 20 sessions |
| `local-nifty-minute-2026-february-v1` | Validation, previously exposed | F2 PASS; 18 observed / 21 official sessions; original v1 catalog 19 |
| `local-nifty-weekly-quotes-20260102-v3` | January 2 accounting smoke | F3 PASS; 805 snapshots; one session; strict fixed-entry scope |
| `local-nifty-weekly-w200-20260102-v3` | Pooled exposed development / later validation history | F3 PASS; 44,848 snapshots; 35 quote-bearing / 41 official sessions |
| `local-nifty-weekly-w500-20260102-v3` | Pooled exposed development / later validation history | F3 PASS; 40,438 snapshots; 36 quote-bearing / 41 official sessions |

The combined manifest is for chronological fitting/evaluation inside the numerical
sandbox; it does not expose the combined observations to research roles. A PASS
on row integrity does not certify full calendar coverage or statistical precision.
The three spot v1 counts use the original 39-directory denominator. Subsequent
official-calendar verification establishes 41 scheduled sessions; see the
[preserved calendar correction](real-data-discovery.md#calendar-correction-directories-are-not-the-exchange-calendar).
Earlier options v1/v2 manifests are retained for lineage. V2 corrects the calendar;
v3 also adds the independently verified historical IPFT charge. Quote bytes are
unchanged across those versions; no originals or earlier results are overwritten. All manifests remain prior-exposed.

The options datasets support only fixed 10:00 construction, their respective wing
width, one 65-unit lot, hold-30 baseline and close at 10/15/20 minutes (smoke: 15).
They do not support recentering, dynamic spot filters or arbitrary entry times.
Quote-bearing sessions and actually executed cycles must be reported separately
from registered calendar decision sessions; missing observations are not measured
zero market returns.

## Clock and cost provenance

The [Shoonya feed documentation](https://www.shoonya.com/api-documentation/subscribe-market-feed)
defines initial state followed by changed fields. Missing fields must not become
zero quotes. Reconstruction is forward in receipt time within a contract/session,
with no future metadata backfill and separately recorded component ages.
Feed clocks are not independently certified exchange timestamps. A conservative
component-age limit is an explicit study restriction, not proof that an unchanged
price is stale.

Selected NIFTY lot units are checked against
[NSE circular FAOP70616](https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf),
which covers the December 2025 transition and January 2026 contracts.
January–February option cost references include
[NSE transaction charges](https://nsearchives.nseindia.com/content/circulars/FA64232.pdf),
[dated STT rates](https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax)
and [regulatory, stamp and GST rates](https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies).
Brokerage assumptions and per-fill paise rounding are modelling choices, not a
claim to reproduce a private historical contract note.

The final cost audit found that the first schedule omitted IPFT. The corrected
January–February combined NSE/IPFT rate is 0.0003553 of premium turnover:
transaction INR3,503 plus IPFT INR50 per crore. SEBI INR10 per crore is separate;
GST applies to these service charges and modelled brokerage. This is supported by
[FA56129](https://archives.nseindia.com/content/circulars/FA56129.pdf) and the
existing-rate table in [FA73061](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf).
The accounting smoke and both complete comparisons are rerun under new immutable
v3 manifests with unchanged hypotheses; incomplete exits retain DATA_LIMITED and
a linked fee-only audit, never invented corrected aggregate P&L.
