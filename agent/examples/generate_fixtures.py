"""Write no-secrets fixtures/manifests to a requested runtime directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from butterfly_lab.fixtures import generate_option_fixture, generate_spot_fixture


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    spot = generate_spot_fixture(args.output / "spot.csv")
    options = generate_option_fixture(args.output / "options.parquet")
    for name, manifest in [("spot", spot), ("options", options)]:
        (args.output / f"{name}-manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        json.dumps(
            {
                "status": "created",
                "provenance": "SYNTHETIC",
                "datasets": [spot["id"], options["id"]],
            }
        )
    )


if __name__ == "__main__":
    main()
