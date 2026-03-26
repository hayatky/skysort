from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

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
