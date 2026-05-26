from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_SRC = Path(__file__).resolve().parents[1] / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from skysort_api.domain.grouping import PhotoCandidate, should_start_new_group  # noqa: E402


@dataclass(frozen=True)
class Scenario:
    name: str
    time_proximity_seconds: int
    similarity_threshold: float


def validate_grouping(fixture_path: Path) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if fixture.get("schema_version") != "v1":
        raise ValueError("grouping validation schema_version must be v1")
    candidates = [_candidate(item) for item in fixture.get("photos", []) if isinstance(item, dict)]
    scenarios = [_scenario(item) for item in fixture.get("scenarios", []) if isinstance(item, dict)]
    if not scenarios:
        scenarios = [Scenario(name="default", time_proximity_seconds=4, similarity_threshold=0.86)]

    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "photo_count": len(candidates),
        "scenarios": [_evaluate_scenario(candidates, scenario) for scenario in scenarios],
    }


def write_report(report: dict[str, Any], output_dir: Path, stem: str = "grouping-validation") -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report, md_path)
    return {"json": str(json_path), "markdown": str(md_path)}


def _candidate(item: dict[str, Any]) -> PhotoCandidate:
    return PhotoCandidate(
        photo_id=str(item.get("photo_id") or item.get("id") or item.get("relative_path")),
        capture_timestamp_ms=int(item["capture_timestamp_ms"]) if item.get("capture_timestamp_ms") is not None else None,
        capture_order_index=int(item.get("capture_order_index") or 0),
        similarity_seed=float(item.get("similarity_seed") or 0.0),
    )


def _scenario(item: dict[str, Any]) -> Scenario:
    return Scenario(
        name=str(item.get("name") or "scenario"),
        time_proximity_seconds=int(item.get("time_proximity_seconds", 4)),
        similarity_threshold=float(item.get("similarity_threshold", 0.86)),
    )


def _evaluate_scenario(candidates: list[PhotoCandidate], scenario: Scenario) -> dict[str, Any]:
    groups = _group_candidates(candidates, scenario)
    group_sizes = [len(group) for group in groups]
    return {
        "name": scenario.name,
        "time_proximity_seconds": scenario.time_proximity_seconds,
        "similarity_threshold": scenario.similarity_threshold,
        "group_count": len(groups),
        "single_group_count": sum(1 for size in group_sizes if size == 1),
        "average_group_size": round(sum(group_sizes) / len(group_sizes), 3) if group_sizes else 0,
        "groups": [[candidate.photo_id for candidate in group] for group in groups],
    }


def _group_candidates(candidates: list[PhotoCandidate], scenario: Scenario) -> list[list[PhotoCandidate]]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            item.capture_timestamp_ms if item.capture_timestamp_ms is not None else float("inf"),
            item.capture_order_index,
            item.photo_id,
        ),
    )
    groups: list[list[PhotoCandidate]] = []
    current: list[PhotoCandidate] = []
    previous: PhotoCandidate | None = None
    for candidate in ordered:
        if should_start_new_group(previous, candidate, scenario.time_proximity_seconds, scenario.similarity_threshold) and current:
            groups.append(current)
            current = []
        current.append(candidate)
        previous = candidate
    if current:
        groups.append(current)
    return groups


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# SkySort Grouping Validation",
        "",
        f"- photo_count: {report['photo_count']}",
        "",
        "| scenario | time proximity | similarity | groups | singles | average size |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in report["scenarios"]:
        lines.append(
            f"| {item['name']} | {item['time_proximity_seconds']} | {item['similarity_threshold']} | {item['group_count']} | {item['single_group_count']} | {item['average_group_size']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare SkySort grouping settings against a lightweight candidate fixture.")
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("var/tmp"))
    parser.add_argument("--stem", default="grouping-validation")
    args = parser.parse_args()

    report = validate_grouping(args.fixture)
    paths = write_report(report, args.output_dir, stem=args.stem)
    print(json.dumps(paths, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
