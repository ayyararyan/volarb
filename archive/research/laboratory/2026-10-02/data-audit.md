# Data reinspection — 2 October 2026

> Historical initial-release qualification, not the current data inventory.
> See the [archive index](README.md) for subsequent capabilities and findings.

Read-only, bounded reinspection during implementation. No private datasets,
credentials, live-account records or machine-specific source paths are committed.
Source locations belong in private runtime manifests.

| Source | Fresh observed evidence | Qualification consequence |
|---|---|---|
| `NIFTY_1MIN_OHLC_2021-2026.zip` | Readable; 14,095,932 bytes; embedded manifest six consolidated yearly files, 587,080 rows, 2021-01-01–2026-08-21; sampled actual header `datetime,open,high,low,close` | Suitable candidate for EXP001, **but embedded documentation does not certify start/end bar labelling**. Real experiment remains DATA_LIMITED until documented convention and session rules are established. |
| `NIFTY_OPTIONS_1MIN_OHLCV_2021-2026.zip` | Readable; 250,130,083 bytes; embedded manifest 2,772 CSVs/20,860,781 rows, 2021-01-01–2026-05-14; sampled actual six-column OHLCV schema | README explicitly identifies rolling WEEK1 ATM-relative lanes and stripped identity fields. Does **not** qualify as held fixed-contract option paths. |
| Richer source manifest | Fresh read again failed OS error11, `Resource deadlock avoided` | Source candidate unavailable, not empty and not silently replaced by the reduced export. |

Fresh package SHA256 fingerprints:

- Spot: `9127f44b2b39b2c31958f5a4e8303028fe151ad1cd51ce1f01b88837d3686484`.
- Options: `d525d14cd7d36927beb33ccfec1bd8a805681083298943a0f292babfd5864d72`.

The counts above are freshly read **manifest totals**, not a new full-session
market-quality audit. Sample rows were opened successfully and package hashes
recomputed. The earlier proposal's richer coverage/clock findings remain prior
audit evidence, not claimed new scans in this implementation.

Do not set `timestamp_convention_verified=true` merely to make a run pass. A
conservative lag does not settle whether the source label denotes a bar start or
end. The CLI can register/execute the manifest with this flag false and preserve
a DATA_LIMITED result before economic estimation. Likewise, a historical options
manifest cannot create identity by adding the label F2.

No unexamined real confirmation partition was established. Historical windows
must remain prior-exposed/exploratory. Synthetic no-secrets fixtures exercise
working numerical, confirmation and failure paths without being presented as
historical discoveries.

## Registered real-source gate results

Two approved, no-model-call campaigns were executed through the actual campaign
and experiment graphs against the source bytes above:

| Campaign / experiment | Recorded terminal finding | Numerical jobs |
|---|---|---|
| `real-audit-spot` / `exp-real-audit-spot-H001` | DATA_LIMITED: OHLC inequalities violated, before the separate unverified bar-label gate | 0 |
| `real-audit-options` / `exp-real-audit-options-H010` | DATA_LIMITED: fixed contract identity/expiry/strike/lot fields absent | 0 |

The spot qualification discovered an additional concrete defect. A separate
bounded scan of the consolidated yearly members found **12 OHLC-inconsistent
rows**; the largest high-versus-open violation was **8.9508 index points**. Some
other differences were very small, but it would be incorrect to classify all 12
as harmless rounding. No source repair, outcome-selected exclusion, or optimistic
price substitution was made.

The options gate used one explicitly selected representative member and verified
the package hash. It did not expand 20.9 million stripped rows merely to rediscover
the missing columns. Scope remains representative-member inspection plus the
embedded export schema/documentation, not a full-chain completeness claim.

Both findings and their qualification records are retained in the private
registry/artifact store; reports contain no historical performance estimate.
No worker was launched into economic estimation after failed qualification.
The tested software therefore distinguishes a completed negative/data-limited
research process from unavailable market evidence.
