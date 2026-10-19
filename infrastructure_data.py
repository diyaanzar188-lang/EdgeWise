"""Illustrative default data for the EdgeWise placement advisor."""

from copy import deepcopy

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


def get_demo_profiles():
    """Return a fresh copy so UI edits cannot mutate the source defaults."""
    return deepcopy(DEMO_PROFILES)
