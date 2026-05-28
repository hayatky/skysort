from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image


_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "review_montages.py"
_SPEC = importlib.util.spec_from_file_location("review_montages", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
review_montages = importlib.util.module_from_spec(_SPEC)
sys.modules["review_montages"] = review_montages
_SPEC.loader.exec_module(review_montages)

build_review_montages = review_montages.build_review_montages


def test_review_montages_builds_group_contact_sheet_from_review_html(tmp_path: Path) -> None:
    image_path = tmp_path / "thumb.jpg"
    Image.new("RGB", (80, 60), (100, 120, 140)).save(image_path)
    html = tmp_path / "review.html"
    html.write_text(
        f"""
        <section class="group">
        <strong>group_a</strong>
        <code>best=DSC0001.JPG</code>
        <article class="photo best pick">
        <img src="file:///{image_path.as_posix()}" alt="DSC0001.JPG">
        </article>
        <article class="photo reject">
        <img src="file:///{image_path.as_posix()}" alt="DSC0002.JPG">
        </article>
        </section>
        """,
        encoding="utf-8",
    )

    manifest = build_review_montages(html, tmp_path / "montages", columns=2)

    assert manifest["group_count"] == 1
    assert manifest["files"][0]["group"] == "group_a"
    assert manifest["files"][0]["photo_count"] == 2
    assert Path(manifest["files"][0]["path"]).exists()
