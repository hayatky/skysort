from skysort_api.domain.grouping import PhotoCandidate, should_start_new_group


def test_grouping_splits_on_time_gap() -> None:
    previous = PhotoCandidate("a", 0, 0, 0.1)
    current = PhotoCandidate("b", 10000, 1, 0.1)
    assert should_start_new_group(previous, current, 5, 0.7)


def test_grouping_keeps_similar_candidates_together() -> None:
    previous = PhotoCandidate("a", 0, 0, 0.1)
    current = PhotoCandidate("b", 2000, 1, 0.12)
    assert not should_start_new_group(previous, current, 5, 0.7)
