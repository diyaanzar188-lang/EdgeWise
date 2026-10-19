"""Local deterministic explanation for structured EdgeWise results."""

from infrastructure_data import TIER_LABELS


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
