from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "human_review_packet.py"
_SPEC = importlib.util.spec_from_file_location("human_review_packet", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
human_review_packet = importlib.util.module_from_spec(_SPEC)
sys.modules["human_review_packet"] = human_review_packet
_SPEC.loader.exec_module(human_review_packet)

build_review_packet = human_review_packet.build_review_packet
apply_review_packet = human_review_packet.apply_review_packet
validate_review_packet = human_review_packet.validate_review_packet
write_packet = human_review_packet.write_packet


def test_human_review_packet_summarizes_remaining_acceptance_evidence(tmp_path: Path) -> None:
    expectations = tmp_path / "expectations.json"
    benchmark = tmp_path / "benchmark.json"
    acceptance = tmp_path / "acceptance.json"
    diagnostics = tmp_path / "diagnostics.json"
    montage_dir = tmp_path / "montages"
    montage_dir.mkdir()
    (montage_dir / "burst-a.jpg").write_bytes(b"stub")
    expectations.write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "human_verified": False,
                "groups": [
                    {
                        "name": "burst-a",
                        "match": {"group_id": "group_a", "relative_paths": ["a/001.jpg", "a/002.jpg"]},
                        "expected_best": "a/002.jpg",
                        "expected_reject": ["a/001.jpg"],
                        "expected_pick": ["a/002.jpg"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    benchmark.write_text(
        json.dumps(
            {
                "human_verified": False,
                "expected_group_count": 1,
                "mismatch_count": 1,
                "metrics": {"group_overmerged_count": 1},
                "comparisons": [
                    {
                        "name": "burst-a",
                        "issues": ["group_overmerged"],
                        "actual_group_ids": ["group_a"],
                        "extra_group_photos": ["a/999.jpg"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    acceptance.write_text(
        json.dumps(
            {
                "summary": {"pass": 3, "needs_review": 2},
                "checks": [{"name": "ai_timeout_rate", "status": "fail"}],
            }
        ),
        encoding="utf-8",
    )
    diagnostics.write_text(json.dumps({"ai_evaluation": {"response_count": 20, "timeout_count": 2}}), encoding="utf-8")

    packet = build_review_packet(expectations, benchmark, acceptance, review_montage_dir=montage_dir, diagnostics_path=diagnostics)
    paths = write_packet(packet, tmp_path, stem="packet")

    assert packet["human_verified"] is False
    assert packet["summary"]["timeout_rate"] == 0.1
    assert packet["summary"]["acceptance_checks"]["ai_timeout_rate"] == "fail"
    assert any("timeout probe" in item for item in packet["required_human_actions"])
    assert packet["groups"][0]["extra_group_photos"] == ["a/999.jpg"]
    assert packet["groups"][0]["review_montage"] == str(montage_dir / "burst-a.jpg")
    assert packet["groups"][0]["human_overmerge_ok"] is None
    assert Path(paths["json"]).exists()
    assert Path(paths["html"]).exists()
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "SkySort Human Review Packet" in markdown
    assert str(montage_dir / "burst-a.jpg") in markdown
    html = Path(paths["html"]).read_text(encoding="utf-8")
    assert "Download reviewed packet JSON" in html
    assert "human_overmerge_ok" in html


def test_human_review_packet_omits_timeout_action_when_gate_passes(tmp_path: Path) -> None:
    expectations = tmp_path / "expectations.json"
    benchmark = tmp_path / "benchmark.json"
    acceptance = tmp_path / "acceptance.json"
    expectations.write_text(json.dumps({"schema_version": "v1", "groups": []}), encoding="utf-8")
    benchmark.write_text(json.dumps({"comparisons": [], "metrics": {}}), encoding="utf-8")
    acceptance.write_text(
        json.dumps({"summary": {"pass": 4}, "checks": [{"name": "ai_timeout_rate", "status": "pass"}]}),
        encoding="utf-8",
    )

    packet = build_review_packet(expectations, benchmark, acceptance)

    assert packet["summary"]["acceptance_checks"]["ai_timeout_rate"] == "pass"
    assert not any("timeout probe" in item for item in packet["required_human_actions"])


def test_human_review_packet_validation_and_promotion(tmp_path: Path) -> None:
    expectations = tmp_path / "expectations.json"
    expectations.write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "human_verified": False,
                "groups": [{"name": "burst-a"}],
            }
        ),
        encoding="utf-8",
    )
    packet = {
        "schema_version": "v1",
        "groups": [
            {
                "name": "burst-a",
                "human_overmerge_ok": True,
                "human_subjective_ok": True,
            }
        ],
    }
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    output = tmp_path / "verified.json"

    validation = validate_review_packet(packet)
    result = apply_review_packet(packet_path, expectations, output)
    promoted = json.loads(output.read_text(encoding="utf-8"))

    assert validation["ready"] is True
    assert result["validation"]["ready"] is True
    assert promoted["human_verified"] is True
    assert promoted["human_review_packet"] == str(packet_path)


def test_human_review_packet_promotion_requires_all_review_flags(tmp_path: Path) -> None:
    expectations = tmp_path / "expectations.json"
    expectations.write_text(json.dumps({"schema_version": "v1", "groups": []}), encoding="utf-8")
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(
        json.dumps({"schema_version": "v1", "groups": [{"name": "burst-a", "human_overmerge_ok": True, "human_subjective_ok": None}]}),
        encoding="utf-8",
    )

    try:
        apply_review_packet(packet_path, expectations, tmp_path / "verified.json")
    except ValueError as exc:
        assert "missing human_subjective_ok" in str(exc)
    else:
        raise AssertionError("expected packet promotion to fail")
