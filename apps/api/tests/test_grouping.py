from skysort_api.domain.grouping import PhotoCandidate, grouping_boundary_reason, max_group_similarity, should_start_new_group


def test_grouping_splits_on_time_gap() -> None:
    previous = PhotoCandidate("a", 0, 0, 0.1)
    current = PhotoCandidate("b", 10000, 1, 0.1)
    assert should_start_new_group(previous, current, 5, 0.7)


def test_grouping_keeps_similar_candidates_together() -> None:
    previous = PhotoCandidate("a", 0, 0, 0.1)
    current = PhotoCandidate("b", 2000, 1, 0.12)
    assert not should_start_new_group(previous, current, 5, 0.7)


def test_grouping_similarity_backend_can_be_swapped_for_embedding_scores() -> None:
    class EmbeddingBackend:
        def score(self, _previous: PhotoCandidate, _current: PhotoCandidate) -> float:
            return 0.95

    previous = PhotoCandidate("a", 0, 0, 0.1)
    current = PhotoCandidate("b", 2000, 1, 0.9)

    assert should_start_new_group(previous, current, 5, 0.7)
    assert not should_start_new_group(previous, current, 5, 0.7, similarity_backend=EmbeddingBackend())


def test_grouping_uses_recent_group_similarity_to_avoid_chain_breaks() -> None:
    first = PhotoCandidate("a", 0, 0, 0.10)
    drifted = PhotoCandidate("b", 1000, 1, 0.40)
    similar_to_first = PhotoCandidate("c", 2000, 2, 0.12)

    assert not grouping_boundary_reason([first, drifted], similar_to_first, 5, 0.85)
    assert max_group_similarity([first, drifted], similar_to_first) > 0.85


def test_grouping_boundary_reason_reports_similarity_gap() -> None:
    previous = PhotoCandidate("a", 0, 0, 0.10)
    current = PhotoCandidate("b", 1000, 1, 0.95)

    assert grouping_boundary_reason([previous], current, 5, 0.8) == "similarity_gap"
