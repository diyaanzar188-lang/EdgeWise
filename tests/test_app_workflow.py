"""Streamlit-level tests for the restored EdgeWise workflow."""

from copy import deepcopy
from pathlib import Path

from streamlit.testing.v1 import AppTest

from decision_engine import evaluate_placement
from infrastructure_data import DEFAULT_REQUIREMENTS, get_demo_profiles

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


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
    at.session_state["assessment_outdated"] = False
    at.session_state["page_menu"] = page
    return at.run(timeout=30)


def test_full_workflow_saves_assesses_reviews_and_explains():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not at.exception
    _click(at, "Define requirements  →")
    _click(at, "Save requirements")
    assert at.session_state["requirements"]["min_compute"] == "medium"
    assert at.session_state["requirements_done"] is True
    _click(at, "Continue to infrastructure data →")

    at.checkbox(key="demo_confirm").check()
    at.run(timeout=30)
    _click(at, "Use demo profiles")
    _click(at, "Continue to assessment →")
    _click(at, "Run Placement Assessment")
    assert at.session_state["assessment"]["recommendation"] == "far_edge"
    _click(at, "View Placement Results →")
    assert len(at.dataframe) >= 1

    at.checkbox(key="reviewed").check()
    at.run(timeout=30)
    _click(at, "Continue to Decision Explanation →")
    assert at.session_state["page_menu"] == "Decision Explanation"
    assert any("Far Edge" in str(element.value) for element in at.markdown)
    assert not at.exception


def test_custom_source_selection_survives_streamlit_rerun():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    _navigate(at, "Infrastructure Data Source")
    at.radio(key="source_mode").set_value("Custom configuration")
    at.run(timeout=30)
    assert at.radio(key="source_mode").value == "Custom configuration"
    assert not at.exception, [exception.message for exception in at.exception]


def test_custom_configuration_can_be_confirmed_and_applied():
    at = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    _navigate(at, "Infrastructure Data Source")
    at.radio(key="source_mode").set_value("Custom configuration")
    at.run(timeout=30)
    assert at.checkbox(key="custom_confirm").disabled is False
    at.checkbox(key="custom_confirm").check()
    at.run(timeout=30)
    _click(at, "Validate and apply custom profiles")
    assert at.session_state["profiles_mode"] == "Custom configuration"
    assert at.session_state["profiles_done"] is True
    assert not at.exception


def test_stale_assessment_is_not_shown_as_current():
    at = AppTest.from_file(str(APP_PATH))
    _seed_current_assessment(at, page="Decision Explanation")
    at.session_state["assessment_outdated"] = True
    at.run(timeout=30)
    assert at.session_state["assessment_outdated"] is True
    assert any("current assessment" in str(message.value).lower() for message in at.info)
    assert not any("Executive summary" in str(element.value) for element in at.markdown)
    assert not at.exception


def test_no_feasible_tier_still_has_a_truthful_explanation():
    at = AppTest.from_file(str(APP_PATH))
    requirements, profiles = deepcopy(DEFAULT_REQUIREMENTS), get_demo_profiles()
    for profile in profiles.values():
        profile.update(latency_ms=999, data_stays_onsite=False, compute="low",
                       bandwidth_mbps=0, monthly_cost=999)
    at.session_state["requirements"] = requirements
    at.session_state["profiles"] = profiles
    at.session_state["requirements_done"] = True
    at.session_state["profiles_done"] = True
    at.session_state["assessment"] = evaluate_placement(requirements, profiles)
    at.session_state["assessment_outdated"] = False
    at.session_state["page_menu"] = "Placement Results"
    at.run(timeout=30)
    assert at.session_state["assessment"]["recommendation"] is None
    assert any("no tier has confirmed feasibility" in str(element.value).lower() for element in at.warning)
    at.checkbox(key="reviewed").check()
    at.run(timeout=30)
    _click(at, "Continue to Decision Explanation →")
    assert any("No placement is recommended" in str(element.value) for element in at.markdown)
    assert not at.exception
