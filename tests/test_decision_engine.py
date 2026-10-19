import copy

import pytest

from decision_engine import TIER_ORDER, WEIGHTS, evaluate_placement
from ai_explainer import explain_assessment


REQ = {
    "max_latency_ms": 20,
    "data_must_stay_onsite": True,
    "min_compute": "medium",
    "required_bandwidth_mbps": 50,
    "max_monthly_cost": 300,
}
DEMO = {
    "on_device": {"latency_ms": 5, "data_stays_onsite": True, "compute": "low", "bandwidth_mbps": 100, "monthly_cost": 0},
    "far_edge": {"latency_ms": 12, "data_stays_onsite": True, "compute": "high", "bandwidth_mbps": 200, "monthly_cost": 180},
    "regional_edge": {"latency_ms": 35, "data_stays_onsite": False, "compute": "high", "bandwidth_mbps": 500, "monthly_cost": 220},
    "cloud": {"latency_ms": 80, "data_stays_onsite": False, "compute": "high", "bandwidth_mbps": 1000, "monthly_cost": 260},
}


def uniform_profiles(profile=None):
    base = profile or {"latency_ms": 5, "data_stays_onsite": True, "compute": "high", "bandwidth_mbps": 100, "monthly_cost": 100}
    return {tier: copy.deepcopy(base) for tier in TIER_ORDER}


def tier_result(result, tier):
    return next(row for row in result["tiers"] if row["tier"] == tier)


def test_demonstration_scenario_status_and_recommendation():
    result = evaluate_placement(REQ, DEMO)
    assert result["valid"] is True
    assert {row["tier"]: row["status"] for row in result["tiers"]} == {
        "on_device": "INFEASIBLE", "far_edge": "FEASIBLE",
        "regional_edge": "INFEASIBLE", "cloud": "INFEASIBLE",
    }
    assert result["recommendation"] == "far_edge"
    assert [entry["tier"] for entry in result["ranking"]] == ["far_edge"]


@pytest.mark.parametrize(("field", "value", "req_field", "req_value", "constraint"), [
    ("latency_ms", 21, "max_latency_ms", 20, "latency"),
    ("data_stays_onsite", False, "data_must_stay_onsite", True, "onsite residency"),
    ("compute", "low", "min_compute", "medium", "compute"),
    ("bandwidth_mbps", 49, "required_bandwidth_mbps", 50, "bandwidth"),
    ("monthly_cost", 301, "max_monthly_cost", 300, "monthly cost"),
])
def test_each_hard_constraint_fails_above_or_below_boundary(field, value, req_field, req_value, constraint):
    req = dict(REQ)
    req[req_field] = req_value
    profiles = uniform_profiles()
    profiles["far_edge"][field] = value
    tier = tier_result(evaluate_placement(req, profiles), "far_edge")
    assert tier["status"] == "INFEASIBLE"
    assert next(c for c in tier["constraints"] if c["constraint"] == constraint)["status"] == "FAIL"


@pytest.mark.parametrize(("field", "value", "req_field", "req_value"), [
    ("latency_ms", 20, "max_latency_ms", 20),
    ("data_stays_onsite", True, "data_must_stay_onsite", True),
    ("compute", "medium", "min_compute", "medium"),
    ("bandwidth_mbps", 50, "required_bandwidth_mbps", 50),
    ("monthly_cost", 300, "max_monthly_cost", 300),
])
def test_hard_constraint_boundaries_are_inclusive(field, value, req_field, req_value):
    req = dict(REQ)
    req[req_field] = req_value
    profiles = uniform_profiles()
    profiles["far_edge"][field] = value
    assert tier_result(evaluate_placement(req, profiles), "far_edge")["status"] == "FEASIBLE"


@pytest.mark.parametrize(("minimum", "compute", "expected"), [
    ("low", "low", "FEASIBLE"), ("low", "medium", "FEASIBLE"), ("low", "high", "FEASIBLE"),
    ("medium", "low", "INFEASIBLE"), ("medium", "medium", "FEASIBLE"), ("medium", "high", "FEASIBLE"),
    ("high", "low", "INFEASIBLE"), ("high", "medium", "INFEASIBLE"), ("high", "high", "FEASIBLE"),
])
def test_compute_ordering(minimum, compute, expected):
    req = dict(REQ, min_compute=minimum)
    profiles = uniform_profiles()
    profiles["far_edge"]["compute"] = compute
    assert tier_result(evaluate_placement(req, profiles), "far_edge")["status"] == expected


def test_onsite_constraint_is_not_applicable_when_not_required():
    result = evaluate_placement(dict(REQ, data_must_stay_onsite=False), uniform_profiles())
    constraint = next(c for c in tier_result(result, "far_edge")["constraints"] if c["constraint"] == "onsite residency")
    assert constraint["status"] == "NOT_APPLICABLE"
    assert constraint["required"] is None


@pytest.mark.parametrize("field", ["latency_ms", "data_stays_onsite", "compute", "bandwidth_mbps", "monthly_cost"])
def test_each_missing_capability_makes_tier_unverified(field):
    profiles = uniform_profiles()
    del profiles["far_edge"][field]
    tier = tier_result(evaluate_placement(REQ, profiles), "far_edge")
    assert tier["status"] == "UNVERIFIED"
    assert tier["score"] is None and tier["score_breakdown"] is None
    assert any(c["status"] == "UNVERIFIED" for c in tier["constraints"])


@pytest.mark.parametrize(("field", "value"), [
    ("latency_ms", -1), ("latency_ms", float("nan")), ("data_stays_onsite", 1),
    ("compute", "extreme"), ("bandwidth_mbps", "100"), ("monthly_cost", float("inf")),
])
def test_invalid_capability_values_are_unverified(field, value):
    profiles = uniform_profiles()
    profiles["far_edge"][field] = value
    assert tier_result(evaluate_placement(REQ, profiles), "far_edge")["status"] == "UNVERIFIED"


@pytest.mark.parametrize("mutator", [
    lambda r: r.pop("max_latency_ms"),
    lambda r: r.update(max_latency_ms=-1),
    lambda r: r.update(max_latency_ms=True),
    lambda r: r.update(data_must_stay_onsite=1),
    lambda r: r.update(min_compute="ultra"),
    lambda r: r.update(min_compute=[]),
    lambda r: r.update(extra_field=1),
])
def test_invalid_requirement_inputs_return_empty_invalid_assessment(mutator):
    req = dict(REQ)
    mutator(req)
    result = evaluate_placement(req, DEMO)
    assert result["valid"] is False and result["errors"]
    assert result["tiers"] == result["ranking"] == []
    assert result["recommendation"] is None


def test_known_failure_takes_precedence_over_unknown_and_reports_both():
    profiles = uniform_profiles()
    profiles["far_edge"].update(latency_ms=30, compute=None)
    tier = tier_result(evaluate_placement(REQ, profiles), "far_edge")
    assert tier["status"] == "INFEASIBLE"
    assert any(c["status"] == "FAIL" for c in tier["constraints"])
    assert any(c["status"] == "UNVERIFIED" for c in tier["constraints"])


def test_malformed_and_extra_profile_data_is_rejected():
    assert evaluate_placement(REQ, {"on_device": {}})["valid"] is False
    profiles = uniform_profiles()
    profiles["far_edge"]["gpu"] = True
    assert evaluate_placement(REQ, profiles)["valid"] is False
    assert evaluate_placement(REQ, {**uniform_profiles(), "other": {}})["valid"] is False


def test_malformed_mapping_keys_return_errors_instead_of_raising():
    req = dict(REQ)
    req[3] = "unexpected"
    result = evaluate_placement(req, {**uniform_profiles(), 3: {}})
    assert result["valid"] is False
    assert result["errors"]


def test_extremely_large_integer_requirement_is_rejected_without_overflow():
    req = dict(REQ, max_latency_ms=10**10000)
    result = evaluate_placement(req, uniform_profiles())
    assert result["valid"] is False
    assert any("finite nonnegative" in error for error in result["errors"])


def test_scores_and_ranking_only_include_feasible_tiers():
    result = evaluate_placement(REQ, DEMO)
    for row in result["tiers"]:
        if row["status"] == "FEASIBLE":
            assert row["score"] is not None and row["score_breakdown"] is not None
        else:
            assert row["score"] is None and row["score_breakdown"] is None
    assert all(tier_result(result, item["tier"])["status"] == "FEASIBLE" for item in result["ranking"])


def test_no_feasible_tier_has_no_recommendation():
    profiles = uniform_profiles()
    for profile in profiles.values():
        profile["compute"] = "low"
    result = evaluate_placement(REQ, profiles)
    assert not result["ranking"]
    assert result["recommendation"] is None


def test_zero_boundary_scoring_and_exact_weights():
    req = {"max_latency_ms": 0, "data_must_stay_onsite": False, "min_compute": "low",
           "required_bandwidth_mbps": 0, "max_monthly_cost": 0}
    profile = {"latency_ms": 0, "data_stays_onsite": False, "compute": "low", "bandwidth_mbps": 0, "monthly_cost": 0}
    tier = tier_result(evaluate_placement(req, uniform_profiles(profile)), "far_edge")
    assert tier["score"] == 80.0
    assert {name: factor["weight"] for name, factor in tier["score_breakdown"].items() if name != "total_score"} == WEIGHTS
    assert tier["score_breakdown"]["compute"]["normalized_value"] == 0
    assert all(tier["score_breakdown"][name]["normalized_value"] == 1
               for name in ("latency", "data_residency", "bandwidth", "monthly_cost"))
    assert sum(f["weighted_points"] for k, f in tier["score_breakdown"].items() if k != "total_score") == pytest.approx(0.8)


def test_score_breakdown_arithmetic_matches_score():
    tier = tier_result(evaluate_placement(REQ, DEMO), "far_edge")
    breakdown = tier["score_breakdown"]
    assert tier["score"] == round(100 * sum(breakdown[k]["weighted_points"] for k in WEIGHTS), 2)
    assert breakdown["total_score"] == tier["score"]


def test_ties_use_canonical_tier_order_and_are_deterministic():
    result = evaluate_placement(REQ, uniform_profiles())
    assert [entry["tier"] for entry in result["ranking"]] == list(TIER_ORDER)
    assert [entry["rank"] for entry in result["ranking"]] == [1, 2, 3, 4]
    assert result == evaluate_placement(REQ, uniform_profiles())


def test_reasons_exist_for_every_status_and_constraint():
    result = evaluate_placement(REQ, DEMO)
    for tier in result["tiers"]:
        assert tier["reasons"]
        assert all(constraint["reason"] for constraint in tier["constraints"])


def test_local_explanation_uses_real_assessment_without_ai_service():
    assessment = evaluate_placement(REQ, DEMO)
    explanation = explain_assessment(assessment)
    assert "Far Edge" in explanation
    assert "suitability score" in explanation
    assert "not a probability" in explanation
    assert "On Device is infeasible" in explanation
    assert "Far Edge is feasible" in explanation
    assert "Regional Edge is infeasible" in explanation
    assert "Cloud is infeasible" in explanation
    for label in ("latency:", "onsite residency:", "compute:", "bandwidth:", "monthly cost:"):
        assert label in explanation
    assert explanation == explain_assessment(assessment)


def test_local_explanation_handles_no_confirmed_feasible_tier():
    profiles = uniform_profiles()
    for profile in profiles.values():
        profile["compute"] = "low"
    explanation = explain_assessment(evaluate_placement(REQ, profiles))
    assert "No placement is recommended" in explanation


def test_local_explanation_identifies_unknown_capability_and_its_effect():
    profiles = uniform_profiles()
    for profile in profiles.values():
        profile["latency_ms"] = None
    tier = evaluate_placement(REQ, profiles)
    explanation = explain_assessment(tier)
    assert "latency: UNVERIFIED" in explanation
    assert "missing or invalid" in explanation
    assert "actual: None" in explanation
    assert "No placement is recommended" in explanation

