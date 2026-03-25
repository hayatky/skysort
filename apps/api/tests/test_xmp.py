from skysort_api.infra.xmp import build_desired_tags, can_write


def test_build_desired_tags_skips_zero_rating_for_normal_items() -> None:
    tags = build_desired_tags(None, "normal", False, True, False)

    assert "XMP:Rating" not in tags
    assert tags["XMP-skysort:BestCut"] == "True"


def test_can_write_rejects_png() -> None:
    allowed, reason = can_write("/tmp/sample.png")

    assert allowed is False
    assert reason == "unsupported_format"
