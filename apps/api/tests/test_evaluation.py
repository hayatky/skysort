from skysort_api.domain.evaluation import (
    SemanticMetrics,
    TechnicalMetrics,
    compute_technical_total,
    final_rating_from_scores,
    provisional_rating_from_technical,
    provisional_rating_from_technical_decision,
)


def test_provisional_rating_rejects_low_scores() -> None:
    assert provisional_rating_from_technical(12) == (None, "rejected")


def test_provisional_rating_decision_rejects_high_risk_scores() -> None:
    assert provisional_rating_from_technical_decision(84, reject_risk_score=82) == (None, "rejected")
    assert provisional_rating_from_technical_decision(84, reject_risk_score=20) == (5, "normal")


def test_technical_total_stays_bounded() -> None:
    total = compute_technical_total(
        TechnicalMetrics(
            sharpness_score=90,
            motion_blur_score=80,
            highlight_clip_ratio=0.01,
            shadow_clip_ratio=0.02,
        )
    )
    assert 0 <= total <= 100


def test_final_rating_uses_semantic_scores() -> None:
    rating, selection_status, evaluation_status = final_rating_from_scores(
        80,
        SemanticMetrics(
            semantic_score=90,
            composition_score=90,
            subject_state_score=85,
            rarity_score=70,
        ),
    )
    assert rating == 5
    assert selection_status == "normal"
    assert evaluation_status == "final"
