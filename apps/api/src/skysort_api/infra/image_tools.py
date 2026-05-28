from __future__ import annotations

import base64
import io
from datetime import datetime, timezone
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageOps

from .file_scan import build_source_signature
from .settings import get_settings

try:
    import rawpy
except ImportError:  # pragma: no cover
    rawpy = None


RAW_EXTENSIONS = {".arw"}


def load_image(path: Path) -> Image.Image:
    image = _load_render_image(path)
    image = ImageOps.exif_transpose(image)
    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    return _convert_to_srgb(image)


def build_asset_cache_key(path: Path | str, file_hash: str, file_size: int, file_mtime: float) -> str:
    return build_source_signature(path, file_hash, file_size, file_mtime)


def asset_paths_for_signature(source_signature: str) -> tuple[Path, Path]:
    settings = get_settings()
    thumbs_dir = settings.cache_dir / "thumbs"
    previews_dir = settings.cache_dir / "previews"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    previews_dir.mkdir(parents=True, exist_ok=True)
    return thumbs_dir / f"{source_signature}.jpg", previews_dir / f"{source_signature}.jpg"


def ensure_preview_assets(path: Path, source_signature: str) -> tuple[Path, Path]:
    settings = get_settings()
    thumb_path, preview_path = asset_paths_for_signature(source_signature)

    if thumb_path.exists() and preview_path.exists():
        return thumb_path, preview_path

    image = load_image(path)
    _save_resized(image, thumb_path, settings.thumbnail_size, settings.preview_jpeg_quality)
    _save_resized(image, preview_path, settings.preview_size, settings.preview_jpeg_quality)
    return thumb_path, preview_path


def build_data_url(path: Path, max_side: int | None = None) -> str:
    image = load_image(path)
    if max_side is not None:
        image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=get_settings().preview_jpeg_quality, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def build_contact_sheet_data_url(items: list[tuple[str, Path]], max_side: int, quality: int) -> tuple[str, dict[str, str]]:
    labels = [chr(ord("A") + index) for index in range(len(items))]
    mapping = {label: photo_id for label, (photo_id, _path) in zip(labels, items, strict=True)}
    if not items:
        empty = Image.new("RGB", (256, 128), "white")
        return _image_to_data_url(empty, quality), mapping

    cell_side = max(160, min(max_side, 512))
    label_height = 34
    columns = min(3, len(items))
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_side, rows * (cell_side + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, (_photo_id, path)) in enumerate(zip(labels, items, strict=True)):
        column = index % columns
        row = index // columns
        x = column * cell_side
        y = row * (cell_side + label_height)
        image = load_image(path).copy()
        image.thumbnail((cell_side, cell_side))
        offset_x = x + ((cell_side - image.width) // 2)
        offset_y = y + label_height + ((cell_side - image.height) // 2)
        draw.rectangle([x, y, x + cell_side, y + label_height], fill=(18, 26, 34))
        draw.text((x + 12, y + 8), label, fill=(255, 255, 255))
        sheet.paste(image, (offset_x, offset_y))
    return _image_to_data_url(sheet, quality), mapping


def _save_resized(image: Image.Image, output_path: Path, max_side: int, quality: int) -> None:
    resized = image.copy()
    resized.thumbnail((max_side, max_side))
    resized.save(output_path, format="JPEG", quality=quality, optimize=True)


def _image_to_data_url(image: Image.Image, quality: int) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def extract_image_metadata(path: Path) -> dict[str, object]:
    image, exif = _load_metadata_source(path)
    width, height = ImageOps.exif_transpose(image).size
    capture_time = exif.get(36867) or exif.get(306)
    subsec = exif.get(37521) or exif.get(9291)
    capture_dt = _parse_capture_time(capture_time, subsec)
    return {
        "width": width,
        "height": height,
        "orientation": exif.get(274),
        "capture_time": capture_dt,
        "capture_timestamp_ms": int(capture_dt.timestamp() * 1000) if capture_dt else None,
        "camera_model": exif.get(272),
        "lens_model": exif.get(42036),
        "focal_length": _fraction_to_float(exif.get(37386)),
        "aperture": _fraction_to_float(exif.get(33437)),
        "iso": exif.get(34855),
        "shutter_speed": _fraction_to_string(exif.get(33434)),
    }


def compute_similarity_seed(path: Path) -> float:
    features = compute_visual_features(path)
    return int(str(features["phash"])[:4], 16) / 65535.0


def compute_visual_features(path: Path) -> dict[str, object]:
    image = load_image(path).resize((128, 128)).convert("RGB")
    histogram = _color_histogram(image)
    return {
        "phash": str(imagehash.phash(image)),
        "dhash": str(imagehash.dhash(image)),
        "ahash": str(imagehash.average_hash(image)),
        "color_histogram": histogram,
    }


def compute_technical_metrics(path: Path, highlight_threshold: int, shadow_threshold: int) -> dict[str, float]:
    image = load_image(path)
    grayscale = image.convert("L")
    grayscale.thumbnail((1024, 1024))
    frame = np.asarray(grayscale, dtype=np.float32)
    h, w = frame.shape
    gx, gy = np.gradient(frame)
    magnitude = np.sqrt((gx**2) + (gy**2))
    subject_mask = _subject_likelihood_mask(magnitude, h, w)
    focus_values = magnitude[subject_mask] if np.any(subject_mask) else magnitude.reshape(-1)
    sharpness_raw = float(np.percentile(focus_values, 92))
    texture_raw = float(np.percentile(focus_values, 75))
    sharpness = _logistic_score(sharpness_raw, midpoint=18.0, scale=7.0)
    motion_blur = _logistic_score((sharpness_raw * 0.65) + (texture_raw * 0.35), midpoint=14.0, scale=6.0)
    highlight = _weighted_clip_ratio(frame, subject_mask, highlight_threshold, above=True)
    shadow = _weighted_clip_ratio(frame, subject_mask, shadow_threshold, above=False)
    return {
        "sharpness_score": round(sharpness, 2),
        "motion_blur_score": round(motion_blur, 2),
        "highlight_clip_ratio": round(highlight, 4),
        "shadow_clip_ratio": round(shadow, 4),
    }


def _subject_likelihood_mask(magnitude: np.ndarray, height: int, width: int) -> np.ndarray:
    y0 = max(0, int(height * 0.15))
    y1 = min(height, int(height * 0.85))
    x0 = max(0, int(width * 0.10))
    x1 = min(width, int(width * 0.90))
    central = np.zeros_like(magnitude, dtype=bool)
    central[y0:y1, x0:x1] = True
    edge_threshold = float(np.percentile(magnitude[central], 70)) if np.any(central) else float(np.percentile(magnitude, 70))
    edge_mask = magnitude >= edge_threshold
    if np.count_nonzero(edge_mask & central) < max(16, magnitude.size // 200):
        return central
    return edge_mask & central


def _logistic_score(value: float, *, midpoint: float, scale: float) -> float:
    return float(100.0 / (1.0 + np.exp(-((value - midpoint) / scale))))


def _weighted_clip_ratio(frame: np.ndarray, subject_mask: np.ndarray, threshold: int, *, above: bool) -> float:
    clipped = frame >= threshold if above else frame <= threshold
    global_ratio = float(np.mean(clipped))
    if not np.any(subject_mask):
        return global_ratio
    subject_ratio = float(np.mean(clipped[subject_mask]))
    return (subject_ratio * 0.7) + (global_ratio * 0.3)


def _color_histogram(image: Image.Image) -> list[float]:
    frame = np.asarray(image, dtype=np.float32)
    values: list[float] = []
    for channel in range(3):
        histogram, _ = np.histogram(frame[:, :, channel], bins=16, range=(0, 256))
        values.extend(float(item) for item in histogram)
    total = sum(values) or 1.0
    return [round(value / total, 6) for value in values]


def _convert_to_srgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    try:
        srgb = ImageCms.createProfile("sRGB")
        profile = image.info.get("icc_profile")
        if not profile:
            return image.convert("RGB")
        source = ImageCms.ImageCmsProfile(io.BytesIO(profile))
        return ImageCms.profileToProfile(image, source, srgb, outputMode="RGB")
    except Exception:
        return image.convert("RGB")


def _parse_capture_time(value: object, subsec: object) -> datetime | None:
    if value is None:
        return None
    try:
        base = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    if subsec is None:
        return base
    digits = "".join(char for char in str(subsec) if char.isdigit())[:3]
    if not digits:
        return base
    return base.replace(microsecond=int(digits.ljust(3, "0")) * 1000)


def _fraction_to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            denominator = value.denominator or 1
            return float(value.numerator) / float(denominator)
        return float(value)
    except Exception:
        return None


def _fraction_to_string(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        denominator = value.denominator or 1
        if value.numerator == 1:
            return f"1/{denominator}"
        return f"{value.numerator}/{denominator}"
    return str(value)


def _load_render_image(path: Path) -> Image.Image:
    if path.suffix.lower() not in RAW_EXTENSIONS:
        return _open_image(path)
    preview_image, _ = _load_raw_preview(path)
    if preview_image is not None:
        return preview_image
    return _load_raw_postprocessed_image(path)


def _load_metadata_source(path: Path) -> tuple[Image.Image, Image.Exif]:
    if path.suffix.lower() not in RAW_EXTENSIONS:
        image = _open_image(path)
        return image, image.getexif()

    preview_image, preview_bytes = _load_raw_preview(path)
    if preview_image is not None:
        if preview_bytes is not None:
            with Image.open(io.BytesIO(preview_bytes)) as source:
                exif = source.getexif()
            return preview_image, exif
        return preview_image, preview_image.getexif()

    rendered = _load_raw_postprocessed_image(path)
    return rendered, Image.Exif()


def _load_raw_preview(path: Path) -> tuple[Image.Image | None, bytes | None]:
    if rawpy is None:
        raise RuntimeError("rawpy is required for ARW processing")
    with rawpy.imread(str(path)) as raw:
        try:
            thumbnail = raw.extract_thumb()
        except Exception:
            return None, None
        if thumbnail.format == rawpy.ThumbFormat.JPEG:
            return _open_image_from_bytes(thumbnail.data), bytes(thumbnail.data)
        if thumbnail.format == rawpy.ThumbFormat.BITMAP:
            return Image.fromarray(thumbnail.data), None
    return None, None


def _load_raw_postprocessed_image(path: Path) -> Image.Image:
    if rawpy is None:
        raise RuntimeError("rawpy is required for ARW processing")
    with rawpy.imread(str(path)) as raw:
        frame = raw.postprocess(use_camera_wb=True, no_auto_bright=False, output_bps=8)
    return Image.fromarray(frame)


def _open_image(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        return image.copy()


def _open_image_from_bytes(payload: bytes) -> Image.Image:
    with Image.open(io.BytesIO(payload)) as image:
        image.load()
        return image.copy()
