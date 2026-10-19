import json
from urllib.error import HTTPError

import pytest

import ai_explainer
from ai_explainer import DecisionExplanation, explain_assessment, explain_decision
from decision_engine import evaluate_placement


REQUIREMENTS = {
    "max_latency_ms": 30,
    "data_must_stay_onsite": True,
    "min_compute": "medium",
    "required_bandwidth_mbps": 40,
    "max_monthly_cost": 250,
}
PROFILES = {
    "on_device": {"latency_ms": 5, "data_stays_onsite": True, "compute": "low", "bandwidth_mbps": 100, "monthly_cost": 0},
    "far_edge": {"latency_ms": 12, "data_stays_onsite": True, "compute": "high", "bandwidth_mbps": 200, "monthly_cost": 180},
    "regional_edge": {"latency_ms": 35, "data_stays_onsite": False, "compute": "high", "bandwidth_mbps": 500, "monthly_cost": 220},
    "cloud": {"latency_ms": 80, "data_stays_onsite": False, "compute": "high", "bandwidth_mbps": 1000, "monthly_cost": 260},
}


class MockResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


@pytest.fixture
def assessment():
    return evaluate_placement(REQUIREMENTS, PROFILES)


@pytest.fixture(autouse=True)
def configured_api(monkeypatch):
    monkeypatch.setattr(ai_explainer, "_load_local_env", lambda: None)
    monkeypatch.setenv("QUALCOMM_IMAGINE_API_KEY", "test-key")
    monkeypatch.setenv("QUALCOMM_IMAGINE_ENDPOINT", "https://example.invalid/chat/completions")
    monkeypatch.setenv("QUALCOMM_IMAGINE_MODEL", "Llama-3.1-8B")


def test_successful_response_labels_source_and_sends_authoritative_assessment_evidence(monkeypatch, assessment):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return MockResponse(json.dumps({"choices": [{"message": {"content": "Far Edge meets the stated criteria."}}]}).encode())

    monkeypatch.setattr(ai_explainer, "urlopen", fake_urlopen)
    explanation = explain_decision(REQUIREMENTS, assessment)

    assert explanation == DecisionExplanation("Far Edge meets the stated criteria.", "Qualcomm Imagine AI")
    assert captured["timeout"] == ai_explainer.REQUEST_TIMEOUT_SECONDS
    assert captured["request"].full_url == "https://example.invalid/chat/completions"
    sent = json.loads(captured["request"].data.decode())
    supplied = json.loads(sent["messages"][1]["content"])
    assert supplied == {"assessment_evidence": ai_explainer._summary_evidence(assessment)}
    assert supplied["assessment_evidence"]["recommendation"] == "Far Edge"
    assert supplied["assessment_evidence"]["status"] == "FEASIBLE"
    assert all(c["status"] == "PASS" for c in supplied["assessment_evidence"]["constraints"])
    assert "regional_edge" not in json.dumps(supplied)
    assert "cloud" not in json.dumps(supplied)
    assert sent["model"] == "Llama-3.1-8B"
    assert "2-3 sentences" in sent["messages"][0]["content"]
    assert "Mention a trade-off only when directly supported" in sent["messages"][0]["content"]
    assert "Do not invent thresholds, latency limits" in sent["messages"][0]["content"]
    assert "Never calculate, alter" in sent["messages"][0]["content"]
    assert assessment["recommendation"] == "far_edge"


def test_existing_chat_completions_path_is_not_duplicated(monkeypatch, assessment):
    monkeypatch.setenv("QUALCOMM_IMAGINE_ENDPOINT", "https://example.invalid/apis/v2/chat/completions")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return MockResponse(json.dumps({"choices": [{"message": {"content": "Assessment explanation."}}]}).encode())

    monkeypatch.setattr(ai_explainer, "urlopen", fake_urlopen)
    explain_decision(REQUIREMENTS, assessment)

    assert captured["url"] == "https://example.invalid/apis/v2/chat/completions"


def assert_deterministic_fallback(explanation, assessment):
    assert explanation.source == "Deterministic fallback"
    assert explanation.text == explain_assessment(assessment)


def test_missing_api_key_uses_deterministic_fallback(monkeypatch, assessment):
    monkeypatch.delenv("QUALCOMM_IMAGINE_API_KEY")
    monkeypatch.setattr(ai_explainer, "_load_local_env", lambda: None)
    monkeypatch.setattr(ai_explainer, "urlopen", lambda *args, **kwargs: pytest.fail("unexpected API request"))
    assert_deterministic_fallback(explain_decision(REQUIREMENTS, assessment), assessment)


def test_timeout_uses_deterministic_fallback(monkeypatch, assessment):
    monkeypatch.setattr(ai_explainer, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()))
    assert_deterministic_fallback(explain_decision(REQUIREMENTS, assessment), assessment)


def test_http_error_uses_deterministic_fallback(monkeypatch, assessment):
    def fail(*args, **kwargs):
        raise HTTPError("https://example.invalid", 503, "Unavailable", {}, None)

    monkeypatch.setattr(ai_explainer, "urlopen", fail)
    assert_deterministic_fallback(explain_decision(REQUIREMENTS, assessment), assessment)


@pytest.mark.parametrize("response_body", [b"not json", b"{}", b'{"choices": []}', b'{"choices": [{"message": {"content": "  "}}]}'])
def test_malformed_model_response_uses_deterministic_fallback(monkeypatch, assessment, response_body):
    monkeypatch.setattr(ai_explainer, "urlopen", lambda *args, **kwargs: MockResponse(response_body))
    assert_deterministic_fallback(explain_decision(REQUIREMENTS, assessment), assessment)


@pytest.mark.parametrize("model_text", [
    "Far Edge latency is 12 ms, above the 30 ms maximum, but all constraints pass.",
    "Far Edge meets the latency requirement, and a 20 ms limit is acceptable.",
    "Cloud is recommended for this workload.",
])
def test_unsupported_or_contradictory_constraint_claim_uses_fallback(monkeypatch, assessment, model_text):
    body = json.dumps({"choices": [{"message": {"content": model_text}}]}).encode()
    monkeypatch.setattr(ai_explainer, "urlopen", lambda *args, **kwargs: MockResponse(body))

    assert_deterministic_fallback(explain_decision(REQUIREMENTS, assessment), assessment)


def test_deterministic_recommendation_summary_is_concise_and_uses_supported_tradeoff(assessment):
    explanation = explain_assessment(assessment)

    assert "Far Edge is recommended" in explanation
    assert "confirmed to meet every applicable hard constraint" in explanation
    assert "weakest scored dimension is monthly cost" in explanation
    assert "not a probability" in explanation
    assert len(explanation.split(". ")) <= 3
    assert "Regional Edge:" not in explanation
    assert "Cloud:" not in explanation


def test_deterministic_no_recommendation_summary_stays_concise():
    profiles = {tier: dict(profile) for tier, profile in PROFILES.items()}
    for profile in profiles.values():
        profile["compute"] = "low"
    assessment = evaluate_placement(REQUIREMENTS, profiles)

    explanation = explain_assessment(assessment)

    assert "No placement is recommended" in explanation
    assert len(explanation.split(". ")) <= 2
