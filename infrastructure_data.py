"""Illustrative default data for the EdgeWise placement advisor."""

from copy import deepcopy
import math
from collections.abc import Mapping

DEFAULT_REQUIREMENTS = {
    "max_latency_ms": 20,
    "data_must_stay_onsite": True,
    "min_compute": "medium",
    "required_bandwidth_mbps": 50,
    "max_monthly_cost": 300,
}

DEMO_PROFILES = {
    "on_device": {"latency_ms": 5, "data_stays_onsite": True, "compute": "low", "bandwidth_mbps": 100, "monthly_cost": 0},
    "far_edge": {"latency_ms": 12, "data_stays_onsite": True, "compute": "high", "bandwidth_mbps": 200, "monthly_cost": 180},
    "regional_edge": {"latency_ms": 35, "data_stays_onsite": False, "compute": "high", "bandwidth_mbps": 500, "monthly_cost": 220},
    "cloud": {"latency_ms": 80, "data_stays_onsite": False, "compute": "high", "bandwidth_mbps": 1000, "monthly_cost": 260},
}

TIER_LABELS = {
    "on_device": "On Device",
    "far_edge": "Far Edge",
    "regional_edge": "Regional Edge",
    "cloud": "Cloud",
}

REQUIREMENT_FIELDS = {
    "max_latency_ms", "data_must_stay_onsite", "min_compute",
    "required_bandwidth_mbps", "max_monthly_cost",
}
CAPABILITY_FIELDS = {
    "latency_ms", "data_stays_onsite", "compute", "bandwidth_mbps", "monthly_cost",
}
TIER_IDS = {"on_device", "far_edge", "regional_edge", "cloud"}


def _valid_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except (OverflowError, TypeError, ValueError):
        return False


def validate_requirements(requirements):
    """Return actionable errors for the exact five-field requirements schema."""
    if not isinstance(requirements, Mapping):
        return ["Requirements must be an object with the five supported fields."]
    errors = []
    errors.extend(f"Missing requirement field: {key}." for key in sorted(REQUIREMENT_FIELDS - set(requirements)))
    errors.extend(f"Unsupported requirement field: {key}." for key in sorted(set(requirements) - REQUIREMENT_FIELDS, key=str))
    for key in ("max_latency_ms", "required_bandwidth_mbps", "max_monthly_cost"):
        if key in requirements and not _valid_number(requirements[key]):
            errors.append(f"{key} must be a finite nonnegative number.")
    if "data_must_stay_onsite" in requirements and type(requirements["data_must_stay_onsite"]) is not bool:
        errors.append("data_must_stay_onsite must be true or false.")
    if "min_compute" in requirements and requirements["min_compute"] not in ("low", "medium", "high"):
        errors.append("min_compute must be low, medium, or high.")
    return errors


def validate_profiles(profiles):
    """Validate tier/profile shape and capability values without filling unknowns."""
    if not isinstance(profiles, Mapping):
        return ["Infrastructure profiles must be an object keyed by the four supported tiers."]
    errors = []
    errors.extend(f"Missing infrastructure tier: {tier}." for tier in sorted(TIER_IDS - set(profiles)))
    errors.extend(f"Unsupported infrastructure tier: {tier}." for tier in sorted(set(profiles) - TIER_IDS, key=str))
    for tier in TIER_IDS & set(profiles):
        profile = profiles[tier]
        if not isinstance(profile, Mapping):
            errors.append(f"{tier} must contain a capability object.")
            continue
        extras = set(profile) - CAPABILITY_FIELDS
        errors.extend(f"{tier} has unsupported capability field: {field}." for field in sorted(extras, key=str))
        for field, value in profile.items():
            if field not in CAPABILITY_FIELDS or value is None:
                continue
            if field in {"latency_ms", "bandwidth_mbps", "monthly_cost"} and not _valid_number(value):
                errors.append(f"{tier}.{field} must be a finite nonnegative number or null.")
            elif field == "data_stays_onsite" and type(value) is not bool:
                errors.append(f"{tier}.{field} must be true, false, or null.")
            elif field == "compute" and value not in ("low", "medium", "high"):
                errors.append(f"{tier}.{field} must be low, medium, high, or null.")
    return errors


def get_demo_profiles():
    """Return a fresh copy so UI edits cannot mutate the source defaults."""
    return deepcopy(DEMO_PROFILES)
