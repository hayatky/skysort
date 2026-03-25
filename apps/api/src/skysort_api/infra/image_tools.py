from __future__ import annotations

import base64
import io
from datetime import datetime, timezone
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image, ImageCms, ImageOps

from .settings import get_settings

try:
    import rawpy
except ImportError:  # pragma: no cover
    rawpy = None


RAW_EXTENSIONS = {".arw"}


def load_image(path: Path) -> Image.Image:
    suffix = path.suffix.lower()
    if suffix in RAW_EXTENSIONS:
        if rawpy is None:
            raise RuntimeError("rawpy is required for ARW processing")
        with rawpy.imread(str(path)) as raw:
            frame = raw.postprocess(use_camera_wb=True, no_auto_bright=False, output_bps=8)
        image = Image.fromarray(frame)
    else:
        image = Image.open(path)
    image = ImageOps.exif_transpose(image)
    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    return _convert_to_srgb(image)


def ensure_preview_assets(path: Path, photo_id: str) -> tuple[Path, Path]:
    settings = get_settings()
    thumbs_dir = settings.cache_dir / "thumbs"
    previews_dir = settings.cache_dir / "previews"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    previews_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumbs_dir / f"{photo_id}.jpg"
    preview_path = previews_dir / f"{photo_id}.jpg"

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


def _save_resized(image: Image.Image, output_path: Path, max_side: int, quality: int) -> None:
    resized = image.copy()
    resized.thumbnail((max_side, max_side))
    resized.save(output_path, format="JPEG", quality=quality, optimize=True)


def extract_image_metadata(path: Path) -> dict[str, object]:
    image = load_image(path)
    width, height = image.size
    exif = image.getexif()
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
    image = load_image(path).resize((64, 64))
    phash = str(imagehash.phash(image))
    return int(phash[:4], 16) / 65535.0


def compute_technical_metrics(path: Path, highlight_threshold: int, shadow_threshold: int) -> dict[str, float]:
    image = load_image(path).convert("L")
    frame = np.asarray(image, dtype=np.float32)
    h, w = frame.shape
    y0 = max(0, int(h * 0.2))
    y1 = min(h, int(h * 0.8))
    x0 = max(0, int(w * 0.2))
    x1 = min(w, int(w * 0.8))
    focus_region = frame[y0:y1, x0:x1]
    gx, gy = np.gradient(focus_region)
    magnitude = np.sqrt((gx ** 2) + (gy ** 2))
    sharpness = float(np.percentile(magnitude, 90))
    motion_blur = float(min(100.0, max(0.0, sharpness / 2.0)))
    normalized = min(100.0, sharpness / 3.0)
    highlight = float(np.mean(frame >= highlight_threshold))
    shadow = float(np.mean(frame <= shadow_threshold))
    return {
        "sharpness_score": round(normalized, 2),
        "motion_blur_score": round(motion_blur, 2),
        "highlight_clip_ratio": round(highlight, 4),
        "shadow_clip_ratio": round(shadow, 4),
    }


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
