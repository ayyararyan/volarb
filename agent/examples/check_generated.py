"""Check JSON schema/package resource/diagram consistency without network or secrets."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from butterfly_lab.schemas import CONTRACTS

root = Path(__file__).resolve().parents[1]
for model in CONTRACTS:
    actual = json.loads((root / "docs" / "schemas" / (model.__name__ + ".json")).read_text())
    assert actual == model.model_json_schema(), f"stale schema: {model.__name__}"
for name in ("seeds.json", "benchmarks.json"):
    assert (root / "configs" / name).read_bytes() == (
        root / "src" / "butterfly_lab" / "resources" / name
    ).read_bytes(), f"stale installed resource: {name}"
manifest = json.loads((root / "docs" / "diagrams" / "render-manifest.json").read_text())
for name, record in manifest["diagrams"].items():
    base = root / "docs" / "diagrams"
    assert (
        hashlib.sha256((base / (name + ".mmd")).read_bytes()).hexdigest() == record["source_sha256"]
    )
    assert (
        hashlib.sha256((base / (name + ".svg")).read_bytes()).hexdigest() == record["render_sha256"]
    )
    assert ET.parse(base / (name + ".svg")).getroot().tag.endswith("svg")
print(
    f"Verified {len(CONTRACTS)} schemas, two installed resources and {len(manifest['diagrams'])} rendered diagrams"
)
