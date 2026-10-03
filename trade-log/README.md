# Private trade records — intentionally omitted

This publicly inspectable source repository contains no personal trade ledger,
executed-trade history, account snapshots or financial calibration episodes.
Those records belong in the configured **private data directory outside the source
checkout**, with the existing shared-writer `Trading/ledger/` store remaining the
sole live accounting authority.

The [private recordkeeping contract](../skill/butterfly-market-outlook/references/repo-logging.md)
documents the CSV/JSONL schemas, provenance and cycle identity conventions for
private use. The summarizer accepts an explicit private input path; no sample
here represents actual fills or account state.

Historical personal records were preserved in a verified private backup during
public-release preparation, not converted into examples or silently discarded.
Do not restore them to Git history, release assets, issues or pull requests.
Source maintenance and publication never initialize a financial ledger.
