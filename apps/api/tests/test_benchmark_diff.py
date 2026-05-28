from __future__ import annotations

import json
import importlib.util
import sqlite3
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

_SEED_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "benchmark_seed.py"
_SEED_SPEC = importlib.util.spec_from_file_location("benchmark_seed", _SEED_SCRIPT_PATH)
assert _SEED_SPEC and _SEED_SPEC.loader
benchmark_seed = importlib.util.module_from_spec(_SEED_SPEC)
sys.modules["benchmark_seed"] = benchmark_seed
_SEED_SPEC.loader.exec_module(benchmark_seed)

build_expectation_draft = benchmark_seed.build_expectation_draft
strip_review_items = benchmark_seed.strip_review_items
write_review_html = benchmark_seed.write_review_html


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
                    "evaluation_status": "final",
                    "pick_flag": True,
                    "best_cut_flag": True,
                    "reviewed_flag": True,
                    "user_override_flag": True,
                },
                {
                    "photo_id": "photo_2",
                    "group_id": "group_a",
                    "file_path": str(root / "a/002.jpg"),
                    "rating": 3,
                    "selection_status": "normal",
                    "evaluation_status": "ai_eval_failed",
                    "pick_flag": False,
                    "best_cut_flag": False,
                    "reviewed_flag": False,
                    "user_override_flag": False,
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
    assert report["metrics"]["best_match_rate"] == 0.0
    assert report["metrics"]["reject_recall"] == 0.0
    assert report["metrics"]["missing_pick_count"] == 1
    assert report["metrics"]["unexpected_pick_count"] == 1
    assert report["metrics"]["ai_failed_count"] == 1
    assert report["metrics"]["review_operation_count"] == 2


def test_benchmark_diff_reports_group_quality_metrics(tmp_path: Path) -> None:
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
                        "name": "fragmented-and-merged",
                        "match": {"relative_paths": ["a/001.jpg", "a/002.jpg"]},
                        "expected_best": "a/001.jpg",
                        "expected_reject": [],
                        "expected_pick": ["a/001.jpg", "a/002.jpg"],
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
                    "rating": 5,
                    "selection_status": "normal",
                    "evaluation_status": "final",
                    "pick_flag": True,
                    "best_cut_flag": True,
                },
                {
                    "photo_id": "photo_2",
                    "group_id": "group_b",
                    "file_path": str(root / "a/002.jpg"),
                    "rating": 4,
                    "selection_status": "normal",
                    "evaluation_status": "final",
                    "pick_flag": True,
                    "best_cut_flag": False,
                },
                {
                    "photo_id": "photo_3",
                    "group_id": "group_b",
                    "file_path": str(root / "a/999.jpg"),
                    "rating": 3,
                    "selection_status": "normal",
                    "evaluation_status": "final",
                    "pick_flag": False,
                    "best_cut_flag": False,
                },
            ]
        ),
        encoding="utf-8",
    )

    report = compare_expectations(expectations, results, root=root)

    comparison = report["comparisons"][0]
    assert "group_overfragmented" in comparison["issues"]
    assert "group_overmerged" in comparison["issues"]
    assert comparison["actual_group_ids"] == ["group_a", "group_b"]
    assert comparison["extra_group_photos"] == ["a/999.jpg"]
    assert report["metrics"]["group_overfragmented_count"] == 1
    assert report["metrics"]["group_overmerged_count"] == 1


def test_benchmark_diff_writes_json_csv_and_markdown(tmp_path: Path) -> None:
    report = {
        "schema_version": "v1",
        "generated_at": "2026-05-27T00:00:00+00:00",
        "expected_group_count": 1,
        "matched_group_count": 1,
        "mismatch_count": 0,
        "metrics": {
            "best_match_rate": 1.0,
            "reject_recall": 1.0,
            "missing_pick_count": 0,
            "unexpected_pick_count": 0,
            "group_overfragmented_count": 0,
            "group_overmerged_count": 0,
            "ai_failure_rate": 0.0,
            "review_operation_count": 1,
        },
        "comparisons": [
            {
                "name": "burst-a",
                "status": "matched",
                "issues": [],
                "expected_best": "a/001.jpg",
                "actual_best": ["a/001.jpg"],
                "expected_reject": [],
                "missing_reject": [],
                "unexpected_reject": [],
                "expected_pick": ["a/001.jpg"],
                "missing_pick": [],
                "unexpected_pick": [],
                "matched_photo_count": 1,
                "expected_photo_count": 1,
                "actual_group_ids": ["group_a"],
                "extra_group_photos": [],
            }
        ],
    }

    paths = write_reports(report, tmp_path, stem="sample")

    assert Path(paths["json"]).exists()
    assert Path(paths["csv"]).exists()
    assert Path(paths["markdown"]).read_text(encoding="utf-8").startswith("# SkySort Benchmark Diff")


def test_benchmark_seed_generates_editable_expectation_draft(tmp_path: Path) -> None:
    db_path = tmp_path / "skysort.db"
    root = tmp_path / "photos"
    root.mkdir()
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            create table jobs (id text primary key, root_path text, updated_at text);
            create table groups (
              id text primary key,
              job_id text,
              group_size integer,
              merge_suggested integer,
              stale_flag integer,
              created_at text
            );
            create table group_members (group_id text, photo_id text, sort_order integer);
            create table photos (id text primary key, file_path text, thumb_path text, preview_path text);
            create table photo_evaluations (
              photo_id text,
              job_id text,
              rating integer,
              selection_status text,
              evaluation_status text,
              pick_flag integer,
              best_cut_flag integer,
              is_current integer
            );
            """
        )
        connection.execute("insert into jobs values ('job_seed', ?, '2026-05-27T00:00:00+00:00')", (str(root),))
        connection.execute("insert into groups values ('group_seed', 'job_seed', 2, 0, 0, '2026-05-27T00:00:00+00:00')")
        for index, name in enumerate(["001.jpg", "002.jpg"]):
            photo_id = f"photo_{index + 1}"
            thumb = tmp_path / f"{name}.thumb.jpg"
            thumb.write_bytes(b"thumb")
            connection.execute("insert into photos values (?, ?, ?, ?)", (photo_id, str(root / name), str(thumb), None))
            connection.execute("insert into group_members values ('group_seed', ?, ?)", (photo_id, index))
        connection.execute("insert into photo_evaluations values ('photo_1', 'job_seed', 1, 'rejected', 'final', 0, 0, 1)")
        connection.execute("insert into photo_evaluations values ('photo_2', 'job_seed', 5, 'normal', 'final', 1, 1, 1)")

    draft = build_expectation_draft(db_path, limit=10)

    assert draft["schema_version"] == "v1"
    assert draft["source"]["job_id"] == "job_seed"
    assert draft["groups"][0]["match"]["relative_paths"] == ["001.jpg", "002.jpg"]
    assert draft["groups"][0]["expected_best"] == "002.jpg"
    assert draft["groups"][0]["expected_reject"] == ["001.jpg"]
    assert draft["groups"][0]["expected_pick"] == ["002.jpg"]
    assert draft["groups"][0]["review_items"][0]["thumb_path"]

    html_path = tmp_path / "draft.html"
    write_review_html(draft, html_path)

    markup = html_path.read_text(encoding="utf-8")
    assert "SkySort Benchmark Draft" in markup
    assert "001.jpg" in markup
    assert "002.jpg" in markup
    assert "class=\"photo reject\"" in markup


def test_benchmark_seed_can_use_rescored_technical_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "skysort.db"
    root = tmp_path / "photos"
    root.mkdir()
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            create table jobs (id text primary key, root_path text, updated_at text);
            create table groups (
              id text primary key,
              job_id text,
              group_size integer,
              merge_suggested integer,
              stale_flag integer,
              created_at text
            );
            create table group_members (group_id text, photo_id text, sort_order integer);
            create table photos (id text primary key, file_path text, thumb_path text, preview_path text);
            create table photo_evaluations (
              photo_id text,
              job_id text,
              rating integer,
              selection_status text,
              evaluation_status text,
              pick_flag integer,
              best_cut_flag integer,
              is_current integer
            );
            """
        )
        connection.execute("insert into jobs values ('job_seed', ?, '2026-05-27T00:00:00+00:00')", (str(root),))
        connection.execute("insert into groups values ('group_seed', 'job_seed', 3, 0, 0, '2026-05-27T00:00:00+00:00')")
        for index, name in enumerate(["001.jpg", "002.jpg", "003.jpg"]):
            photo_id = f"photo_{index + 1}"
            connection.execute("insert into photos values (?, ?, null, null)", (photo_id, str(root / name)))
            connection.execute("insert into group_members values ('group_seed', ?, ?)", (photo_id, index))
            connection.execute("insert into photo_evaluations values (?, 'job_seed', 1, 'normal', 'final', 0, 0, 1)", (photo_id,))
    score_fixture = tmp_path / "fixture.json"
    score_fixture.write_text(
        json.dumps(
            {
                "technical_scores": [
                    {"photo_id": "photo_1", "candidate_quality_score": 35, "reject_risk_score": 20},
                    {"photo_id": "photo_2", "candidate_quality_score": 88, "reject_risk_score": 10},
                    {"photo_id": "photo_3", "candidate_quality_score": 78, "reject_risk_score": 10},
                ]
            }
        ),
        encoding="utf-8",
    )

    draft = build_expectation_draft(db_path, limit=10, score_fixture_path=score_fixture)
    stripped = strip_review_items(draft)

    assert draft["groups"][0]["expected_best"] == "002.jpg"
    assert draft["groups"][0]["expected_reject"] == ["001.jpg"]
    assert draft["groups"][0]["expected_pick"] == ["002.jpg", "003.jpg"]
    assert "review_items" not in stripped["groups"][0]
    assert "root" not in stripped["source"]
    assert "db_path" not in stripped["source"]
