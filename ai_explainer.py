"""Local deterministic explanation for structured EdgeWise results."""

from infrastructure_data import TIER_LABELS

FACTOR_LABELS = {
    "latency": "Latency",
    "data_residency": "Data residency",
    "compute": "Compute",
    "bandwidth": "Bandwidth",
    "monthly_cost": "Monthly cost",
}


def _constraint_explanation(constraint: dict) -> str:
    actual = repr(constraint.get("actual"))
    required = repr(constraint.get("required"))
    return (f"{constraint['constraint']}: {constraint['status']}. {constraint['reason']} "
            f"(actual: {actual}; required: {required}).")


def explain_assessment(assessment: dict) -> str:
    """Explain every tier and constraint from a valid structured assessment."""
    if not assessment.get("valid"):
        details = " ".join(assessment.get("errors", []))
        return f"This assessment could not be evaluated because its inputs are invalid. {details}".strip()

    recommendation = assessment.get("recommendation")
    if recommendation is None:
        summary = "No placement is recommended because no tier has confirmed feasibility."
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
            summary += " Its score reflects these trade-offs: " + "; ".join(factors) + "."

    tiers = []
    for tier in assessment.get("tiers", []):
        tier_name = TIER_LABELS.get(tier.get("tier"), str(tier.get("tier", "Unknown tier")))
        detail = " ".join(_constraint_explanation(item) for item in tier.get("constraints", []))
        status_reasons = " ".join(tier.get("reasons", []))
        tier_text = f"**{tier_name} is {str(tier.get('status', 'unknown')).lower()}.** {status_reasons}"
        if detail:
            tier_text += " " + detail
        tiers.append(tier_text)
    return summary + "\n\n" + "\n\n".join(tiers)
