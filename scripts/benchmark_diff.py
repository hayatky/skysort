from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PhotoResult:
    photo_id: str
    group_id: str | None
    file_path: str
    relative_path: str
    rating: int | None
    selection_status: str
    evaluation_status: str
    pick_flag: bool
    best_cut_flag: bool
    reviewed_flag: bool
    user_override_flag: bool


def load_results(path: Path, root: Path | None) -> list[PhotoResult]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("results export must be a JSON array")
    return [_photo_result(item, root) for item in payload if isinstance(item, dict)]


def compare_expectations(expectations_path: Path, results_path: Path, *, root: Path | None = None) -> dict[str, Any]:
    expectations = json.loads(expectations_path.read_text(encoding="utf-8"))
    if expectations.get("schema_version") != "v1":
        raise ValueError("benchmark expectations schema_version must be v1")

    results = load_results(results_path, root)
    by_relative_path = {item.relative_path: item for item in results}
    groups = expectations.get("groups", [])
    if not isinstance(groups, list):
        raise ValueError("benchmark expectations groups must be an array")

    comparisons = [_compare_group(group, results, by_relative_path) for group in groups if isinstance(group, dict)]
    mismatches = [item for item in comparisons if item["status"] != "matched"]
    metrics = _benchmark_metrics(comparisons, results)
    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "human_verified": bool(expectations.get("human_verified")),
        "expected_group_count": len(groups),
        "matched_group_count": len(comparisons) - len(mismatches),
        "mismatch_count": len(mismatches),
        "metrics": metrics,
        "comparisons": comparisons,
    }


def write_reports(report: dict[str, Any], output_dir: Path, stem: str = "benchmark-diff") -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(report, csv_path)
    _write_markdown(report, md_path)
    return {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}


def _photo_result(item: dict[str, Any], root: Path | None) -> PhotoResult:
    file_path = str(item.get("file_path") or "")
    relative_path = str(item.get("relative_path") or _relative_path(file_path, root))
    return PhotoResult(
        photo_id=str(item.get("photo_id") or item.get("id") or ""),
        group_id=str(item["group_id"]) if item.get("group_id") is not None else None,
        file_path=file_path,
        relative_path=relative_path,
        rating=int(item["rating"]) if item.get("rating") is not None else None,
        selection_status=str(item.get("selection_status") or "normal"),
        evaluation_status=str(item.get("evaluation_status") or "provisional"),
        pick_flag=bool(item.get("pick_flag")),
        best_cut_flag=bool(item.get("best_cut_flag")),
        reviewed_flag=bool(item.get("reviewed_flag")),
        user_override_flag=bool(item.get("user_override_flag")),
    )


def _compare_group(group: dict[str, Any], results: list[PhotoResult], by_relative_path: dict[str, PhotoResult]) -> dict[str, Any]:
    name = str(group.get("name") or group.get("match", {}).get("group_id") or "unnamed")
    matched = _match_group(group.get("match", {}), results, by_relative_path)
    expected_best = group.get("expected_best")
    expected_reject = set(_string_list(group.get("expected_reject")))
    expected_pick = set(_string_list(group.get("expected_pick")))
    expected_paths = set(_string_list(group.get("match", {}).get("relative_paths") if isinstance(group.get("match"), dict) else []))

    actual_best = sorted(item.relative_path for item in matched if item.best_cut_flag)
    actual_reject = sorted(item.relative_path for item in matched if item.selection_status == "rejected")
    actual_pick = sorted(item.relative_path for item in matched if item.pick_flag)
    grouping = _group_quality(expected_paths, results, by_relative_path)

    issues: list[str] = []
    if expected_best and expected_best not in actual_best:
        issues.append("best_mismatch")
    missing_reject = sorted(expected_reject.difference(actual_reject))
    unexpected_reject = sorted(set(actual_reject).difference(expected_reject))
    missing_pick = sorted(expected_pick.difference(actual_pick))
    unexpected_pick = sorted(set(actual_pick).difference(expected_pick))
    if missing_reject or unexpected_reject:
        issues.append("reject_mismatch")
    if missing_pick or unexpected_pick:
        issues.append("pick_mismatch")
    if grouping["overfragmented"]:
        issues.append("group_overfragmented")
    if grouping["overmerged"]:
        issues.append("group_overmerged")
    if not matched:
        issues.append("group_not_found")

    return {
        "name": name,
        "status": "matched" if not issues else "mismatch",
        "issues": issues,
        "expected_best": expected_best,
        "expected_reject": sorted(expected_reject),
        "expected_pick": sorted(expected_pick),
        "actual_best": actual_best,
        "missing_reject": missing_reject,
        "unexpected_reject": unexpected_reject,
        "missing_pick": missing_pick,
        "unexpected_pick": unexpected_pick,
        "matched_photo_count": len(matched),
        "expected_photo_count": len(expected_paths),
        "actual_group_ids": grouping["actual_group_ids"],
        "extra_group_photos": grouping["extra_group_photos"],
    }


def _match_group(match: Any, results: list[PhotoResult], by_relative_path: dict[str, PhotoResult]) -> list[PhotoResult]:
    if not isinstance(match, dict):
        return []
    group_id = match.get("group_id")
    if group_id:
        return [item for item in results if item.group_id == group_id]
    relative_paths = _string_list(match.get("relative_paths"))
    if relative_paths:
        return [by_relative_path[path] for path in relative_paths if path in by_relative_path]
    return []


def _group_quality(expected_paths: set[str], results: list[PhotoResult], by_relative_path: dict[str, PhotoResult]) -> dict[str, Any]:
    if not expected_paths:
        return {"actual_group_ids": [], "extra_group_photos": [], "overfragmented": False, "overmerged": False}
    expected_results = [by_relative_path[path] for path in expected_paths if path in by_relative_path]
    actual_group_ids = sorted({item.group_id for item in expected_results if item.group_id})
    extra_group_photos = sorted(
        {
            item.relative_path
            for item in results
            if item.group_id in actual_group_ids and item.relative_path not in expected_paths
        }
    )
    return {
        "actual_group_ids": actual_group_ids,
        "extra_group_photos": extra_group_photos,
        "overfragmented": len(actual_group_ids) > 1,
        "overmerged": bool(extra_group_photos),
    }


def _benchmark_metrics(comparisons: list[dict[str, Any]], results: list[PhotoResult]) -> dict[str, Any]:
    expected_best_count = len([item for item in comparisons if item.get("expected_best")])
    best_match_count = len(
        [
            item
            for item in comparisons
            if item.get("expected_best") and item.get("expected_best") in set(item.get("actual_best", []))
        ]
    )
    expected_reject_count = sum(len(_string_list(item.get("expected_reject"))) for item in comparisons)
    missing_reject_count = sum(len(_string_list(item.get("missing_reject"))) for item in comparisons)
    expected_pick_count = sum(len(_string_list(item.get("expected_pick"))) for item in comparisons)
    missing_pick_count = sum(len(_string_list(item.get("missing_pick"))) for item in comparisons)
    unexpected_pick_count = sum(len(_string_list(item.get("unexpected_pick"))) for item in comparisons)
    matched_photo_count = sum(int(item.get("matched_photo_count") or 0) for item in comparisons)
    ai_failed_count = len([item for item in results if item.evaluation_status == "ai_eval_failed"])
    reviewed_count = len([item for item in results if item.reviewed_flag])
    user_override_count = len([item for item in results if item.user_override_flag])
    return {
        "best_match_count": best_match_count,
        "expected_best_count": expected_best_count,
        "best_match_rate": _ratio(best_match_count, expected_best_count),
        "reject_recall_count": expected_reject_count - missing_reject_count,
        "expected_reject_count": expected_reject_count,
        "reject_recall": _ratio(expected_reject_count - missing_reject_count, expected_reject_count),
        "expected_pick_count": expected_pick_count,
        "missing_pick_count": missing_pick_count,
        "unexpected_pick_count": unexpected_pick_count,
        "group_overfragmented_count": len([item for item in comparisons if "group_overfragmented" in item.get("issues", [])]),
        "group_overmerged_count": len([item for item in comparisons if "group_overmerged" in item.get("issues", [])]),
        "ai_failed_count": ai_failed_count,
        "matched_photo_count": matched_photo_count,
        "ai_failure_rate": _ratio(ai_failed_count, len(results)),
        "reviewed_count": reviewed_count,
        "user_override_count": user_override_count,
        "review_operation_count": reviewed_count + user_override_count,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def _relative_path(file_path: str, root: Path | None) -> str:
    if not root or not file_path:
        return file_path
    try:
        return Path(file_path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return file_path


def _write_csv(report: dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "name",
                "status",
                "issues",
                "expected_best",
                "actual_best",
                "expected_reject",
                "missing_reject",
                "unexpected_reject",
                "expected_pick",
                "missing_pick",
                "unexpected_pick",
                "matched_photo_count",
                "expected_photo_count",
                "actual_group_ids",
                "extra_group_photos",
            ],
        )
        writer.writeheader()
        for item in report["comparisons"]:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value for key, value in item.items()})


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# SkySort Benchmark Diff",
        "",
        f"- expected_group_count: {report['expected_group_count']}",
        f"- matched_group_count: {report['matched_group_count']}",
        f"- mismatch_count: {report['mismatch_count']}",
        "",
        "## Metrics",
        "",
    ]
    metrics = report.get("metrics", {})
    for key in [
        "best_match_rate",
        "reject_recall",
        "missing_pick_count",
        "unexpected_pick_count",
        "group_overfragmented_count",
        "group_overmerged_count",
        "ai_failure_rate",
        "review_operation_count",
    ]:
        lines.append(f"- {key}: {metrics.get(key)}")
    lines.extend(
        [
            "",
            "## Groups",
            "",
            "| group | status | issues | expected_best | actual_best | group_ids | extra_group_photos |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for item in report["comparisons"]:
        lines.append(
            f"| {item['name']} | {item['status']} | {', '.join(item['issues']) or '-'} | {item.get('expected_best') or '-'} | {', '.join(item['actual_best']) or '-'} | {', '.join(item.get('actual_group_ids', [])) or '-'} | {', '.join(item.get('extra_group_photos', [])) or '-'} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare SkySort benchmark expectations with exported JSON results.")
    parser.add_argument("--expectations", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("var/tmp"))
    parser.add_argument("--stem", default="benchmark-diff")
    args = parser.parse_args()

    report = compare_expectations(args.expectations, args.results, root=args.root)
    paths = write_reports(report, args.output_dir, stem=args.stem)
    print(json.dumps(paths, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
