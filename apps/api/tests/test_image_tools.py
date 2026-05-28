from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageFilter

from skysort_api.infra import image_tools


def _jpeg_preview_bytes() -> bytes:
    image = Image.new("RGB", (32, 20), (12, 34, 56))
    exif = Image.Exif()
    exif[272] = "Preview Cam"
    exif[36867] = "2026:03:26 12:34:56"
    exif[9291] = "321"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_arw_prefers_embedded_preview_for_render_and_metadata(monkeypatch, tmp_path: Path) -> None:
    preview_bytes = _jpeg_preview_bytes()
    calls = {"extract_thumb": 0, "postprocess": 0}

    class FakeRaw:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_thumb(self):
            calls["extract_thumb"] += 1
            return SimpleNamespace(format="jpeg", data=preview_bytes)

        def postprocess(self, **kwargs):
            calls["postprocess"] += 1
            raise AssertionError("postprocess should not be used when an embedded preview exists")

    fake_rawpy = SimpleNamespace(
        imread=lambda _: FakeRaw(),
        ThumbFormat=SimpleNamespace(JPEG="jpeg", BITMAP="bitmap"),
    )
    monkeypatch.setattr(image_tools, "rawpy", fake_rawpy)
    raw_path = tmp_path / "sample.arw"
    raw_path.write_bytes(b"raw-placeholder")

    image = image_tools.load_image(raw_path)
    metadata = image_tools.extract_image_metadata(raw_path)

    assert image.size == (32, 20)
    assert metadata["camera_model"] == "Preview Cam"
    assert metadata["capture_timestamp_ms"] is not None
    assert calls["extract_thumb"] >= 2
    assert calls["postprocess"] == 0


def test_compute_visual_features_contains_full_hashes_and_histogram(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    Image.new("RGB", (64, 64), (120, 80, 40)).save(image_path)

    features = image_tools.compute_visual_features(image_path)

    assert len(str(features["phash"])) == 16
    assert len(str(features["dhash"])) == 16
    assert len(str(features["ahash"])) == 16
    assert len(features["color_histogram"]) == 48
    assert abs(sum(features["color_histogram"]) - 1.0) < 0.001


def test_compute_technical_metrics_spreads_sharp_and_blurred_images(tmp_path: Path) -> None:
    sharp_path = tmp_path / "sharp.jpg"
    blur_path = tmp_path / "blur.jpg"
    image = Image.new("L", (128, 128), 128)
    for x in range(16, 112, 8):
        for y in range(16, 112):
            image.putpixel((x, y), 255 if (x // 8) % 2 else 0)
    image.convert("RGB").save(sharp_path)
    image.filter(ImageFilter.GaussianBlur(radius=5)).convert("RGB").save(blur_path)

    sharp = image_tools.compute_technical_metrics(sharp_path, 252, 3)
    blurred = image_tools.compute_technical_metrics(blur_path, 252, 3)

    assert sharp["sharpness_score"] - blurred["sharpness_score"] > 20
    assert sharp["motion_blur_score"] > blurred["motion_blur_score"]


def test_build_contact_sheet_data_url_labels_photo_ids(tmp_path: Path) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    Image.new("RGB", (40, 30), (255, 0, 0)).save(first)
    Image.new("RGB", (30, 40), (0, 0, 255)).save(second)

    data_url, mapping = image_tools.build_contact_sheet_data_url(
        [("photo_a", first), ("photo_b", second)],
        max_side=256,
        quality=80,
    )

    assert data_url.startswith("data:image/jpeg;base64,")
    assert mapping == {"A": "photo_a", "B": "photo_b"}
