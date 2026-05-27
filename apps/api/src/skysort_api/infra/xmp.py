from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .settings import get_settings


RAW_EXTENSIONS = {".arw"}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}
SUPPORTED_EXTENSIONS = RAW_EXTENSIONS | JPEG_EXTENSIONS


def build_desired_tags(
    rating: int | None,
    selection_status: str,
    pick: bool,
    best_cut: bool,
    reviewed: bool,
) -> dict[str, str]:
    tags: dict[str, str] = {}
    if selection_status == "rejected":
        tags["XMP:Rating"] = "-1"
    elif rating is not None:
        tags["XMP:Rating"] = str(rating)
    tags["XMP-skysort:Pick"] = "True" if pick else "False"
    tags["XMP-skysort:BestCut"] = "True" if best_cut else "False"
    tags["XMP-skysort:Reviewed"] = "True" if reviewed else "False"
    return tags


def build_xmp_summary(file_path: str, rating: int | None, selection_status: str, pick: bool, best_cut: bool, reviewed: bool) -> str:
    desired = build_desired_tags(rating, selection_status, pick, best_cut, reviewed)
    rendered = ", ".join(f"{key}={value}" for key, value in desired.items())
    return f"{file_path}: {rendered}"


def can_write(file_path: str) -> tuple[bool, str | None]:
    suffix = Path(file_path).suffix.lower()
    if suffix in SUPPORTED_EXTENSIONS:
        return True, None
    return False, "unsupported_format"


def exiftool_available() -> bool:
    settings = get_settings()
    try:
        result = subprocess.run([settings.exiftool_path, "-ver"], capture_output=True, check=False, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def inspect_existing_tags(file_path: str) -> dict[str, str]:
    settings = get_settings()
    if not exiftool_available():
        return {}
    result = subprocess.run(
        [
            settings.exiftool_path,
            "-j",
            "-XMP:Rating",
            "-XMP-skysort:Pick",
            "-XMP-skysort:BestCut",
            "-XMP-skysort:Reviewed",
            file_path,
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return {}
    payload = json.loads(result.stdout or "[]")
    if not payload:
        return {}
    item = payload[0]
    return {
        "XMP:Rating": str(item.get("Rating")) if item.get("Rating") is not None else "",
        "XMP-skysort:Pick": str(item.get("Pick")) if item.get("Pick") is not None else "",
        "XMP-skysort:BestCut": str(item.get("BestCut")) if item.get("BestCut") is not None else "",
        "XMP-skysort:Reviewed": str(item.get("Reviewed")) if item.get("Reviewed") is not None else "",
    }


def detect_conflict(file_path: str, desired_tags: dict[str, str]) -> dict[str, Any] | None:
    existing = inspect_existing_tags(file_path)
    if not existing:
        return None
    diff = {
        key: {"current": existing.get(key, ""), "desired": value}
        for key, value in desired_tags.items()
        if existing.get(key, "") not in {"", value}
    }
    if not diff:
        return None
    return {"file_path": file_path, "diff": diff}


def write_tags(
    file_path: str,
    rating: int | None,
    selection_status: str,
    pick: bool,
    best_cut: bool,
    reviewed: bool,
) -> tuple[bool, str]:
    settings = get_settings()
    target = Path(file_path)
    suffix = target.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return False, "unsupported_format"
    if not exiftool_available():
        return False, "exiftool_not_available"

    tags = build_desired_tags(rating, selection_status, pick, best_cut, reviewed)
    args = [settings.exiftool_path]
    if suffix in RAW_EXTENSIONS:
        sidecar = str(target.with_suffix(".xmp"))
        if "/" in file_path and "\\" not in file_path:
            sidecar = sidecar.replace("\\", "/")
        args.extend(["-o", sidecar])
    else:
        args.append("-overwrite_original")
    for key, value in tags.items():
        args.append(f"-{key}={value}")
    args.append(str(target))
    result = subprocess.run(args, capture_output=True, check=False, text=True)
    if result.returncode != 0:
        return False, result.stderr.strip() or "exiftool_failed"
    return True, "written"
