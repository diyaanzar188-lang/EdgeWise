"""Deterministic local explanations with an optional Qualcomm AI enhancement.

The placement engine remains authoritative. The optional model receives the
already-computed inputs and result and can only produce explanatory prose.
"""

from __future__ import annotations

import json
import os
import re
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


def _concise_assessment_summary(assessment: dict) -> str:
    """Return a short deterministic summary derived only from the engine result."""
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
        summary = (f"{TIER_LABELS[recommendation]} is recommended because it is the highest-ranked "
                   "confirmed feasible tier and confirmed to meet every applicable hard constraint, "
                   f"with a suitability score of {score:.2f}/100. The score is a weighted comparison, "
                   "not a probability.")
        breakdown = chosen.get("score_breakdown") or {}
        factors = {
            key: factor for key, factor in breakdown.items()
            if key != "total_score" and isinstance(factor, dict)
        }
        ordered = sorted(factors, key=lambda key: factors[key].get("normalized_value", 1.0))
        if len(ordered) > 1 and factors[ordered[0]].get("normalized_value") < factors[ordered[1]].get("normalized_value"):
            summary += f" Its weakest scored dimension is {FACTOR_LABELS.get(ordered[0], ordered[0]).lower()}."
    return summary


def explain_assessment(assessment: dict, *, include_details: bool = False) -> str:
    """Describe the engine result; optionally include per-tier evidence for the UI."""
    summary = _concise_assessment_summary(assessment)
    if not include_details or not assessment.get("valid"):
        return summary

    recommendation = assessment.get("recommendation")
    if recommendation is not None:
        chosen = next((tier for tier in assessment.get("tiers", []) if tier.get("tier") == recommendation), {})
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
            summary += " Score details: " + "; ".join(factors) + "."

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


def _summary_evidence(assessment: dict) -> dict:
    """Return only engine evidence needed to summarize the current recommendation."""
    if not assessment.get("valid"):
        return {"valid": False, "errors": assessment.get("errors", [])}

    recommendation = assessment.get("recommendation")
    if recommendation is None:
        return {
            "valid": True,
            "recommendation": None,
            "tier_statuses": [
                {"tier": TIER_LABELS.get(tier["tier"], tier["tier"]), "status": tier["status"], "reasons": tier["reasons"]}
                for tier in assessment.get("tiers", [])
            ],
        }

    selected = next((tier for tier in assessment.get("tiers", []) if tier["tier"] == recommendation), None)
    if selected is None:
        return {"valid": True, "recommendation": TIER_LABELS.get(recommendation, recommendation), "evidence_error": "Recommended tier details are missing."}

    constraints = [
        {key: constraint.get(key) for key in ("constraint", "status", "actual", "required", "reason")}
        for constraint in selected.get("constraints", [])
    ]
    score_breakdown = selected.get("score_breakdown") or {}
    score_factors = {
        name: {"normalized_value": factor.get("normalized_value")}
        for name, factor in score_breakdown.items()
        if name != "total_score"
    }
    return {
        "valid": True,
        "recommendation": TIER_LABELS.get(recommendation, recommendation),
        "status": selected.get("status"),
        "reasons": selected.get("reasons", []),
        "constraints": constraints,
        "score_factors": score_factors,
    }


def _response_is_supported(text: str, assessment: dict) -> bool:
    """Reject numeric claims absent from the recommendation evidence and constraint contradictions."""
    evidence = _summary_evidence(assessment)
    evidence_numbers = {float(value) for value in re.findall(r"\b\d+(?:\.\d+)?\b", json.dumps(evidence))}
    response_numbers = {float(value) for value in re.findall(r"\b\d+(?:\.\d+)?\b", text)}
    if not response_numbers.issubset(evidence_numbers):
        return False

    selected = next(
        (tier for tier in assessment.get("tiers", []) if tier.get("tier") == assessment.get("recommendation")),
        None,
    )
    if selected is None:
        denial = re.search(r"\bno (?:placement|tier|recommendation)\b", text, re.IGNORECASE)
        recommendation_claim = re.search(r"\b(?:recommend(?:ed|ation)?|should run|should be placed)\b", text, re.IGNORECASE)
        if recommendation_claim and not denial:
            return False
        return True

    for tier_id, label in TIER_LABELS.items():
        if tier_id != selected["tier"] and (
            re.search(rf"\b{re.escape(tier_id)}\b", text, re.IGNORECASE)
            or re.search(rf"\b{re.escape(label)}\b", text, re.IGNORECASE)
        ):
            return False

    negative_claim = re.compile(
        r"\b(?:above|over|exceed\w*)\b.{0,60}\b(?:maximum|max|limit|threshold|requirement)\b"
        r"|\b(?:fail\w*|does not meet|doesn't meet|not within)\b.{0,60}\b(?:maximum|max|limit|threshold|requirement)\b"
    )
    positive_claim = re.compile(
        r"\b(?:within|meet\w*|satisf\w*|pass\w*)\b.{0,60}\b(?:maximum|max|limit|threshold|requirement)\b"
    )
    for constraint in selected.get("constraints", []):
        label = str(constraint.get("constraint", "")).lower()
        if not label or constraint.get("status") not in {"PASS", "FAIL"}:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", text.lower()):
            if label not in sentence:
                continue
            if constraint["status"] == "PASS" and negative_claim.search(sentence):
                return False
            if constraint["status"] == "FAIL" and positive_claim.search(sentence):
                return False
    return True


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


def _model_explanation(assessment: dict) -> str:
    """Request concise prose about engine-provided evidence; never ask the model to decide."""
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
                    "Write a concise EdgeWise executive summary in 2-3 sentences. Treat the supplied assessment "
                    "as authoritative. State the recommended tier using its supplied display name and explain why it "
                    "is suitable using only its supplied status, reasons, and constraint evidence. Never reinterpret "
                    "constraint statuses or required values. Do not invent thresholds, latency limits, acceptable "
                    "values, capabilities, trade-offs, or other facts. Mention a trade-off only when directly supported "
                    "by the supplied evidence; otherwise omit it. Do not list every constraint or score. Never calculate, "
                    "alter, infer, or recommend any feasibility, score, ranking, or placement. If there is no "
                    "recommendation, briefly explain that from the supplied statuses."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"assessment_evidence": _summary_evidence(assessment)}, allow_nan=False),
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
    text = text.strip()
    if not _response_is_supported(text, assessment):
        raise ValueError("Qualcomm Imagine returned claims unsupported by the assessment evidence")
    return text


def explain_decision(requirements: dict, result: dict) -> DecisionExplanation:
    """Use optional Qualcomm prose, falling back to local deterministic text."""
    try:
        text = _model_explanation(result)
        return DecisionExplanation(text, "Qualcomm Imagine AI")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError,
            IndexError, TypeError, json.JSONDecodeError):
        return DecisionExplanation(explain_assessment(result), "Deterministic fallback")
