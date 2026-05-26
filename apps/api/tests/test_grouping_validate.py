from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "grouping_validate.py"
_SPEC = importlib.util.spec_from_file_location("grouping_validate", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
grouping_validate = importlib.util.module_from_spec(_SPEC)
sys.modules["grouping_validate"] = grouping_validate
_SPEC.loader.exec_module(grouping_validate)

validate_grouping = grouping_validate.validate_grouping
write_report = grouping_validate.write_report


def test_grouping_validate_compares_settings_metrics(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "photos": [
                    {"photo_id": "a", "capture_timestamp_ms": 1000, "capture_order_index": 0, "similarity_seed": 0.10},
                    {"photo_id": "b", "capture_timestamp_ms": 2000, "capture_order_index": 1, "similarity_seed": 0.11},
                    {"photo_id": "c", "capture_timestamp_ms": 9000, "capture_order_index": 2, "similarity_seed": 0.12},
                ],
                "scenarios": [
                    {"name": "loose", "time_proximity_seconds": 10, "similarity_threshold": 0.80},
                    {"name": "strict-time", "time_proximity_seconds": 2, "similarity_threshold": 0.80},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = validate_grouping(fixture)

    assert report["photo_count"] == 3
    assert report["scenarios"][0]["group_count"] == 1
    assert report["scenarios"][0]["average_group_size"] == 3
    assert report["scenarios"][1]["group_count"] == 2
    assert report["scenarios"][1]["single_group_count"] == 1


def test_grouping_validate_writes_reports(tmp_path: Path) -> None:
    report = {
        "schema_version": "v1",
        "generated_at": "2026-05-27T00:00:00+00:00",
        "photo_count": 2,
        "scenarios": [
            {
                "name": "default",
                "time_proximity_seconds": 4,
                "similarity_threshold": 0.86,
                "group_count": 1,
                "single_group_count": 0,
                "average_group_size": 2,
                "groups": [["a", "b"]],
            }
        ],
    }

    paths = write_report(report, tmp_path, stem="grouping")

    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).read_text(encoding="utf-8").startswith("# SkySort Grouping Validation")
