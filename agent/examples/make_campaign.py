"""Write a no-secrets campaign and safe synthetic inputs outside the checkout."""

import argparse
import json
from pathlib import Path

from butterfly_lab.agents import load_seeds
from butterfly_lab.config import runtime_root
from butterfly_lab.fixtures import (
    generate_option_fixture,
    generate_spot_fixture,
    default_ironfly_parameters,
)
from butterfly_lab.schemas import CampaignSpec, DatasetManifest

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("destination")
p.add_argument("--kind", choices=["spot", "fourleg"], default="spot")
a = p.parse_args()
root = runtime_root(a.destination)
data = (
    generate_spot_fixture(root / "spot.csv")
    if a.kind == "spot"
    else generate_option_fixture(root / "fourleg.parquet")
)
campaign = CampaignSpec(
    id="example-" + a.kind,
    objective="Bounded synthetic research, including informative negative and data-limited outcomes",
    approved=True,
)
seeds = load_seeds(Path(__file__).resolve().parents[1] / "configs" / "seeds.json", campaign.id)
if a.kind == "fourleg":
    seed = seeds[10].model_copy(
        update={
            "minimum_data": ["identified_contracts", "two_sided_quotes"],
            "proposed_dsl": default_ironfly_parameters(),
        }
    )
    seeds = [seed, seeds[0]]
for name, value in [
    ("campaign", campaign.model_dump(mode="json")),
    ("dataset", DatasetManifest.model_validate(data).model_dump(mode="json")),
    ("hypotheses", [s.model_dump(mode="json") for s in seeds]),
]:
    (root / (name + ".json")).write_text(json.dumps(value, indent=2) + "\n")
print("Generated labelled synthetic campaign, dataset and hypotheses in", root)
