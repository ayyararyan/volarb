# Local historical data discovery — 3 October 2026

Research-only work began at main `730e632f4e5fec10823ef5322b520977a446dc1b`.
Configuration, ChatGPT authentication, managed Codex app-server, enforced numerical
sandbox, registry and checkpoint integrity were checked before data discovery.
No diagnostic model request, broker call, acquisition or original-data write was made.

## Search and authority

Read-only metadata searches covered local projects, Documents, Downloads, Desktop,
workspace exports/data, readable cloud roots, relevant application caches and an
attached external volume. Spotlight supplemented targeted filesystem traversal.
Private inventories retain searched locations, errors, exact paths, file metadata,
schema samples, duplicate candidates and source hashes. Missing/denied locations
and cloud placeholders are not represented as readable files. This was intelligent
discovery, not a claim to read every file or hash the entire Mac.

**20 source families** were classified. This includes packages, copies and derived
research stores, not 20 independent vendors or admitted datasets.

| Important source family | Fresh evidence | Authority / limitation |
|---|---|---|
| External raw index/derivative archive | 77,835 Parquet files, approximately 53.7 GB; 39 represented sessions, January–February 2026; NIFTY, BANKNIFTY, SENSEX | Best readable quote-level candidate. Individual source files contain sparse broker-feed updates, not one-second candles. Full hashes bind every admitted file; the whole archive was not blindly hashed. |
| NIFTY index tick subset | 38 actual index files; 14,357 derived minute bars; January 1–February 27 | Selected for real F2 prediction. February 19 absent; three missing regular minutes; 110 outside-regular bars retained. |
| NIFTY historical spot package | 587,080 unique yearly rows, January 2021–August 2026; ZIP CRC and 78 embedded checksums pass | Older derived delivery; 12 invalid OHLC rows and unresolved inherited candle convention. Not used to bypass qualification. |
| NIFTY historical option package | Approximately 20.9 million OHLCV rows, 2021–2026 | Rolling ATM-relative lanes with identity stripped. Never held-contract P&L data. Copies hash-identical. |
| BANKNIFTY native download master | 378 fixed active option identities; 2,575,872 minute OHLC/volume/OI rows, April 22–September 11, 2026; separate futures/reference/rolling responses | Richer than rolling exports; original request metadata binds security, expiry, strike and side. Candle convention remains unresolved; historical lots require dated evidence. |
| BANKNIFTY futures | Three fixed contracts; 37,833 bars, July–September 2026 | Individual futures, not a verified continuous/rolled series. |
| BANKNIFTY reference spot | 534,984 rows, August 2021–September 2026 | Four OHLC defects and 2,065 non-minute timestamps; not silently cleaned. |
| Cloud Dhan originals / fixed-option exports | Large catalog-visible source trees and fixed-option candidates | Sample content reads fail with OS `Resource deadlock avoided`; metadata visibility is not access. Daily `DHANFIX` filenames alone do not establish expiry identity. |
| Other research snapshots, refreshes, image datasets, chain stores, VIX and live-capture caches | Inventoried as separate families with schemas where readable | Derived, partial, unknown or limited-session evidence; not promoted to authoritative history by modification time. |

The BANKNIFTY fixed archive is materially incomplete: only 2,393 of 7,424
represented contract-sessions contain all 375 regular minutes. A coverage-only
four-leg endpoint check is not a P&L result or proof of executable timing.

## Identity, lineage and duplicates

The external archive binds fixed contracts using observed trading symbol and token.
Its numeric weekly symbols encode a date; monthly symbols require a separate dated
calendar. A legacy research loader's last-Thursday monthly rule is not reused.
Observed `ls` is lot units; `ml=1` is not a one-unit lot. Feed epoch seconds and
capture clocks are preserved separately. Capture timestamps require documented
IST localization; per-source clock checks precede normalization.

Identical ZIP copies are confirmed by full SHA256. Package-to-extracted and
monthly-to-yearly representations are lineage relationships, never additive
observations. Other duplicates remain `LIKELY_IDENTICAL`, `DERIVED_VERSION`,
`DIFFERENT_SOURCE`, `CONFLICTING_SOURCE` or `UNKNOWN` where hashes/provenance do
not settle them. No copies were removed.

Original sources remain untouched. Derived stores are separate, content-hashed,
read-only artifacts with source-row references and transformation records. Raw
market observations, original paths, runtime databases and source manifests remain
private. Model roles receive only sanitized IDs, hashes and qualified summaries.

## Calendar correction: directories are not the exchange calendar

The 39 source directories do **not** represent every scheduled session. The
official NSE calendar has 41 January–February sessions (20 + 21): January 15 and
26 are holidays, while [circular FAOP72352](https://nsearchives.nseindia.com/content/circulars/FAOP72352.pdf)
opens February 1 for Budget trading. The entire archive lacks February 1 and
February 10. The [NSE holiday calendar](https://www.nseindia.com/resources/exchange-communication-holidays)
contains no February weekday holiday that would explain February 10.

This gap was found before options numerical execution. New immutable options
manifests retain all 41 expected decision sessions; their quote bytes and earlier
manifest versions are unchanged. Missing market returns remain unknown. The
completed spot smoke retains its original catalog-bound manifest/result, with
this correction recorded as a limitation: 38/41 market sessions overall and
18/21 in February, not full exchange coverage. No economic result was rerun or
selected after this correction. Missing the Budget day particularly limits event
risk conclusions.

## Prior exposure

Existing research outputs demonstrate prior use of these archives. All admitted
history is conservatively `prior_exposed=true`; no pristine protected confirmation
is claimed. January is development and February later exploratory validation.
Hypothesis generation never receives raw observations from either partition.

See [capabilities](real-data-capabilities.md) and [campaign findings](first-real-campaign.md).
