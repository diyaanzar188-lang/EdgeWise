"""Streamlit-level tests for the user-visible assessment workflow."""

from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import ai_explainer
from decision_engine import evaluate_placement
from infrastructure_data import DEFAULT_REQUIREMENTS, get_demo_profiles

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture(autouse=True)
def disable_live_explanation_api(monkeypatch):
    monkeypatch.setattr(ai_explainer, "_load_local_env", lambda: None)
    monkeypatch.setenv("QUALCOMM_IMAGINE_API_KEY", "")


def _click(at: AppTest, label: str) -> None:
    next(button for button in at.button if button.label == label).click()
    at.run(timeout=30)
    assert not at.exception, [exception.message for exception in at.exception]


def _navigate(at: AppTest, page: str) -> None:
    at.session_state["page_menu"] = page
    at.run(timeout=30)
    assert not at.exception, [exception.message for exception in at.exception]


def _seed_current_assessment(at: AppTest, page="Placement Results"):
    requirements, profiles = deepcopy(DEFAULT_REQUIREMENTS), get_demo_profiles()
    at.session_state["requirements"] = requirements
    at.session_state["profiles"] = profiles
    at.session_state["requirements_done"] = True
    at.session_state["profiles_done"] = True
    at.session_state["assessment"] = evaluate_placement(requirements, profiles)
    at.session_state["assessment_requirements_snapshot"] = deepcopy(requirements)
    at.session_state["assessment_profiles_snapshot"] = deepcopy(profiles)
    at.session_state["assessment_id"] = "test-assessment"
    at.session_state["assessment_created_at"] = "2026-10-19T00:00:00+00:00"
    at.session_state["page_menu"] = page
    return at.run(timeout=30)


def test_full_workflow_saves_assesses_reviews_and_explains():
    at = AppTest.from_file(APP_PATH).run(timeout=30)
    assert not at.exception
    _click(at, "Start assessment")
    _click(at, "Save Requirements & Continue")
    assert at.session_state["page_menu"] == "Infrastructure Data Source"
    _click(at, "Save Infrastructure & Continue")
    assert at.session_state["page_menu"] == "Infrastructure Assessment"
    _click(at, "Run Assessment")
    assert at.session_state["page_menu"] == "Placement Results"
    assert at.session_state["assessment_id"]
    assert at.session_state["assessment_created_at"]
    assert at.session_state["assessment"]["recommendation"] == "far_edge"
    assert len(at.dataframe) >= 1  # comparison and feasible-tier score details
    _click(at, "Understand the Decision")
    assert at.session_state["page_menu"] == "Decision Explanation"
    assert at.session_state["explanation_generated_for_assessment_id"] == at.session_state["assessment_id"]
    assert any("On Device is infeasible" in str(element.value) for element in at.markdown)
    assert not at.exception


def test_custom_source_selection_survives_streamlit_rerun():
    at = AppTest.from_file(APP_PATH).run(timeout=30)
    _navigate(at, "Infrastructure Data Source")
    at.radio(key="profile_source_mode").set_value("Custom data")
    at.run(timeout=30)
    assert at.radio(key="profile_source_mode").value == "Custom data"
    assert not at.exception, [exception.message for exception in at.exception]


def test_understand_workflow_step_routes_to_explanation_for_current_result():
    at = AppTest.from_file(APP_PATH)
    _seed_current_assessment(at)
    assert not at.exception
    at.button(key="workflow_step_4").click()
    at.run(timeout=30)
    assert at.session_state["page_menu"] == "Decision Explanation"
    assert any("Monthly cost:" in str(element.value) for element in at.markdown)
    assert not at.exception, [exception.message for exception in at.exception]


def test_explanation_rejects_result_when_saved_profiles_changed():
    at = AppTest.from_file(APP_PATH)
    _seed_current_assessment(at, page="Decision Explanation")
    changed = deepcopy(at.session_state["profiles"])
    changed["far_edge"]["monthly_cost"] = 181
    at.session_state["profiles"] = changed
    at.run(timeout=30)
    assert any("outdated" in str(message.value).lower() for message in at.warning)
    assert not any("highest-ranked confirmed feasible tier" in str(element.value) for element in at.markdown)
    assert not at.exception, [exception.message for exception in at.exception]


def test_explanation_stage_completes_only_after_generation():
    at = AppTest.from_file(APP_PATH)
    _seed_current_assessment(at, page="Placement Results")
    assert at.session_state["explanation_generated_for_assessment_id"] is None
    _click(at, "Understand the Decision")
    assert at.session_state["explanation_generated_for_assessment_id"] == "test-assessment"
    assert at.session_state["understood"] is True


def test_new_assessment_clears_prior_result_but_keeps_saved_inputs():
    at = AppTest.from_file(APP_PATH)
    _seed_current_assessment(at)
    _click(at, "Start New Assessment")
    assert at.session_state["assessment"] is None
    assert at.session_state["assessment_id"] is None
    assert at.session_state["page_menu"] == "Application Requirements"
    assert at.session_state["requirements"] == DEFAULT_REQUIREMENTS
    assert at.session_state["profiles"] == get_demo_profiles()


def test_missing_assessment_id_cannot_be_explained_as_current():
    at = AppTest.from_file(APP_PATH)
    _seed_current_assessment(at)
    at.session_state["assessment_id"] = None
    at.session_state["page_menu"] = "Decision Explanation"
    at.run(timeout=30)
    assert any("outdated" in str(message.value).lower() for message in at.warning)
    assert not at.exception, [exception.message for exception in at.exception]


def test_no_feasible_tier_still_has_a_truthful_explanation():
    at = AppTest.from_file(APP_PATH)
    requirements, profiles = deepcopy(DEFAULT_REQUIREMENTS), get_demo_profiles()
    for profile in profiles.values():
        profile.update(latency_ms=999, data_stays_onsite=False, compute="low",
                       bandwidth_mbps=0, monthly_cost=999)
    at.session_state["requirements"] = requirements
    at.session_state["profiles"] = profiles
    at.session_state["requirements_done"] = True
    at.session_state["profiles_done"] = True
    at.session_state["assessment"] = evaluate_placement(requirements, profiles)
    at.session_state["assessment_requirements_snapshot"] = deepcopy(requirements)
    at.session_state["assessment_profiles_snapshot"] = deepcopy(profiles)
    at.session_state["assessment_id"] = "no-feasible-tier"
    at.session_state["assessment_created_at"] = "2026-10-19T00:00:00+00:00"
    at.session_state["page_menu"] = "Placement Results"
    at.run(timeout=30)
    assert at.session_state["assessment"]["recommendation"] is None
    assert any("no tier has confirmed feasibility" in str(element.value).lower() for element in at.warning)
    _click(at, "Understand the Decision")
    assert any("no placement is recommended" in str(element.value).lower() for element in at.markdown)
    assert not at.exception, [exception.message for exception in at.exception]
