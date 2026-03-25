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
    reason: str | None = None
    ai_failed: bool = False


def compute_technical_total(metrics: TechnicalMetrics) -> float:
    exposure_health = max(0.0, 100.0 - (metrics.highlight_clip_ratio * 100.0) - (metrics.shadow_clip_ratio * 60.0))
    total = (
        metrics.sharpness_score * 0.45
        + metrics.motion_blur_score * 0.25
        + exposure_health * 0.30
    )
    return round(max(0.0, min(total, 100.0)), 2)


def provisional_rating_from_technical(total: float, thresholds: Mapping[str, float] | None = None) -> tuple[int | None, str]:
    values = thresholds or {"reject": 20.0, "star_2": 48.0, "star_3": 64.0, "star_4": 78.0, "star_5": 83.0}
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


def final_rating_from_scores(
    technical_total: float,
    semantic: SemanticMetrics,
    weights: Mapping[str, float] | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> tuple[int | None, str, str]:
    configured_weights = weights or {"technical_quality": 0.35, "composition": 0.35, "subject_state": 0.20, "rarity": 0.10}
    configured_thresholds = thresholds or {"reject": 20.0, "star_2": 48.0, "star_3": 64.0, "star_4": 78.0, "star_5": 83.0}
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
