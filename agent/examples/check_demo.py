"""Assert lifecycle completion, not merely a successful CLI exit code."""

import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
assert report["label"].startswith("SYNTHETIC")
expected = {
    "demo-spot": ("exp-demo-spot-H001", "INCONCLUSIVE"),
    "demo-fourleg": ("exp-demo-fourleg-H011", "EXPLORATORY_SUPPORTED"),
}
assert len(report["examples"]) == 2
for example in report["examples"]:
    campaign = example["report"]
    identifier, outcome = expected[campaign["campaign_id"]]
    findings = {item["experiment_id"]: item for item in campaign["findings"]}
    assert findings[identifier]["outcome"] == outcome
    assert findings[identifier]["evidence_grade"]["replication"] == "independently_reconstructed"
    assert findings[identifier]["evidence_grade"]["fidelity"] == "F0"
    assert any(item["outcome"] == "DATA_LIMITED" for item in findings.values())
    assert not campaign["pending_experiments"]
    assert campaign["status"]["runs"] == {"INGESTED": 1}
print("Both controlled campaign graphs completed with ingested, reconstructed F0 results")
