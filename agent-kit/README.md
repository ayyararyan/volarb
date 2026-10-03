# Portable research-agent kit

Start with the [setup and packaging guide](../docs/AGENT_KIT.md), then the
[dependency inventory](../docs/DEPENDENCY_INVENTORY.md).

| Path | Purpose |
|---|---|
| `manifest.json` | Pinned runtimes, installation defaults and explicit source-package roots |
| `profiles/dhandho.json` | Adopted sanitized research/governance profile; no live execution authorization |
| `workspace/` | Create-only personal-agent templates; existing personal files are preserved |
| `source-inventory.json` | Dated 2026-09-29 import provenance; original hashes are historical, not current drift checks |
| [`tools/volarb.py`](../tools/volarb.py) | Explicit setup, offline diagnostics, environment launcher and source packaging |
| [`tests/test_agent_kit.py`](../tests/test_agent_kit.py) | Synthetic installer, private-state exclusion, mutation-disable and package-import regressions |

Setup starts no service, submits no order, registers no scheduler and creates no
financial ledger. Private data/workspace locations remain external to the checkout.
Execution Testbed source included in a package is not a production dependency.
