"""Inspect explicit source paths. No inferred historical timestamp/contract guarantees."""

import argparse
import hashlib
from pathlib import Path

from butterfly_lab.schemas import DatasetManifest

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("source")
p.add_argument("--kind", choices=["spot_bars", "option_bars", "option_quotes"], required=True)
p.add_argument("--id", required=True)
p.add_argument("--bar-label", choices=["start", "end", "event"], required=True)
p.add_argument(
    "--label-verified",
    action="store_true",
    help="Only after documented provider/calendar verification",
)
p.add_argument("--output", required=True)
a = p.parse_args()
source = Path(a.source).expanduser().resolve()
h = hashlib.sha256()
with source.open("rb") as f:
    for block in iter(lambda: f.read(1048576), b""):
        h.update(block)
manifest = DatasetManifest(
    id=a.id,
    kind=a.kind,
    source_path=str(source),
    source_sha256=h.hexdigest(),
    fidelity="F3" if a.kind == "option_quotes" else "F2",
    provenance="HISTORICAL",
    bar_label=a.bar_label,
    timestamp_convention_verified=a.label_verified,
    availability_lag_seconds=0 if a.kind == "option_quotes" else 60,
    prior_exposed=True,
)
Path(a.output).write_text(manifest.model_dump_json(indent=2) + "\n")
print("Wrote manifest only; run data validate. Qualification is not implied.")
