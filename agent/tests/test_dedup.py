from pathlib import Path

import pytest

from butterfly_lab.agents import load_seeds
from butterfly_lab.dedup import behavior_fingerprint, deduplicate, register_hypothesis
from butterfly_lab.registry import Registry


def seed():
    return load_seeds(Path(__file__).parents[1] / "configs" / "seeds.json")[0]


def test_renamed_duplicate_not_a_new_trial_and_retains_lineage(tmp_path):
    original = seed()
    renamed = original.model_copy(
        update={"id": "renamed", "mechanism": "A paraphrase of the same economic claim."}
    )
    registry = Registry(tmp_path / "runtime")
    register_hypothesis(registry, original)
    decision = register_hypothesis(registry, renamed)
    assert decision.relation == "DUPLICATE"
    assert decision.matched_id == original.id
    assert len(registry.list("hypothesis")) == 2
    assert registry.list("lineage")[0]["relation"] == "DUPLICATE"


def test_parameter_variant_and_materially_different_question():
    original = seed()
    variant = original.model_copy(update={"id": "variant", "parameter_domain": {"ridge": [0.1]}})
    assert deduplicate(variant, [original]).relation == "VARIANT"
    different = original.model_copy(
        update={
            "id": "other",
            "family_id": "other",
            "horizon_minutes": 60,
            "mechanism": "Insurance skew changes the price of protection.",
            "decision_change": "Select asymmetric wings.",
            "observable_inputs": ["skew"],
        }
    )
    assert deduplicate(different, [original]).relation == "NEW"


def test_behavior_is_development_only_and_correlated_variant_retained():
    original = seed()
    variant = original.model_copy(update={"id": "variant", "proposed_dsl": {"other_rule": True}})
    actions = [
        {"opportunity_id": str(i), "action": "hold", "partition": "development"} for i in range(100)
    ]
    other = [*actions[:-1], {**actions[-1], "action": "close"}]
    decision = deduplicate(variant, [original], behaviors={original.id: actions, variant.id: other})
    assert decision.relation == "VARIANT" and decision.behavior_similarity == 0.99
    with pytest.raises(ValueError, match="development"):
        behavior_fingerprint([{"opportunity_id": "1", "partition": "confirmation"}])
