# Research and decision skills

These source packages are separately packaged research/decision modules,
not the generic [Execution Engine](../execution-engine/README.md) or broker-order
authorization. Installed copies are pinned deployments, not automatic source syncs.

| Skill | Role and entrypoint |
|---|---|
| [Butterfly Market Outlook](butterfly-market-outlook/SKILL.md) | Strategy-specific first-terminal-gate controller; start with its [decision algorithm](butterfly-market-outlook/references/decision-algorithm.md) |
| [Intraday Realized Volatility Forecast](intraday-realized-volatility-forecast/SKILL.md) | HF physical-variance, jump-pressure and drift child; never issues the final trade action |
| [Market News Signal Filter](market-news-signal-filter/SKILL.md) | Normalized event/hazard child; calibration is dated and must retain its freshness status |

The [personal trading covenant](../docs/PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md)
overrides generic overnight examples: intraday only, flat by 15:00 IST, no entry
or recenter thereafter. Aryan executes; these packages do not imply broker orders
or new monitoring. The retrospective [research laboratory](../agent/README.md)
is separate; its frozen observed-controller copy must not be updated in lockstep.

## Package layout and offline validation

Each directory owns `SKILL.md`, progressive `references/`, optional deterministic
`scripts/`, and packaged `agents/`/`assets/`. Version labels on calculation modules
describe the module generation, not a competing controller. `architecture-v2.md`
is a retained strategy-reference path; repository-wide architecture lives in
[`architecture/`](../architecture/README.md).

From the repository root, with the locked development dependencies installed:

```sh
python -m pytest -q skill/butterfly-market-outlook/tests
python .github/skill-tools/check_rv_fixtures.py
python .github/skill-tools/package_skill.py skill/butterfly-market-outlook /tmp/butterfly-skill-package
python .github/skill-tools/package_skill.py skill/intraday-realized-volatility-forecast /tmp/rv-skill-package
python .github/skill-tools/package_skill.py skill/market-news-signal-filter /tmp/news-skill-package
```

RV `scripts/test_*.json` files are deliberate offline regression inputs consumed by
the fixture checker, not captured live data or disposable generated outputs.

## Package navigation and dependencies

Each ZIP contains its own skill directory and bundled references/scripts/assets. Cross-skill and repository-level documentation links use canonical GitHub source URLs so they do not become broken filesystem links after installation. These source links may be viewed under the repository's proprietary LICENSE; visibility does not authorize reuse or deployment. A configured local source checkout is an equivalent read location. The parent butterfly workflow requires the RV and news skills; packaging each independently does not remove those runtime research dependencies. Installed copies remain pinned until explicitly refreshed.
