from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "acceptance_gate.py"
_SPEC = importlib.util.spec_from_file_location("acceptance_gate", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
acceptance_gate = importlib.util.module_from_spec(_SPEC)
sys.modules["acceptance_gate"] = acceptance_gate
_SPEC.loader.exec_module(acceptance_gate)

evaluate_acceptance = acceptance_gate.evaluate_acceptance
write_reports = acceptance_gate.write_reports


def test_acceptance_gate_reports_pass_fail_and_manual_statuses(tmp_path: Path) -> None:
    diagnostics = tmp_path / "diagnostics.json"
    diagnostics.write_text(
        json.dumps(
            {
                "current_grouping": {"single_group_count": 100, "small_group_count_2_to_4": 80},
                "scenarios": [
                    {
                        "name": "current",
                        "single_group_count": 40,
                        "small_group_count_2_to_4": 30,
                        "internal_gap_risk": {"groups_with_internal_gap_over_8s": 0},
                    }
                ],
                "rating_distribution": {"star1_or_reject_rate": 0.95, "rating_counts": {"1": 95}, "selection_status_counts": {"normal": 95}},
                "ai_evaluation": {"response_count": 100, "json_parse_failure_count": 25, "timeout_count": 10},
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_acceptance(diagnostics)
    statuses = {item["name"]: item["status"] for item in report["checks"]}

    assert statuses["grouping_reduction"] == "pass"
    assert statuses["overmerge_safety"] == "needs_review"
    assert statuses["rating_distribution"] == "fail"
    assert statuses["json_schema_failure_rate"] == "fail"
    assert statuses["ai_timeout_rate"] == "fail"


def test_acceptance_gate_uses_baseline_and_benchmark_diff_for_acceptance(tmp_path: Path) -> None:
    diagnostics = tmp_path / "diagnostics.json"
    baseline = tmp_path / "baseline.json"
    benchmark = tmp_path / "benchmark.json"
    diagnostics.write_text(
        json.dumps(
            {
                "current_grouping": {"single_group_count": 100, "small_group_count_2_to_4": 80},
                "scenarios": [{"name": "current", "single_group_count": 40, "small_group_count_2_to_4": 30}],
                "rating_distribution": {"star1_or_reject_rate": 0.2},
                "ai_evaluation": {"response_count": 100, "json_parse_failure_count": 1, "timeout_count": 0},
            }
        ),
        encoding="utf-8",
    )
    baseline.write_text(
        json.dumps(
            {
                "rating_distribution": {"star1_or_reject_rate": 0.95},
                "ai_evaluation": {"response_count": 100, "json_parse_failure_count": 25, "timeout_count": 10},
            }
        ),
        encoding="utf-8",
    )
    benchmark.write_text(
        json.dumps(
            {
                "human_verified": True,
                "expected_group_count": 12,
                "mismatch_count": 0,
                "metrics": {"group_overmerged_count": 0, "best_match_rate": 1.0},
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_acceptance(diagnostics, baseline_diagnostics_path=baseline, benchmark_diff_path=benchmark)
    statuses = {item["name"]: item["status"] for item in report["checks"]}
    paths = write_reports(report, tmp_path, stem="gate")

    assert statuses["rating_distribution"] == "pass"
    assert statuses["json_schema_failure_rate"] == "pass"
    assert statuses["ai_timeout_rate"] == "pass"
    assert statuses["overmerge_safety"] == "pass"
    assert statuses["benchmark_expectations"] == "pass"
    assert statuses["subjective_benchmark"] == "pass"
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).read_text(encoding="utf-8").startswith("# SkySort Acceptance Gate")


def test_acceptance_gate_prefers_simulated_current_code_rating_distribution(tmp_path: Path) -> None:
    diagnostics = tmp_path / "diagnostics.json"
    diagnostics.write_text(
        json.dumps(
            {
                "current_grouping": {"single_group_count": 100, "small_group_count_2_to_4": 80},
                "scenarios": [{"name": "current", "single_group_count": 40, "small_group_count_2_to_4": 30}],
                "rating_distribution": {"star1_or_reject_rate": 0.99},
                "simulated_rating_distribution": {
                    "source": "current_scoring_from_rescored_current_code",
                    "star1_or_reject_rate": 0.14,
                    "rating_counts": {"1": 14, "3": 50, "4": 36},
                    "selection_status_counts": {"normal": 100},
                },
                "ai_evaluation": {"response_count": 100, "json_parse_failure_count": 25, "timeout_count": 10},
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_acceptance(diagnostics)
    rating = next(item for item in report["checks"] if item["name"] == "rating_distribution")

    assert rating["status"] == "pass"
    assert rating["evidence"]["rating_source"] == "current_scoring_from_rescored_current_code"
    assert rating["evidence"]["persisted_star1_or_reject_rate"] == 0.99


def test_acceptance_gate_uses_replay_adjusted_json_schema_failure_count(tmp_path: Path) -> None:
    diagnostics = tmp_path / "diagnostics.json"
    diagnostics.write_text(
        json.dumps(
            {
                "current_grouping": {"single_group_count": 100, "small_group_count_2_to_4": 80},
                "scenarios": [{"name": "current", "single_group_count": 40, "small_group_count_2_to_4": 30}],
                "rating_distribution": {"star1_or_reject_rate": 0.2},
                "ai_evaluation": {
                    "response_count": 100,
                    "json_parse_failure_count": 25,
                    "projected_json_schema_failure_count_after_replay": 5,
                    "timeout_count": 10,
                },
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_acceptance(diagnostics)
    json_check = next(item for item in report["checks"] if item["name"] == "json_schema_failure_rate")

    assert json_check["status"] == "pass"
    assert json_check["evidence"]["json_parse_failure_count"] == 5
    assert json_check["evidence"]["original_json_parse_failure_count"] == 25


def test_acceptance_gate_uses_executed_current_payload_probe_for_json_schema_failures(tmp_path: Path) -> None:
    diagnostics = tmp_path / "diagnostics.json"
    timeout_probe = tmp_path / "timeout.json"
    diagnostics.write_text(
        json.dumps(
            {
                "current_grouping": {"single_group_count": 100, "small_group_count_2_to_4": 80},
                "scenarios": [{"name": "current", "single_group_count": 40, "small_group_count_2_to_4": 30}],
                "rating_distribution": {"star1_or_reject_rate": 0.2},
                "ai_evaluation": {
                    "response_count": 100,
                    "json_parse_failure_count": 25,
                    "projected_json_schema_failure_count_after_replay": 15,
                    "timeout_count": 10,
                    "failed_response_replay": {"schema_valid_count": 10},
                },
            }
        ),
        encoding="utf-8",
    )
    timeout_probe.write_text(
        json.dumps(
            {
                "execute": True,
                "payload_mode": "current",
                "baseline": {"timeout_rate": 0.2},
                "summary": {
                    "executed_count": 20,
                    "timeout_count": 0,
                    "timeout_rate": 0.0,
                    "json_schema_failure_count": 2,
                    "json_schema_failure_rate": 0.1,
                },
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_acceptance(diagnostics, timeout_probe_path=timeout_probe)
    json_check = next(item for item in report["checks"] if item["name"] == "json_schema_failure_rate")

    assert json_check["status"] == "pass"
    assert json_check["evidence"]["source"] == "current_payload_probe"
    assert json_check["evidence"]["json_schema_failure_count"] == 2


def test_acceptance_gate_uses_review_packet_and_executed_timeout_probe(tmp_path: Path) -> None:
    diagnostics = tmp_path / "diagnostics.json"
    benchmark = tmp_path / "benchmark.json"
    review_packet = tmp_path / "packet.json"
    timeout_probe = tmp_path / "timeout.json"
    diagnostics.write_text(
        json.dumps(
            {
                "current_grouping": {"single_group_count": 100, "small_group_count_2_to_4": 80},
                "scenarios": [{"name": "current", "single_group_count": 40, "small_group_count_2_to_4": 30}],
                "rating_distribution": {"star1_or_reject_rate": 0.2},
                "ai_evaluation": {"response_count": 100, "json_parse_failure_count": 1, "timeout_count": 40},
            }
        ),
        encoding="utf-8",
    )
    benchmark.write_text(
        json.dumps(
            {
                "human_verified": True,
                "expected_group_count": 10,
                "mismatch_count": 0,
                "metrics": {"group_overmerged_count": 3},
            }
        ),
        encoding="utf-8",
    )
    review_packet.write_text(
        json.dumps(
            {
                "groups": [
                    {"name": "burst-a", "human_overmerge_ok": True, "human_subjective_ok": True},
                    {"name": "burst-b", "human_overmerge_ok": True, "human_subjective_ok": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    timeout_probe.write_text(
        json.dumps(
            {
                "execute": True,
                "baseline": {"timeout_rate": 0.2},
                "summary": {"executed_count": 10, "timeout_count": 0, "timeout_rate": 0.0},
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_acceptance(diagnostics, benchmark_diff_path=benchmark, review_packet_path=review_packet, timeout_probe_path=timeout_probe)
    statuses = {item["name"]: item["status"] for item in report["checks"]}
    timeout = next(item for item in report["checks"] if item["name"] == "ai_timeout_rate")

    assert statuses["overmerge_safety"] == "pass"
    assert statuses["subjective_benchmark"] == "pass"
    assert statuses["ai_timeout_rate"] == "pass"
    assert timeout["evidence"]["source"] == "timeout_probe"
