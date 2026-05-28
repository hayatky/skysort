from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(slots=True)
class TechnicalMetrics:
    sharpness_score: float
    motion_blur_score: float
    highlight_clip_ratio: float
    shadow_clip_ratio: float


@dataclass(slots=True)
class SemanticMetrics:
    semantic_score: float | None = None
    composition_score: float | None = None
    subject_state_score: float | None = None
    rarity_score: float | None = None
    confidence_score: float | None = None
    problem_tags: list[str] | None = None
    reason: str | None = None
    ai_failed: bool = False


def compute_technical_total(metrics: TechnicalMetrics) -> float:
    exposure_health = exposure_health_from_clip(metrics.highlight_clip_ratio, metrics.shadow_clip_ratio)
    total = (
        metrics.sharpness_score * 0.45
        + metrics.motion_blur_score * 0.25
        + exposure_health * 0.30
    )
    return round(max(0.0, min(total, 100.0)), 2)


def exposure_health_from_clip(highlight_clip_ratio: float, shadow_clip_ratio: float) -> float:
    return max(0.0, 100.0 - (highlight_clip_ratio * 100.0) - (shadow_clip_ratio * 60.0))


def technical_candidate_quality(
    technical_score_total: float,
    sharpness_rank: float,
    exposure_rank: float,
    motion_blur_score: float,
) -> float:
    quality = (
        technical_score_total * 0.52
        + sharpness_rank * 0.24
        + exposure_rank * 0.16
        + motion_blur_score * 0.08
    )
    return round(max(0.0, min(100.0, quality)), 2)


def technical_reject_risk(
    highlight_clip_ratio: float,
    shadow_clip_ratio: float,
    motion_blur_score: float,
    sharpness_rank: float,
) -> float:
    exposure_risk = min(100.0, (highlight_clip_ratio * 180.0) + (shadow_clip_ratio * 140.0))
    blur_risk = max(0.0, 100.0 - motion_blur_score)
    relative_blur_risk = max(0.0, 100.0 - sharpness_rank)
    risk = exposure_risk * 0.35 + blur_risk * 0.35 + relative_blur_risk * 0.30
    return round(max(0.0, min(100.0, risk)), 2)


def provisional_rating_from_technical(total: float, thresholds: Mapping[str, float] | None = None) -> tuple[int | None, str]:
    values = thresholds or {"reject": 22.0, "star_2": 42.0, "star_3": 58.0, "star_4": 74.0, "star_5": 83.0}
    if total < values["reject"]:
        return None, "rejected"
    if total < values["star_2"]:
        return 1, "normal"
    if total < values["star_3"]:
        return 2, "normal"
    if total < values["star_4"]:
        return 3, "normal"
    if total < values["star_5"]:
        return 4, "normal"
    return 5, "normal"


def provisional_rating_from_technical_decision(
    decision_score: float,
    reject_risk_score: float | None = None,
    thresholds: Mapping[str, float] | None = None,
    reject_risk_threshold: float = 78.0,
) -> tuple[int | None, str]:
    if reject_risk_score is not None and reject_risk_score >= reject_risk_threshold:
        return None, "rejected"
    return provisional_rating_from_technical(decision_score, thresholds)


def final_rating_from_scores(
    technical_total: float,
    semantic: SemanticMetrics,
    weights: Mapping[str, float] | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> tuple[int | None, str, str]:
    configured_weights = weights or {"technical_quality": 0.35, "composition": 0.35, "subject_state": 0.20, "rarity": 0.10}
    configured_thresholds = thresholds or {"reject": 22.0, "star_2": 42.0, "star_3": 58.0, "star_4": 74.0, "star_5": 83.0}
    if semantic.ai_failed:
        provisional, selection = provisional_rating_from_technical(technical_total, configured_thresholds)
        return provisional, selection, "ai_eval_failed"

    comp = semantic.composition_score if semantic.composition_score is not None else technical_total
    subject = semantic.subject_state_score if semantic.subject_state_score is not None else technical_total
    rarity = semantic.rarity_score if semantic.rarity_score is not None else 50.0
    total = (
        technical_total * configured_weights["technical_quality"]
        + comp * configured_weights["composition"]
        + subject * configured_weights["subject_state"]
        + rarity * configured_weights["rarity"]
    )
    if total < configured_thresholds["reject"]:
        return None, "rejected", "final"
    if total < configured_thresholds["star_2"]:
        return 1, "normal", "final"
    if total < configured_thresholds["star_3"]:
        return 2, "normal", "final"
    if total < configured_thresholds["star_4"]:
        return 3, "normal", "final"
    if total < configured_thresholds["star_5"]:
        return 4, "normal", "final"
    return 5, "normal", "final"
