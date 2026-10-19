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
    "data_residency",
    "min_compute",
    "required_bandwidth_mbps",
    "max_monthly_cost",
}
LEGACY_REQUIREMENT_FIELDS = (REQUIREMENT_FIELDS - {"data_residency"}) | {"data_must_stay_onsite"}
DATA_RESIDENCY_OPTIONS = {"On-site Only", "Specific Region Only", "No Restriction"}
CAPABILITY_FIELDS = {
    "latency_ms",
    "data_stays_onsite",
    "compute",
    "bandwidth_mbps",
    "monthly_cost",
    "location",
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
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except (OverflowError, TypeError, ValueError):
        return False


def _valid_capability(field: str, value: Any) -> bool:
    if value is None:
        return False
    if field in ("latency_ms", "bandwidth_mbps", "monthly_cost"):
        return _finite_nonnegative(value)
    if field == "data_stays_onsite":
        return type(value) is bool
    if field == "compute":
        return isinstance(value, str) and value in COMPUTE_RANK
    if field == "location":
        return isinstance(value, str) and bool(value.strip())
    return False


def _normalize_requirements(requirements: Mapping[str, Any]) -> dict[str, Any]:
    """Map only explicit legacy booleans; other legacy values remain invalid."""
    normalized = dict(requirements)
    if "data_must_stay_onsite" in normalized and "data_residency" not in normalized:
        legacy_value = normalized.pop("data_must_stay_onsite")
        if type(legacy_value) is bool:
            normalized["data_residency"] = "On-site Only" if legacy_value else "No Restriction"
        elif isinstance(legacy_value, str) and legacy_value in ("Yes", "No"):
            normalized["data_residency"] = "On-site Only" if legacy_value == "Yes" else "No Restriction"
    return normalized


def _validate_inputs(requirements: Any, profiles: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(requirements, Mapping):
        errors.append("Requirements must be an object with exactly the five required fields.")
    else:
        legacy = "data_must_stay_onsite" in requirements
        canonical = "data_residency" in requirements
        if legacy and canonical:
            errors.append("Use either data_residency or the legacy data_must_stay_onsite field, not both.")
        required_fields = LEGACY_REQUIREMENT_FIELDS if legacy and not canonical else REQUIREMENT_FIELDS
        allowed_fields = required_fields | {"permitted_region"}
        missing = required_fields - set(requirements)
        extra = set(requirements) - allowed_fields
        errors.extend(f"Missing requirement field: {field}." for field in sorted(missing))
        errors.extend(f"Unsupported requirement field: {field}." for field in sorted(extra, key=str))
        for field in ("max_latency_ms", "required_bandwidth_mbps", "max_monthly_cost"):
            if field in requirements and not _finite_nonnegative(requirements[field]):
                errors.append(f"Requirement {field} must be a finite nonnegative number.")
        legacy_value = requirements.get("data_must_stay_onsite")
        if legacy and type(legacy_value) is not bool and not (isinstance(legacy_value, str) and legacy_value in ("Yes", "No")):
            errors.append('Legacy data_must_stay_onsite must be boolean true/false or the exact string "Yes"/"No".')
        residency_value = requirements.get("data_residency")
        if canonical and (not isinstance(residency_value, str) or residency_value not in DATA_RESIDENCY_OPTIONS):
            errors.append('Requirement data_residency must be "On-site Only", "Specific Region Only", or "No Restriction".')
        region = requirements.get("permitted_region")
        if region is not None and not isinstance(region, str):
            errors.append("Requirement permitted_region must be text or null.")
        if canonical and requirements.get("data_residency") == "Specific Region Only" and (not isinstance(region, str) or not region.strip()):
            errors.append("A non-empty permitted_region is required for Specific Region Only.")
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
        for tier in sorted(tier_keys - set(TIER_ORDER), key=str):
            errors.append(f"Unsupported infrastructure tier: {tier}.")
        for tier in TIER_ORDER:
            if tier not in profiles:
                continue
            profile = profiles[tier]
            if not isinstance(profile, Mapping):
                errors.append(f"Infrastructure profile {tier} must be an object.")
                continue
            extras = set(profile) - CAPABILITY_FIELDS
            errors.extend(f"Unsupported capability field in {tier}: {field}." for field in sorted(extras, key=str))
            if "location" in profile and profile["location"] is not None and not isinstance(profile["location"], str):
                errors.append(f"Infrastructure profile {tier} location must be text or null.")
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

    req: Mapping[str, Any] = _normalize_requirements(requirements)
    profile_map: Mapping[str, Any] = profiles
    tiers: list[TierAssessment] = []

    for tier in TIER_ORDER:
        profile: Mapping[str, Any] = profile_map[tier]
        constraints: list[ConstraintResult] = []

        # Evaluate all non-residency hard constraints before scoring.
        for field, label, required, comparator in (
            ("latency_ms", "latency", req["max_latency_ms"], lambda a, b: a <= b),
            ("compute", "compute", req["min_compute"], lambda a, b: COMPUTE_RANK[a] >= COMPUTE_RANK[b]),
            ("bandwidth_mbps", "bandwidth", req["required_bandwidth_mbps"], lambda a, b: a >= b),
            ("monthly_cost", "monthly cost", req["max_monthly_cost"], lambda a, b: a <= b),
        ):
            actual = profile.get(field)
            if not _valid_capability(field, actual):
                constraints.append(_constraint(label, "UNVERIFIED", actual, required, f"Cannot verify {label}: capability data is missing or invalid."))
            else:
                passed = comparator(actual, required)
                verdict = "PASS" if passed else "FAIL"
                if field == "latency_ms":
                    reason = f"Latency {actual} ms is {'within' if passed else 'above'} the {required} ms maximum."
                elif field == "compute":
                    reason = f"Compute level {actual} {'meets' if passed else 'is below'} the {required} requirement."
                elif field == "bandwidth_mbps":
                    reason = f"Bandwidth {actual} Mbps {'meets' if passed else 'is below'} the {required} Mbps minimum."
                else:
                    reason = f"Monthly cost {actual} {'is within' if passed else 'exceeds'} the {required} maximum."
                constraints.append(_constraint(label, verdict, actual, required, reason))

        residency = req["data_residency"]
        if residency == "No Restriction":
            constraints.append(_constraint("data residency", "NOT_APPLICABLE", profile.get("location"), None,
                                           "No additional data-residency constraint applies."))
        elif residency == "On-site Only":
            actual = profile.get("data_stays_onsite")
            if not _valid_capability("data_stays_onsite", actual):
                constraints.append(_constraint("data residency", "UNVERIFIED", actual, residency,
                                               "Cannot verify onsite residency because capability data is missing or invalid."))
            else:
                passed = actual is True
                constraints.append(_constraint("data residency", "PASS" if passed else "FAIL", actual, residency,
                                               "Infrastructure confirms data remains onsite." if passed else
                                               "Infrastructure is known not to keep data onsite."))
        else:
            actual = profile.get("location")
            if not _valid_capability("location", actual):
                constraints.append(_constraint("data residency", "UNVERIFIED", actual, req.get("permitted_region"),
                                               "Cannot verify permitted region because infrastructure location is missing or unknown."))
            else:
                # Matching is trimmed, case-insensitive, exact string equality.
                permitted = req["permitted_region"]
                passed = actual.strip().casefold() == permitted.strip().casefold()
                constraints.append(_constraint("data residency", "PASS" if passed else "FAIL", actual, permitted,
                                               f"Infrastructure location {actual.strip()} {'matches' if passed else 'does not match'} permitted region {permitted.strip()} (case-insensitive exact match)."))

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
