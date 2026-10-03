# Private market journals — intentionally omitted

Daily market outlooks, candidate searches and position reviews can expose personal
trading activity. They are recorded only in the configured **private journal outside
the source checkout**, not in this repository or its public issues, pull requests
and release assets.

The [private recordkeeping contract](../skill/butterfly-market-outlook/references/repo-logging.md)
preserves one append-only IST daily file across symbols, including unchanged and
blocked checks. Its paths are relative to the private journal root, not this
navigation directory. Recordkeeping never delays urgent risk decisions.

Historical journals were preserved in a verified private backup during
public-release preparation. They are not bundled with the publicly viewable
source, and source publication does not migrate or activate journal writers.
