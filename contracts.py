"""Shared JSON-friendly contracts for EdgeWise placement assessments."""

from typing import Literal, NotRequired, TypedDict

TierId = Literal["on_device", "far_edge", "regional_edge", "cloud"]
ComputeLevel = Literal["low", "medium", "high"]
TierStatus = Literal["FEASIBLE", "INFEASIBLE", "UNVERIFIED"]
ConstraintStatus = Literal["PASS", "FAIL", "UNVERIFIED", "NOT_APPLICABLE"]


class ApplicationRequirements(TypedDict):
    max_latency_ms: float
    data_must_stay_onsite: bool
    min_compute: ComputeLevel
    required_bandwidth_mbps: float
    max_monthly_cost: float


class InfrastructureProfile(TypedDict):
    latency_ms: NotRequired[float | None]
    data_stays_onsite: NotRequired[bool | None]
    compute: NotRequired[ComputeLevel | None]
    bandwidth_mbps: NotRequired[float | None]
    monthly_cost: NotRequired[float | None]


class InfrastructureProfiles(TypedDict):
    on_device: InfrastructureProfile
    far_edge: InfrastructureProfile
    regional_edge: InfrastructureProfile
    cloud: InfrastructureProfile


class ConstraintResult(TypedDict):
    constraint: str
    status: ConstraintStatus
    actual: object
    required: object
    reason: str


class ScoreFactor(TypedDict):
    weight: float
    normalized_value: float
    weighted_points: float


class ScoreBreakdown(TypedDict):
    latency: ScoreFactor
    data_residency: ScoreFactor
    compute: ScoreFactor
    bandwidth: ScoreFactor
    monthly_cost: ScoreFactor
    total_score: float


class TierAssessment(TypedDict):
    tier: TierId
    status: TierStatus
    reasons: list[str]
    constraints: list[ConstraintResult]
    score: float | None
    score_breakdown: ScoreBreakdown | None


class RankingEntry(TypedDict):
    tier: TierId
    score: float
    rank: int


class PlacementAssessment(TypedDict):
    valid: bool
    errors: list[str]
    tiers: list[TierAssessment]
    ranking: list[RankingEntry]
    recommendation: TierId | None
