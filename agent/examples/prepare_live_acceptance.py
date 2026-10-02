"""Create bounded synthetic inputs; this script makes no model or broker calls.

Run the resulting campaign with the normal `campaign run ... --wait` command.
Use a fresh ID for each immutable acceptance campaign.
"""

import argparse
from pathlib import Path

from butterfly_lab.benchmarks import controlled_dataset, controlled_hypothesis
from butterfly_lab.schemas import BudgetSpec, CampaignSpec


def prepare(output: Path, campaign_id: str) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    hypothesis = controlled_hypothesis(campaign_id + "-h1", campaign_id).model_copy(
        update={
            "mechanism": "Engineering calibration: an explicitly planted paired loss reduction tests the registered inference and workflow, not an economic mechanism or alpha.",
            "decision_change": "Compare fixed seeded candidate loss against the registered unit-loss control; no trading decision.",
            "primary_comparison": "Paired mean baseline loss 1 versus candidate loss 1 - effect + IID Gaussian noise on identical generated sessions",
            "primary_metric": "paired_loss_improvement",
            "falsification_rule": "With adequate registered precision, an interval entirely below the 0.01 practical relative-loss reduction threshold rejects the claim; overlap is inconclusive. Reconstruction disagreement invalidates implementation evidence.",
            "alternative_explanations": [
                "Finite-sample Monte Carlo variation",
                "Implementation or inference errors rather than the registered generator",
                "Planted synthetic calibration does not imply an economic or causal effect",
            ],
            "proposed_dsl": {
                "evaluator": "controlled",
                "effect": 0.2,
                "noise": 0.05,
                "n_sessions": 64,
            },
            "parameter_domain": {"effect": [0.2], "noise": [0.05], "n_sessions": [64]},
        }
    )
    dataset = controlled_dataset(campaign_id + "-synthetic").model_copy(
        update={
            "metadata": {
                "generator": "controlled_session_panel_v1",
                "effect": 0.2,
                "noise": 0.05,
                "n_sessions": 64,
            }
        }
    )
    campaign = CampaignSpec(
        id=campaign_id,
        approved=True,
        provider="codex",
        max_hypotheses=1,
        preparation_batch=1,
        llm_concurrency=1,
        numerical_concurrency=1,
        seed=17,
        objective=(
            "Verify one full research lifecycle using a deliberately planted synthetic engineering calibration. "
            "Generate exactly one hypothesis within the approved reference design below, retaining the controlled "
            "evaluator, unit-loss baseline, effect 0.2, Gaussian noise standard deviation 0.05, 64 paired sessions, "
            "search budget one and practical relative-improvement threshold 0.01. The hypothesis is whether the "
            "registered computation detects the planted effect, not whether a strategy is profitable. "
            "No parameter search, live trading, broker calls, historical evidence or protected confirmation. "
            "The critic must judge the actual design independently; deficiencies must not be waived."
        ),
        budget=BudgetSpec(
            max_runs=1,
            cpu_seconds=60,
            storage_bytes=20_000_000,
            memory_mb=1024,
            max_pending=1,
            llm_calls=14,
            llm_tokens=524288,
        ),
        source_records=[
            {
                "id": "controlled-generator-contract-v1",
                "title": "Approved synthetic calibration contract",
                "summary": (
                    "Protected controlled evaluator generates 64 paired session rows with NumPy default_rng(seed=17). "
                    "Baseline loss is 1; candidate loss is 1 - 0.2 + IID Gaussian noise with zero mean and standard "
                    "deviation 0.05. Business-day labels begin 2020-01-01 and are synthetic indices, not market data. "
                    "No fitting, model selection or calendar split filtering occurs. Registered moving-block inference "
                    "uses 999 repetitions, alpha 0.05, primary block length 5 and robustness lengths 1/5/10; "
                    "unit is paired session, minimum 30 sessions. Comparator and inference are deterministic. "
                    "No observations, results or independent verification exist during preparation."
                ),
                "limitations": [
                    "F0 controlled evidence only; no historical profitability or causal claim."
                ],
                "reference_hypothesis": hypothesis.model_dump(mode="json"),
            }
        ],
    )
    paths = output / "campaign.json", output / "dataset.json"
    for path, model in zip(paths, (campaign, dataset), strict=True):
        with path.open("x") as stream:
            stream.write(model.model_dump_json(indent=2) + "\n")
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    for path in prepare(args.output, args.campaign_id):
        print(path)
