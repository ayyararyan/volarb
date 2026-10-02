"""Deterministic duplicate/variant detection without erasing the search history."""

from __future__ import annotations

import re
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import HypothesisSpec, digest


class DedupDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    relation: Literal["NEW", "DUPLICATE", "VARIANT", "REVIEW"]
    matched_id: str | None = None
    canonical_hash: str
    semantic_similarity: float = Field(default=0, ge=0, le=1)
    feature_overlap: float = Field(default=0, ge=0, le=1)
    behavior_similarity: float | None = Field(default=None, ge=0, le=1)
    reason: str


def _mapping(spec: HypothesisSpec | dict[str, Any]) -> dict[str, Any]:
    return spec.model_dump(mode="json") if isinstance(spec, HypothesisSpec) else spec


def canonical_spec(spec: HypothesisSpec | dict[str, Any]) -> dict[str, Any]:
    """Names and prose are not scientific identity; feature definitions/DSL are.

    No unsafe unit conversion or commutative rewriting of ordered actions is done.
    Missing DSLs retain decision/comparison text to avoid over-merging seeds.
    """
    data = _mapping(spec)
    keys = (
        "evaluator",
        "family_id",
        "horizon_minutes",
        "outcome",
        "baseline_id",
        "primary_metric",
        "practical_effect",
        "parameter_domain",
        "minimum_data",
    )
    canonical = {key: data.get(key) for key in keys}
    canonical["observable_inputs"] = sorted(set(data.get("observable_inputs", [])))
    canonical["risk_constraints"] = sorted(set(data.get("risk_constraints", [])))
    canonical["minimum_data"] = sorted(set(data.get("minimum_data", [])))
    canonical["proposed_dsl"] = data.get("proposed_dsl") or {
        "decision_change": data.get("decision_change"),
        "comparison": data.get("primary_comparison"),
    }
    return canonical


def _tokens(text: str) -> set[str]:
    stop = {"the", "a", "an", "and", "or", "of", "to", "is", "in", "with", "by", "for"}
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in stop}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def behavior_fingerprint(actions: list[dict[str, Any]]) -> str:
    """Fixture actions must be PIT development observations, never final results."""
    if any(a.get("partition", "development") != "development" for a in actions):
        raise ValueError("Behavior deduplication requires development-only actions")
    ordered = sorted(actions, key=lambda row: str(row["opportunity_id"]))
    if len({str(row["opportunity_id"]) for row in ordered}) != len(ordered):
        raise ValueError("Duplicate behavior opportunity ID")
    return digest(ordered)


def deduplicate(
    spec: HypothesisSpec | dict[str, Any],
    existing: Iterable[HypothesisSpec | dict[str, Any]],
    *,
    behaviors: dict[str, list[dict[str, Any]]] | None = None,
) -> DedupDecision:
    candidate = _mapping(spec)
    canonical = canonical_spec(candidate)
    canonical_hash = digest(canonical)
    best: DedupDecision | None = None
    for old in existing:
        prior = _mapping(old)
        if prior["id"] == candidate["id"]:
            continue
        old_canonical = canonical_spec(prior)
        semantic = _jaccard(
            _tokens(candidate["mechanism"] + " " + candidate["decision_change"]),
            _tokens(prior["mechanism"] + " " + prior["decision_change"]),
        )
        overlap = _jaccard(set(candidate["observable_inputs"]), set(prior["observable_inputs"]))
        behavior = None
        if behaviors and candidate["id"] in behaviors and prior["id"] in behaviors:
            left, right = behaviors[candidate["id"]], behaviors[prior["id"]]
            behavior_fingerprint(left)
            behavior_fingerprint(right)
            lmap = {str(row["opportunity_id"]): row for row in left}
            rmap = {str(row["opportunity_id"]): row for row in right}
            common = lmap.keys() & rmap.keys()
            if common and lmap.keys() == rmap.keys():
                behavior = sum(lmap[key] == rmap[key] for key in common) / len(common)
        if canonical_hash == digest(old_canonical):
            return DedupDecision(
                relation="DUPLICATE",
                matched_id=prior["id"],
                canonical_hash=canonical_hash,
                semantic_similarity=semantic,
                feature_overlap=overlap,
                behavior_similarity=behavior,
                reason="Same frozen scientific specification; retain alias lineage",
            )
        family_same = candidate["family_id"] == prior["family_id"]
        except_parameters = {
            k: v for k, v in canonical.items() if k not in ("parameter_domain", "proposed_dsl")
        }
        prior_except = {
            k: v for k, v in old_canonical.items() if k not in ("parameter_domain", "proposed_dsl")
        }
        if family_same and (
            except_parameters == prior_except or (behavior is not None and behavior >= 0.99)
        ):
            decision = DedupDecision(
                relation="VARIANT",
                matched_id=prior["id"],
                canonical_hash=canonical_hash,
                semantic_similarity=semantic,
                feature_overlap=overlap,
                behavior_similarity=behavior,
                reason="Related policy/parameter alternative; new selection trial, shared family",
            )
        elif semantic >= 0.75 and overlap >= 0.5:
            decision = DedupDecision(
                relation="REVIEW",
                matched_id=prior["id"],
                canonical_hash=canonical_hash,
                semantic_similarity=semantic,
                feature_overlap=overlap,
                behavior_similarity=behavior,
                reason="Semantic resemblance requires review; no automatic merge",
            )
        else:
            continue
        if best is None or decision.relation == "VARIANT":
            best = decision
    return best or DedupDecision(
        relation="NEW",
        canonical_hash=canonical_hash,
        reason="No duplicate or policy variant established",
    )


def register_hypothesis(
    registry: Any, spec: HypothesisSpec, *, behaviors: dict[str, list[dict[str, Any]]] | None = None
) -> DedupDecision:
    decision = deduplicate(spec, registry.list("hypotheses"), behaviors=behaviors)
    registry.put("hypotheses", spec.id, spec.model_dump(mode="json"))
    registry.put("source", "dedup:" + spec.id, decision.model_dump(mode="json"))
    if decision.matched_id:
        registry.put(
            "lineage_edges",
            digest({"child": spec.id, "parent": decision.matched_id}),
            {
                "child_id": spec.id,
                "parent_id": decision.matched_id,
                "relation": decision.relation,
                "campaign_id": spec.campaign_id,
            },
        )
    return decision
