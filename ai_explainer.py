"""Deterministic local explanations with an optional Qualcomm AI enhancement.

The placement engine remains authoritative. The optional model receives the
already-computed inputs and result and can only produce explanatory prose.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from infrastructure_data import TIER_LABELS

DEFAULT_MODEL = "Llama-3.1-8B"
REQUEST_TIMEOUT_SECONDS = 15

FACTOR_LABELS = {
    "latency": "Latency",
    "data_residency": "Data residency",
    "compute": "Compute",
    "bandwidth": "Bandwidth",
    "monthly_cost": "Monthly cost",
}


@dataclass(frozen=True)
class DecisionExplanation:
    text: str
    source: str


def _constraint_explanation(constraint: dict) -> str:
    actual = repr(constraint.get("actual"))
    required = repr(constraint.get("required"))
    return (f"{constraint['constraint']}: {constraint['status']}. {constraint['reason']} "
            f"(actual: {actual}; required: {required}).")


def explain_assessment(assessment: dict) -> str:
    """Return a deterministic explanation derived only from the engine result."""
    if not assessment.get("valid"):
        details = " ".join(assessment.get("errors", []))
        return f"This assessment could not be evaluated because its inputs are invalid. {details}".strip()

    recommendation = assessment.get("recommendation")
    if recommendation is None:
        summary = "No placement is recommended because no tier has confirmed feasibility."
        unverified = [TIER_LABELS.get(tier.get("tier"), str(tier.get("tier")))
                      for tier in assessment.get("tiers", []) if tier.get("status") == "UNVERIFIED"]
        if unverified:
            summary += " Feasibility remains unconfirmed for: " + ", ".join(unverified) + "."
        elif assessment.get("tiers"):
            summary += " The configured tiers failed one or more known hard constraints."
    else:
        chosen = next(t for t in assessment["tiers"] if t["tier"] == recommendation)
        score = chosen["score"]
        summary = (f"{TIER_LABELS[recommendation]} is the highest-ranked confirmed feasible tier, "
                   f"with a suitability score of {score:.2f}/100. The score is a weighted comparison, "
                   "not a probability.")
        breakdown = chosen.get("score_breakdown") or {}
        factors = []
        for key, label in FACTOR_LABELS.items():
            factor = breakdown.get(key)
            if factor is not None:
                factors.append(
                    f"{label}: utility {factor['normalized_value']:.2f} × "
                    f"{factor['weight']:.0%} weight = {factor['weighted_points'] * 100:.2f} points"
                )
        if factors:
            summary += " Score trade-offs: " + "; ".join(factors) + "."

    tier_explanations = []
    for tier in assessment.get("tiers", []):
        tier_id = tier.get("tier", "Unknown tier")
        tier_name = TIER_LABELS.get(tier_id, str(tier_id))
        status = str(tier.get("status", "unknown")).lower()
        reasons = " ".join(tier.get("reasons", []))
        constraints = " ".join(_constraint_explanation(item) for item in tier.get("constraints", []))
        detail = f"**{tier_name} is {status}.** {reasons}"
        if constraints:
            detail += " " + constraints
        tier_explanations.append(detail.strip())
    return summary + ("\n\n" + "\n\n".join(tier_explanations) if tier_explanations else "")


def _load_local_env() -> None:
    """Load project-local Qualcomm settings without overriding process env."""
    env_path = Path(__file__).with_name(".env")
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1]:
            value = value[1:-1]
        if key.startswith("QUALCOMM_IMAGINE_"):
            os.environ.setdefault(key, value)


def _model_explanation(requirements: dict, assessment: dict) -> str:
    """Request prose about a fixed result; never ask the model to decide."""
    _load_local_env()
    api_key = os.getenv("QUALCOMM_IMAGINE_API_KEY")
    endpoint = os.getenv("QUALCOMM_IMAGINE_ENDPOINT")
    model = os.getenv("QUALCOMM_IMAGINE_MODEL") or DEFAULT_MODEL
    if not api_key or not endpoint:
        raise ValueError("Qualcomm Imagine API configuration is incomplete")

    request_url = endpoint.rstrip("/")
    if not request_url.endswith("/chat/completions"):
        request_url += "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Explain the supplied EdgeWise assessment in clear language. Treat the supplied result as "
                    "authoritative. Do not calculate, alter, infer, or recommend feasibility, scores, ranking, or "
                    "placement. Explain only what the supplied requirements and assessment state."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"requirements": requirements, "assessment": assessment}, allow_nan=False),
            },
        ],
        "temperature": 0.2,
    }
    request = Request(
        request_url,
        data=json.dumps(payload, allow_nan=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        response_data = json.loads(response.read().decode("utf-8"))
    text = response_data["choices"][0]["message"]["content"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Qualcomm Imagine returned an empty explanation")
    return text.strip()


def explain_decision(requirements: dict, result: dict) -> DecisionExplanation:
    """Use optional Qualcomm prose, falling back to local deterministic text."""
    try:
        text = _model_explanation(requirements, result)
        return DecisionExplanation(text, "Qualcomm Imagine AI")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError,
            IndexError, TypeError, json.JSONDecodeError):
        return DecisionExplanation(explain_assessment(result), "Deterministic fallback")
