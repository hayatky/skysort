from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class PhotoCandidate:
    photo_id: str
    capture_timestamp_ms: int | None
    capture_order_index: int
    similarity_seed: float


class SimilarityBackend(Protocol):
    def score(self, previous: PhotoCandidate, current: PhotoCandidate) -> float:
        """Return normalized visual similarity in the 0.0 to 1.0 range."""


class SeedSimilarityBackend:
    def score(self, previous: PhotoCandidate, current: PhotoCandidate) -> float:
        return 1.0 - abs(current.similarity_seed - previous.similarity_seed)


def should_start_new_group(
    previous: PhotoCandidate | None,
    current: PhotoCandidate,
    time_proximity_seconds: int,
    similarity_threshold: float,
    similarity_backend: SimilarityBackend | None = None,
) -> bool:
    if previous is None:
        return True
    if previous.capture_timestamp_ms is not None and current.capture_timestamp_ms is not None:
        distance_seconds = abs(current.capture_timestamp_ms - previous.capture_timestamp_ms) / 1000.0
        if distance_seconds > time_proximity_seconds:
            return True
    else:
        if current.capture_order_index - previous.capture_order_index > max(3, time_proximity_seconds):
            return True

    backend = similarity_backend or SeedSimilarityBackend()
    similarity = backend.score(previous, current)
    return similarity < similarity_threshold
