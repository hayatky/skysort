from skysort_api.infra.xmp import build_desired_tags, can_write, write_tags


def test_build_desired_tags_skips_zero_rating_for_normal_items() -> None:
    tags = build_desired_tags(None, "normal", False, True, False)

    assert "XMP:Rating" not in tags
    assert tags["XMP-skysort:BestCut"] == "True"


def test_can_write_rejects_png() -> None:
    allowed, reason = can_write("/tmp/sample.png")

    assert allowed is False
    assert reason == "unsupported_format"


def test_write_tags_uses_sidecar_for_arw(isolated_runtime, monkeypatch) -> None:
    calls = []

    def fake_run(args, **_kwargs):
        calls.append(args)

        class Result:
            returncode = 0
            stdout = "12.00"
            stderr = ""

        return Result()

    monkeypatch.setattr("skysort_api.infra.xmp.subprocess.run", fake_run)

    success, message = write_tags("/tmp/sample.ARW", 5, "normal", True, False, True)

    assert success is True
    assert message == "written"
    assert calls[0][-1] == "-ver"
    assert "-o" in calls[1]
    assert "/tmp/sample.xmp" in calls[1]
    assert "-overwrite_original" not in calls[1]


def test_write_tags_overwrites_jpeg_evaluation_fields(isolated_runtime, monkeypatch) -> None:
    calls = []

    def fake_run(args, **_kwargs):
        calls.append(args)

        class Result:
            returncode = 0
            stdout = "12.00"
            stderr = ""

        return Result()

    monkeypatch.setattr("skysort_api.infra.xmp.subprocess.run", fake_run)

    success, _ = write_tags("/tmp/sample.jpg", None, "rejected", False, True, False)

    assert success is True
    assert "-overwrite_original" in calls[1]
    assert "-o" not in calls[1]
    assert "-XMP:Rating=-1" in calls[1]
