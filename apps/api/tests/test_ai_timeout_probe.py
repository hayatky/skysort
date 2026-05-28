from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "ai_timeout_probe.py"
_SPEC = importlib.util.spec_from_file_location("ai_timeout_probe", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
ai_timeout_probe = importlib.util.module_from_spec(_SPEC)
sys.modules["ai_timeout_probe"] = ai_timeout_probe
_SPEC.loader.exec_module(ai_timeout_probe)

build_timeout_probe_report = ai_timeout_probe.build_timeout_probe_report
_is_localhost_url = ai_timeout_probe._is_localhost_url
write_reports = ai_timeout_probe.write_reports


def test_ai_timeout_probe_builds_dry_run_report_from_stored_payloads(tmp_path: Path) -> None:
    db_path = tmp_path / "skysort.db"
    photo_path = tmp_path / "preview.jpg"
    photo_path.write_bytes(b"jpeg")
    diagnostics = tmp_path / "diagnostics.json"
    diagnostics.write_text(json.dumps({"ai_evaluation": {"response_count": 20, "timeout_count": 3}}), encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            create table jobs (id text primary key, finished_at text, updated_at text, started_at text);
            create table photos (id text primary key, job_id text, preview_path text, file_path text);
            create table ai_responses (
              id text primary key,
              job_id text,
              phase text,
              response_status text,
              request_payload text,
              target_photo_ids_json text,
              latency_ms integer,
              requested_at text
            );
            """
        )
        connection.execute("insert into jobs values ('job_probe', null, '2026-05-27T00:00:00+00:00', null)")
        connection.execute("insert into photos values ('photo_1', 'job_probe', ?, ?)", (str(photo_path), str(photo_path)))
        connection.execute(
            "insert into ai_responses values ('ai_1', 'job_probe', 'single', 'ai_eval_failed', ?, ?, 12000, '2026-05-27T00:00:00+00:00')",
            (
                json.dumps({"messages": [{"role": "user", "content": [{"type": "image_url", "image_ref": "preview_jpeg"}]}]}),
                json.dumps(["photo_1"]),
            ),
        )

    report = build_timeout_probe_report(db_path, diagnostics_path=diagnostics, execute=False, timeout_seconds=120.0)
    paths = write_reports(report, tmp_path, stem="probe")

    assert report["summary"]["sample_count"] == 1
    assert report["summary"]["replayable_count"] == 1
    assert report["summary"]["json_schema_failure_rate"] is None
    assert report["baseline"]["timeout_rate"] == 0.15
    assert report["payload_mode"] == "stored"
    assert report["timeout_seconds_override"] == 120.0
    assert report["cases"][0]["replayable"] is True
    assert Path(paths["json"]).exists()
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "SkySort AI Timeout Probe" in markdown
    assert "payload_mode: stored" in markdown
    assert "timeout_seconds_override: 120.0" in markdown
    assert "json_schema_failure_rate: None" in markdown


def test_ai_timeout_probe_localhost_guard() -> None:
    assert _is_localhost_url("http://127.0.0.1:1234/v1") is True
    assert _is_localhost_url("http://localhost:1234/v1") is True
    assert _is_localhost_url("https://example.test/v1") is False
