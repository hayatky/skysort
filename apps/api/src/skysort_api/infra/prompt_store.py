from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .settings import get_settings


def load_prompt(name: str) -> tuple[str, str]:
    settings = get_settings()
    path = settings.prompt_template_dir / f"{name}.txt"
    if not path.exists():
        fallback = Path(__file__).resolve().parent / "prompts" / f"{name}.txt"
        path = fallback
    body = path.read_text(encoding="utf-8")
    return body, sha256(body.encode("utf-8")).hexdigest()
