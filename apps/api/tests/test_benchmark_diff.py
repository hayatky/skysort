from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "benchmark_diff.py"
_SPEC = importlib.util.spec_from_file_location("benchmark_diff", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
benchmark_diff = importlib.util.module_from_spec(_SPEC)
sys.modules["benchmark_diff"] = benchmark_diff
_SPEC.loader.exec_module(benchmark_diff)

compare_expectations = benchmark_diff.compare_expectations
write_reports = benchmark_diff.write_reports


def test_benchmark_diff_reports_best_reject_and_pick_mismatches(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    expectations = tmp_path / "expectations.json"
    results = tmp_path / "results.json"
    expectations.write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "groups": [
                    {
                        "name": "burst-a",
                        "match": {"group_id": "group_a"},
                        "expected_best": "a/002.jpg",
                        "expected_reject": ["a/001.jpg"],
                        "expected_pick": ["a/002.jpg"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    results.write_text(
        json.dumps(
            [
                {
                    "photo_id": "photo_1",
                    "group_id": "group_a",
                    "file_path": str(root / "a/001.jpg"),
                    "rating": 4,
                    "selection_status": "normal",
                    "pick_flag": True,
                    "best_cut_flag": True,
                },
                {
                    "photo_id": "photo_2",
                    "group_id": "group_a",
                    "file_path": str(root / "a/002.jpg"),
                    "rating": 3,
                    "selection_status": "normal",
                    "pick_flag": False,
                    "best_cut_flag": False,
                },
            ]
        ),
        encoding="utf-8",
    )

    report = compare_expectations(expectations, results, root=root)

    assert report["mismatch_count"] == 1
    comparison = report["comparisons"][0]
    assert comparison["issues"] == ["best_mismatch", "reject_mismatch", "pick_mismatch"]
    assert comparison["actual_best"] == ["a/001.jpg"]
    assert comparison["missing_reject"] == ["a/001.jpg"]
    assert comparison["unexpected_pick"] == ["a/001.jpg"]


def test_benchmark_diff_writes_json_csv_and_markdown(tmp_path: Path) -> None:
    report = {
        "schema_version": "v1",
        "generated_at": "2026-05-27T00:00:00+00:00",
        "expected_group_count": 1,
        "matched_group_count": 1,
        "mismatch_count": 0,
        "comparisons": [
            {
                "name": "burst-a",
                "status": "matched",
                "issues": [],
                "expected_best": "a/001.jpg",
                "actual_best": ["a/001.jpg"],
                "missing_reject": [],
                "unexpected_reject": [],
                "missing_pick": [],
                "unexpected_pick": [],
                "matched_photo_count": 1,
            }
        ],
    }

    paths = write_reports(report, tmp_path, stem="sample")

    assert Path(paths["json"]).exists()
    assert Path(paths["csv"]).exists()
    assert Path(paths["markdown"]).read_text(encoding="utf-8").startswith("# SkySort Benchmark Diff")
