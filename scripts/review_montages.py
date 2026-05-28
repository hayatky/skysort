from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class ReviewPhoto:
    path: Path
    name: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class ReviewGroup:
    name: str
    expected_best: str
    photos: tuple[ReviewPhoto, ...]


def build_review_montages(
    review_html_path: Path,
    output_dir: Path,
    *,
    columns: int = 6,
    cell_width: int = 210,
    image_height: int = 140,
) -> dict[str, Any]:
    groups = _parse_review_html(review_html_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for group in groups:
        path = output_dir / f"{group.name}.jpg"
        _write_group_montage(group, path, columns=columns, cell_width=cell_width, image_height=image_height)
        files.append({"group": group.name, "path": str(path), "photo_count": len(group.photos)})
    return {
        "schema_version": "v1",
        "review_html": str(review_html_path),
        "output_dir": str(output_dir),
        "group_count": len(groups),
        "files": files,
    }


def write_manifest(manifest: dict[str, Any], output_dir: Path, stem: str = "human-review-montages") -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{stem}.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"json": str(path)}


def _parse_review_html(path: Path) -> list[ReviewGroup]:
    html = path.read_text(encoding="utf-8")
    groups = []
    for section in re.findall(r'<section class="group">(.*?)</section>', html, flags=re.S):
        name_match = re.search(r"<strong>(.*?)</strong>", section)
        if not name_match:
            continue
        best_match = re.search(r"<code>best=(.*?)</code>", section)
        groups.append(
            ReviewGroup(
                name=unescape(name_match.group(1)),
                expected_best=unescape(best_match.group(1)) if best_match else "",
                photos=tuple(_parse_photos(section)),
            )
        )
    return groups


def _parse_photos(section: str) -> list[ReviewPhoto]:
    photos = []
    for classes, article in re.findall(r'<article class="photo([^"]*)">(.*?)</article>', section, flags=re.S):
        image_match = re.search(r'<img src="file:///(.*?)" alt="(.*?)">', article)
        if not image_match:
            continue
        tags = []
        if "best" in classes:
            tags.append("BEST")
        if "pick" in classes:
            tags.append("PICK")
        if "reject" in classes:
            tags.append("REJECT")
        photos.append(
            ReviewPhoto(
                path=Path(unescape(image_match.group(1))),
                name=unescape(image_match.group(2)),
                tags=tuple(tags),
            )
        )
    return photos


def _write_group_montage(group: ReviewGroup, path: Path, *, columns: int, cell_width: int, image_height: int) -> None:
    if columns <= 0:
        raise ValueError("columns must be positive")
    font = ImageFont.load_default()
    label_height = 44
    header_height = 42
    rows = max(1, (len(group.photos) + columns - 1) // columns)
    sheet = Image.new("RGB", (columns * cell_width, header_height + rows * (image_height + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    draw.rectangle([0, 0, sheet.width, header_height], fill=(24, 33, 39))
    draw.text((10, 8), f"{group.name}  photos={len(group.photos)}  expected_best={group.expected_best}", fill="white", font=font)
    for index, photo in enumerate(group.photos):
        row, column = divmod(index, columns)
        x = column * cell_width
        y = header_height + row * (image_height + label_height)
        image = _load_photo(photo.path, cell_width=cell_width, image_height=image_height)
        image.thumbnail((cell_width - 12, image_height - 10))
        sheet.paste(image, (x + (cell_width - image.width) // 2, y + 5))
        outline = _outline_color(photo.tags)
        draw.rectangle([x + 2, y + 2, x + cell_width - 3, y + image_height + label_height - 3], outline=outline, width=3 if photo.tags else 1)
        draw.text((x + 6, y + image_height + 2), photo.name, fill=(24, 33, 39), font=font)
        draw.text((x + 6, y + image_height + 18), ",".join(photo.tags) if photo.tags else "normal", fill=outline, font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=92)


def _load_photo(path: Path, *, cell_width: int, image_height: int) -> Image.Image:
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        return Image.new("RGB", (cell_width, image_height), (230, 230, 230))


def _outline_color(tags: tuple[str, ...]) -> tuple[int, int, int]:
    if "REJECT" in tags:
        return (160, 80, 80)
    if "BEST" in tags or "PICK" in tags:
        return (47, 125, 99)
    return (216, 221, 215)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build visual montage sheets from a SkySort benchmark review HTML file.")
    parser.add_argument("--review-html", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("var/tmp/human-review-montages"))
    parser.add_argument("--columns", type=int, default=6)
    parser.add_argument("--stem", default="human-review-montages")
    args = parser.parse_args()

    manifest = build_review_montages(args.review_html, args.output_dir, columns=args.columns)
    print(json.dumps(write_manifest(manifest, args.output_dir, stem=args.stem), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
