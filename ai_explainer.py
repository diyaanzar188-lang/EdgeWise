"""Deterministic and Qualcomm AI explanations for structured EdgeWise results."""

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


@dataclass(frozen=True)
class DecisionExplanation:
    text: str
    source: str


def explain_assessment(assessment: dict) -> str:
    """Describe the current result without changing or reinterpreting it."""
    if not assessment.get("valid"):
        details = " ".join(assessment.get("errors", []))
        return f"This assessment could not be evaluated because its inputs are invalid. {details}".strip()
    recommendation = assessment.get("recommendation")
    if recommendation is None:
        unverified = [TIER_LABELS[t["tier"]] for t in assessment["tiers"] if t["status"] == "UNVERIFIED"]
        if unverified:
            return ("No placement is recommended because no tier has confirmed feasibility. "
                    "Some tiers remain unverified because capability information is missing or invalid: "
                    + ", ".join(unverified) + ".")
        return "No placement is recommended because none of the configured tiers satisfies every hard constraint."

    chosen = next(t for t in assessment["tiers"] if t["tier"] == recommendation)
    score = chosen["score"]
    failed = []
    for tier in assessment["tiers"]:
        if tier["status"] == "INFEASIBLE":
            failed.append(f"{TIER_LABELS[tier['tier']]}: " + " ".join(
                c["reason"] for c in tier["constraints"] if c["status"] == "FAIL"
            ))
    explanation = (f"{TIER_LABELS[recommendation]} is the highest-ranked confirmed feasible tier, "
                   f"with a suitability score of {score:.2f}/100. This score compares the configured "
                   "latency, data residency, compute, bandwidth, and monthly cost utilities; it is not a probability.")
    if failed:
        explanation += " Other tiers were excluded by hard constraints. " + " ".join(failed)
    return explanation


def _load_local_env() -> None:
    """Load simple KEY=VALUE entries from the project .env without overriding the process env."""
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
        key = key.strip()
        value = value.strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1]:
            value = value[1:-1]
        if key.startswith("QUALCOMM_IMAGINE_"):
            os.environ.setdefault(key, value)


def _model_explanation(requirements: dict, assessment: dict) -> str:
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
                    "Explain the supplied EdgeWise assessment in clear language. Treat its result as authoritative. "
                    "Do not calculate, alter, infer, or recommend any feasibility, scores, ranking, or placement. "
                    "Explain only what the provided requirements and assessment say."
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
    """Explain an existing engine result; use the deterministic text on any API failure."""
    try:
        return DecisionExplanation(_model_explanation(requirements, result), "Qualcomm Imagine AI")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return DecisionExplanation(explain_assessment(result), "Deterministic fallback")
