"""Deterministic, AI-independent infrastructure placement decision engine."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from contracts import (
    ApplicationRequirements,
    ConstraintResult,
    InfrastructureProfiles,
    PlacementAssessment,
    ScoreBreakdown,
    TierAssessment,
    TierId,
)

TIER_ORDER: tuple[TierId, ...] = ("on_device", "far_edge", "regional_edge", "cloud")
REQUIREMENT_FIELDS = {
    "max_latency_ms",
    "data_must_stay_onsite",
    "min_compute",
    "required_bandwidth_mbps",
    "max_monthly_cost",
}
CAPABILITY_FIELDS = {
    "latency_ms",
    "data_stays_onsite",
    "compute",
    "bandwidth_mbps",
    "monthly_cost",
}
COMPUTE_RANK = {"low": 1, "medium": 2, "high": 3}
WEIGHTS = {
    "latency": 0.25,
    "data_residency": 0.20,
    "compute": 0.20,
    "bandwidth": 0.15,
    "monthly_cost": 0.20,
}


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _valid_capability(field: str, value: Any) -> bool:
    if value is None:
        return False
    if field in ("latency_ms", "bandwidth_mbps", "monthly_cost"):
        return _finite_nonnegative(value)
    if field == "data_stays_onsite":
        return type(value) is bool
    if field == "compute":
        return isinstance(value, str) and value in COMPUTE_RANK
    return False


def _validate_inputs(requirements: Any, profiles: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(requirements, Mapping):
        errors.append("Requirements must be an object with exactly the five required fields.")
    else:
        missing = REQUIREMENT_FIELDS - set(requirements)
        extra = set(requirements) - REQUIREMENT_FIELDS
        errors.extend(f"Missing requirement field: {field}." for field in sorted(missing))
        errors.extend(f"Unsupported requirement field: {field}." for field in sorted(extra))
        for field in ("max_latency_ms", "required_bandwidth_mbps", "max_monthly_cost"):
            if field in requirements and not _finite_nonnegative(requirements[field]):
                errors.append(f"Requirement {field} must be a finite nonnegative number.")
        if "data_must_stay_onsite" in requirements and type(requirements["data_must_stay_onsite"]) is not bool:
            errors.append("Requirement data_must_stay_onsite must be a boolean.")
        if "min_compute" in requirements and (
            not isinstance(requirements["min_compute"], str)
            or requirements["min_compute"] not in COMPUTE_RANK
        ):
            errors.append('Requirement min_compute must be one of "low", "medium", or "high".')

    if not isinstance(profiles, Mapping):
        errors.append("Infrastructure profiles must be an object keyed by the four supported tiers.")
    else:
        tier_keys = set(profiles)
        for tier in sorted(set(TIER_ORDER) - tier_keys):
            errors.append(f"Missing infrastructure tier: {tier}.")
        for tier in sorted(tier_keys - set(TIER_ORDER)):
            errors.append(f"Unsupported infrastructure tier: {tier}.")
        for tier in TIER_ORDER:
            if tier not in profiles:
                continue
            profile = profiles[tier]
            if not isinstance(profile, Mapping):
                errors.append(f"Infrastructure profile {tier} must be an object.")
                continue
            extras = set(profile) - CAPABILITY_FIELDS
            errors.extend(f"Unsupported capability field in {tier}: {field}." for field in sorted(extras))
    return errors


def _constraint(name: str, status: str, actual: Any, required: Any, reason: str) -> ConstraintResult:
    return {"constraint": name, "status": status, "actual": actual, "required": required, "reason": reason}  # type: ignore[return-value]


def _score(req: Mapping[str, Any], profile: Mapping[str, Any]) -> tuple[float, ScoreBreakdown]:
    latency = profile["latency_ms"]
    max_latency = req["max_latency_ms"]
    cost = profile["monthly_cost"]
    max_cost = req["max_monthly_cost"]
    bandwidth = profile["bandwidth_mbps"]
    required_bandwidth = req["required_bandwidth_mbps"]
    compute_rank = COMPUTE_RANK[profile["compute"]]

    values = {
        "latency": 1.0 if max_latency == 0 else 1 - latency / max_latency,
        "data_residency": 1.0,
        "compute": (compute_rank - 1) / 2,
        "bandwidth": 1.0 if required_bandwidth == 0 else min(bandwidth / required_bandwidth, 2) / 2,
        "monthly_cost": 1.0 if max_cost == 0 else 1 - cost / max_cost,
    }
    breakdown: dict[str, Any] = {}
    weighted_sum = 0.0
    for factor, weight in WEIGHTS.items():
        normalized = values[factor]
        points = weight * normalized
        breakdown[factor] = {
            "weight": weight,
            "normalized_value": normalized,
            "weighted_points": points,
        }
        weighted_sum += points
    total = round(100 * weighted_sum, 2)
    breakdown["total_score"] = total
    return total, breakdown  # type: ignore[return-value]


def evaluate_placement(
    requirements: ApplicationRequirements | Mapping[str, Any],
    profiles: InfrastructureProfiles | Mapping[str, Any],
) -> PlacementAssessment:
    """Assess all tiers; score and rank only tiers with confirmed feasibility."""
    errors = _validate_inputs(requirements, profiles)
    if errors:
        return {"valid": False, "errors": errors, "tiers": [], "ranking": [], "recommendation": None}

    req: Mapping[str, Any] = requirements
    profile_map: Mapping[str, Any] = profiles
    tiers: list[TierAssessment] = []

    for tier in TIER_ORDER:
        profile: Mapping[str, Any] = profile_map[tier]
        constraints: list[ConstraintResult] = []

        # Evaluate all five hard constraints, even when data is unknown.
        for field, label, required, comparator in (
            ("latency_ms", "latency", req["max_latency_ms"], lambda a, b: a <= b),
            ("data_stays_onsite", "onsite residency", True, lambda a, b: a is b),
            ("compute", "compute", req["min_compute"], lambda a, b: COMPUTE_RANK[a] >= COMPUTE_RANK[b]),
            ("bandwidth_mbps", "bandwidth", req["required_bandwidth_mbps"], lambda a, b: a >= b),
            ("monthly_cost", "monthly cost", req["max_monthly_cost"], lambda a, b: a <= b),
        ):
            actual = profile.get(field)
            if field == "data_stays_onsite" and not req["data_must_stay_onsite"]:
                constraints.append(_constraint(label, "NOT_APPLICABLE", actual, None, "Onsite residency is not required."))
            elif not _valid_capability(field, actual):
                constraints.append(_constraint(label, "UNVERIFIED", actual, required, f"Cannot verify {label}: capability data is missing or invalid."))
            else:
                passed = comparator(actual, required)
                verdict = "PASS" if passed else "FAIL"
                if field == "latency_ms":
                    reason = f"Latency {actual} ms is {'within' if passed else 'above'} the {required} ms maximum."
                elif field == "data_stays_onsite":
                    reason = "Data stays onsite as required." if passed else "Data does not stay onsite, as required."
                elif field == "compute":
                    reason = f"Compute level {actual} {'meets' if passed else 'is below'} the {required} requirement."
                elif field == "bandwidth_mbps":
                    reason = f"Bandwidth {actual} Mbps {'meets' if passed else 'is below'} the {required} Mbps minimum."
                else:
                    reason = f"Monthly cost {actual} {'is within' if passed else 'exceeds'} the {required} maximum."
                constraints.append(_constraint(label, verdict, actual, required, reason))

        failures = [c for c in constraints if c["status"] == "FAIL"]
        unknowns = [c for c in constraints if c["status"] == "UNVERIFIED"]
        if failures:
            status = "INFEASIBLE"
            reasons = [c["reason"] for c in failures] + [c["reason"] for c in unknowns]
            reasons.append("Known hard-constraint failure makes this tier infeasible." )
        elif unknowns:
            status = "UNVERIFIED"
            reasons = [c["reason"] for c in unknowns]
            reasons.append("Missing or invalid capability data prevents confirmation of feasibility.")
        else:
            status = "FEASIBLE"
            reasons = ["All applicable hard constraints are satisfied; feasibility is confirmed."]

        score, breakdown = _score(req, profile) if status == "FEASIBLE" else (None, None)
        tiers.append({"tier": tier, "status": status, "reasons": reasons, "constraints": constraints,
                      "score": score, "score_breakdown": breakdown})

    ranked_tiers = sorted(
        (entry for entry in tiers if entry["status"] == "FEASIBLE"),
        key=lambda entry: (-entry["score"], TIER_ORDER.index(entry["tier"])),
    )
    ranking = [{"tier": entry["tier"], "score": entry["score"], "rank": rank}
               for rank, entry in enumerate(ranked_tiers, start=1)]
    recommendation = ranking[0]["tier"] if ranking else None
    return {"valid": True, "errors": [], "tiers": tiers, "ranking": ranking,
            "recommendation": recommendation}
