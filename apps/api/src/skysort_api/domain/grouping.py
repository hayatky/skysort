from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Protocol


@dataclass(slots=True)
class PhotoCandidate:
    photo_id: str
    capture_timestamp_ms: int | None
    capture_order_index: int
    similarity_seed: float
    visual_features: dict[str, object] | None = None


class SimilarityBackend(Protocol):
    def score(self, previous: PhotoCandidate, current: PhotoCandidate) -> float:
        """Return normalized visual similarity in the 0.0 to 1.0 range."""


class SeedSimilarityBackend:
    def score(self, previous: PhotoCandidate, current: PhotoCandidate) -> float:
        return 1.0 - abs(current.similarity_seed - previous.similarity_seed)


class VisualSimilarityBackend:
    def score(self, previous: PhotoCandidate, current: PhotoCandidate) -> float:
        if not previous.visual_features or not current.visual_features:
            return SeedSimilarityBackend().score(previous, current)
        scores = [
            _hash_similarity(previous.visual_features.get("phash"), current.visual_features.get("phash")),
            _hash_similarity(previous.visual_features.get("dhash"), current.visual_features.get("dhash")),
            _hash_similarity(previous.visual_features.get("ahash"), current.visual_features.get("ahash")),
            _histogram_similarity(previous.visual_features.get("color_histogram"), current.visual_features.get("color_histogram")),
        ]
        available = [score for score in scores if score is not None]
        if not available:
            return SeedSimilarityBackend().score(previous, current)
        return sum(available) / len(available)


def should_start_new_group(
    previous: PhotoCandidate | None,
    current: PhotoCandidate,
    time_proximity_seconds: int,
    similarity_threshold: float,
    similarity_backend: SimilarityBackend | None = None,
) -> bool:
    return grouping_boundary_reason(
        [previous] if previous is not None else [],
        current,
        time_proximity_seconds,
        similarity_threshold,
        similarity_backend=similarity_backend,
    ) is not None


def grouping_boundary_reason(
    current_group: list[PhotoCandidate],
    current: PhotoCandidate,
    time_proximity_seconds: int,
    similarity_threshold: float,
    similarity_backend: SimilarityBackend | None = None,
) -> str | None:
    if not current_group:
        return "job_start"
    previous = current_group[-1]
    if previous.capture_timestamp_ms is not None and current.capture_timestamp_ms is not None:
        distance_seconds = abs(current.capture_timestamp_ms - previous.capture_timestamp_ms) / 1000.0
        if distance_seconds > time_proximity_seconds:
            return "time_gap"
    elif current.capture_order_index - previous.capture_order_index > max(3, time_proximity_seconds):
        return "metadata_gap"

    backend = similarity_backend or VisualSimilarityBackend()
    anchors = _group_similarity_anchors(current_group)
    best_similarity = max(backend.score(anchor, current) for anchor in anchors)
    if best_similarity < similarity_threshold:
        return "similarity_gap"
    return None


def max_group_similarity(
    current_group: list[PhotoCandidate],
    current: PhotoCandidate,
    similarity_backend: SimilarityBackend | None = None,
) -> float:
    if not current_group:
        return 1.0
    backend = similarity_backend or VisualSimilarityBackend()
    return max(backend.score(anchor, current) for anchor in _group_similarity_anchors(current_group))


def _group_similarity_anchors(current_group: list[PhotoCandidate]) -> list[PhotoCandidate]:
    anchors = [current_group[0]]
    for candidate in current_group[-3:]:
        if candidate.photo_id not in {anchor.photo_id for anchor in anchors}:
            anchors.append(candidate)
    return anchors


def _hash_similarity(previous: object, current: object) -> float | None:
    if not previous or not current:
        return None
    try:
        previous_int = int(str(previous), 16)
        current_int = int(str(current), 16)
    except ValueError:
        return None
    bit_count = max(len(str(previous)), len(str(current))) * 4
    if bit_count <= 0:
        return None
    distance = (previous_int ^ current_int).bit_count()
    return max(0.0, min(1.0, 1.0 - (distance / bit_count)))


def _histogram_similarity(previous: object, current: object) -> float | None:
    if not isinstance(previous, list) or not isinstance(current, list) or len(previous) != len(current):
        return None
    try:
        left = [float(value) for value in previous]
        right = [float(value) for value in current]
    except (TypeError, ValueError):
        return None
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return None
    return max(0.0, min(1.0, numerator / (left_norm * right_norm)))
