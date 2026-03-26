from __future__ import annotations

import hashlib
import os
from pathlib import Path

import xxhash


SUPPORTED_EXTENSIONS = {".arw", ".jpg", ".jpeg", ".png"}


def normalize_root_path(root_path: str) -> Path:
    path = Path(root_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")
    return path


def iter_photo_files(root: Path, recursive: bool, file_types: list[str]) -> list[Path]:
    allowed = {extension.lower() for extension in file_types} if file_types else SUPPORTED_EXTENSIONS
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted([path for path in iterator if path.is_file() and path.suffix.lower() in allowed])


def compute_fast_hash(path: Path) -> str:
    stat = path.stat()
    hasher = xxhash.xxh3_64()
    with path.open("rb") as handle:
        hasher.update(handle.read(1024 * 1024))
    hasher.update(str(stat.st_size).encode("utf-8"))
    return hasher.hexdigest()


def file_metadata(path: Path) -> tuple[int, float]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime


def build_source_signature(path: Path | str, file_hash: str, file_size: int, file_mtime: float) -> str:
    normalized = str(Path(path).expanduser().resolve())
    payload = f"{normalized}|{file_hash}|{file_size}|{int(file_mtime * 1000)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
