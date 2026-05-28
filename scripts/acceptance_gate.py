from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def evaluate_acceptance(
    diagnostics_path: Path,
    *,
    baseline_diagnostics_path: Path | None = None,
    benchmark_diff_path: Path | None = None,
    review_packet_path: Path | None = None,
    timeout_probe_path: Path | None = None,
    max_star1_or_reject_rate: float = 0.6,
    max_json_parse_failure_rate: float = 0.1,
    max_timeout_rate: float = 0.05,
) -> dict[str, Any]:
    diagnostics = _load_json(diagnostics_path)
    baseline = _load_json(baseline_diagnostics_path) if baseline_diagnostics_path else None
    benchmark = _load_json(benchmark_diff_path) if benchmark_diff_path else None
    review_packet = _load_json(review_packet_path) if review_packet_path else None
    timeout_probe = _load_json(timeout_probe_path) if timeout_probe_path else None
    checks = [
        _grouping_reduction_check(diagnostics),
        _overmerge_check(diagnostics, benchmark, review_packet),
        _rating_distribution_check(diagnostics, baseline, max_star1_or_reject_rate),
        _json_failure_check(diagnostics, baseline, timeout_probe, max_json_parse_failure_rate),
        _timeout_check(diagnostics, baseline, timeout_probe, max_timeout_rate),
        _benchmark_expectation_check(benchmark),
        _subjective_benchmark_check(benchmark, review_packet),
    ]
    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "diagnostics": str(diagnostics_path),
            "baseline_diagnostics": str(baseline_diagnostics_path) if baseline_diagnostics_path else None,
            "benchmark_diff": str(benchmark_diff_path) if benchmark_diff_path else None,
            "review_packet": str(review_packet_path) if review_packet_path else None,
            "timeout_probe": str(timeout_probe_path) if timeout_probe_path else None,
        },
        "summary": {
            "pass": sum(1 for item in checks if item["status"] == "pass"),
            "fail": sum(1 for item in checks if item["status"] == "fail"),
            "needs_review": sum(1 for item in checks if item["status"] == "needs_review"),
            "not_evaluated": sum(1 for item in checks if item["status"] == "not_evaluated"),
        },
        "checks": checks,
    }


def write_reports(report: dict[str, Any], output_dir: Path, stem: str = "acceptance-gate") -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report, md_path)
    return {"json": str(json_path), "markdown": str(md_path)}


def _grouping_reduction_check(diagnostics: dict[str, Any]) -> dict[str, Any]:
    current = diagnostics.get("current_grouping") or {}
    scenario = _scenario(diagnostics, "current")
    if not current or not scenario:
        return _check("grouping_reduction", "not_evaluated", "current grouping or scenario metrics are missing")
    old_singles = int(current.get("single_group_count") or 0)
    old_small = int(current.get("small_group_count_2_to_4") or 0)
    new_singles = int(scenario.get("single_group_count") or 0)
    new_small = int(scenario.get("small_group_count_2_to_4") or 0)
    passed = old_singles > 0 and old_small > 0 and new_singles <= old_singles * 0.5 and new_small <= old_small * 0.5
    return _check(
        "grouping_reduction",
        "pass" if passed else "fail",
        "single and 2-4 photo groups should drop by at least 50 percent in the current scenario",
        {"old_single": old_singles, "new_single": new_singles, "old_2_to_4": old_small, "new_2_to_4": new_small},
    )


def _overmerge_check(diagnostics: dict[str, Any], benchmark: dict[str, Any] | None, review_packet: dict[str, Any] | None) -> dict[str, Any]:
    scenario = _scenario(diagnostics, "current") or {}
    risk = scenario.get("internal_gap_risk") or {}
    benchmark_overmerged = (benchmark or {}).get("metrics", {}).get("group_overmerged_count")
    human_verified = bool((benchmark or {}).get("human_verified"))
    packet_review = _review_packet_status(review_packet)
    evidence = {
        "internal_gap_risk": risk,
        "benchmark_group_overmerged_count": benchmark_overmerged,
        "benchmark_human_verified": human_verified,
        "review_packet": packet_review,
    }
    if packet_review["group_count"] > 0 and packet_review["missing_overmerge_count"] == 0:
        passed = packet_review["failed_overmerge_count"] == 0
        return _check(
            "overmerge_safety",
            "pass" if passed else "fail",
            "human review packet overmerge flags are authoritative when every group is reviewed",
            evidence,
        )
    if benchmark_overmerged is not None:
        if not human_verified:
            return _check(
                "overmerge_safety",
                "needs_review",
                "machine benchmark drafts cannot prove unrelated-scene over-merge safety without visual verification",
                evidence,
            )
        return _check(
            "overmerge_safety",
            "pass" if int(benchmark_overmerged) == 0 else "fail",
            "benchmark expectations are the authority for unrelated-scene over-merge safety",
            evidence,
        )
    return _check(
        "overmerge_safety",
        "needs_review",
        "time-gap risk is only a heuristic; visual benchmark review is still required",
        evidence,
    )


def _rating_distribution_check(diagnostics: dict[str, Any], baseline: dict[str, Any] | None, max_rate: float) -> dict[str, Any]:
    rating = diagnostics.get("rating_distribution") or {}
    simulated = diagnostics.get("simulated_rating_distribution") or {}
    rate = simulated.get("star1_or_reject_rate")
    rating_source = simulated.get("source")
    if rate is None:
        rate = rating.get("star1_or_reject_rate")
        rating_source = "persisted_rating_distribution"
    if rate is None:
        return _check("rating_distribution", "not_evaluated", "rating distribution is missing")
    baseline_rate = _rating_rate(baseline)
    improved = baseline_rate is None or float(rate) < float(baseline_rate)
    passed = float(rate) <= max_rate and improved
    return _check(
        "rating_distribution",
        "pass" if passed else "fail",
        f"star1_or_reject_rate must be <= {max_rate} and lower than baseline when provided; simulated current-code ratings are used when present",
        {
            "star1_or_reject_rate": rate,
            "rating_source": rating_source,
            "baseline_star1_or_reject_rate": baseline_rate,
            "persisted_star1_or_reject_rate": rating.get("star1_or_reject_rate"),
            "simulated_star1_or_reject_rate": simulated.get("star1_or_reject_rate"),
            "rating_counts": (simulated or rating).get("rating_counts"),
            "selection_status_counts": (simulated or rating).get("selection_status_counts"),
        },
    )


def _rating_rate(report: dict[str, Any] | None) -> float | None:
    if not report:
        return None
    simulated_rate = (report.get("simulated_rating_distribution") or {}).get("star1_or_reject_rate")
    if simulated_rate is not None:
        return float(simulated_rate)
    persisted_rate = (report.get("rating_distribution") or {}).get("star1_or_reject_rate")
    return float(persisted_rate) if persisted_rate is not None else None


def _json_failure_check(
    diagnostics: dict[str, Any],
    baseline: dict[str, Any] | None,
    timeout_probe: dict[str, Any] | None,
    max_rate: float,
) -> dict[str, Any]:
    ai = diagnostics.get("ai_evaluation") or {}
    response_count = int(ai.get("response_count") or 0)
    original_failure_count = int(ai.get("json_parse_failure_count") or 0)
    probe_summary = (timeout_probe or {}).get("summary") if isinstance((timeout_probe or {}).get("summary"), dict) else {}
    if (
        timeout_probe
        and timeout_probe.get("execute") is True
        and timeout_probe.get("payload_mode") == "current"
        and int(probe_summary.get("executed_count") or 0) > 0
        and probe_summary.get("json_schema_failure_rate") is not None
    ):
        rate = float(probe_summary["json_schema_failure_rate"])
        baseline_rate = round(original_failure_count / response_count, 4) if response_count else _ai_rate(baseline, "json_parse_failure_count")
        improved = baseline_rate is None or rate < baseline_rate
        return _check(
            "json_schema_failure_rate",
            "pass" if rate <= max_rate and improved else "fail",
            f"executed current-payload probe json/schema failure rate must be <= {max_rate} and lower than baseline when provided",
            {
                "json_schema_failure_count": int(probe_summary.get("json_schema_failure_count") or 0),
                "executed_count": int(probe_summary.get("executed_count") or 0),
                "rate": rate,
                "baseline_rate": baseline_rate,
                "source": "current_payload_probe",
                "stored_response_replay": ai.get("failed_response_replay"),
            },
        )
    failure_count = int(ai.get("projected_json_schema_failure_count_after_replay") if ai.get("projected_json_schema_failure_count_after_replay") is not None else original_failure_count)
    if response_count <= 0:
        return _check("json_schema_failure_rate", "not_evaluated", "AI response count is zero")
    rate = round(failure_count / response_count, 4)
    baseline_rate = _ai_rate(baseline, "json_parse_failure_count")
    improved = baseline_rate is None or rate < baseline_rate
    return _check(
        "json_schema_failure_rate",
        "pass" if rate <= max_rate and improved else "fail",
        f"json_parse_failure_rate must be <= {max_rate} and lower than baseline when provided; replay-adjusted current parser count is used when present",
        {
            "json_parse_failure_count": failure_count,
            "original_json_parse_failure_count": original_failure_count,
            "response_count": response_count,
            "rate": rate,
            "baseline_rate": baseline_rate,
            "failed_response_replay": ai.get("failed_response_replay"),
        },
    )


def _timeout_check(diagnostics: dict[str, Any], baseline: dict[str, Any] | None, timeout_probe: dict[str, Any] | None, max_rate: float) -> dict[str, Any]:
    probe_summary = (timeout_probe or {}).get("summary") if isinstance((timeout_probe or {}).get("summary"), dict) else {}
    probe_baseline = (timeout_probe or {}).get("baseline") if isinstance((timeout_probe or {}).get("baseline"), dict) else {}
    if timeout_probe and timeout_probe.get("execute") is True and int(probe_summary.get("executed_count") or 0) > 0 and probe_summary.get("timeout_rate") is not None:
        rate = float(probe_summary["timeout_rate"])
        baseline_rate = probe_baseline.get("timeout_rate")
        improved = baseline_rate is None or rate < float(baseline_rate)
        return _check(
            "ai_timeout_rate",
            "pass" if rate <= max_rate and improved else "fail",
            f"executed timeout probe rate must be <= {max_rate} and lower than baseline when provided",
            {
                "timeout_count": int(probe_summary.get("timeout_count") or 0),
                "executed_count": int(probe_summary.get("executed_count") or 0),
                "rate": rate,
                "baseline_rate": baseline_rate,
                "source": "timeout_probe",
            },
        )
    ai = diagnostics.get("ai_evaluation") or {}
    response_count = int(ai.get("response_count") or 0)
    timeout_count = int(ai.get("timeout_count") or 0)
    if response_count <= 0:
        return _check("ai_timeout_rate", "not_evaluated", "AI response count is zero")
    rate = round(timeout_count / response_count, 4)
    baseline_rate = _ai_rate(baseline, "timeout_count")
    improved = baseline_rate is None or rate < baseline_rate
    return _check(
        "ai_timeout_rate",
        "pass" if rate <= max_rate and improved else "fail",
        f"ai_timeout_rate must be <= {max_rate} and lower than baseline when provided",
        {
            "timeout_count": timeout_count,
            "response_count": response_count,
            "rate": rate,
            "baseline_rate": baseline_rate,
            "source": "diagnostics",
            "timeout_probe": {"execute": (timeout_probe or {}).get("execute"), "summary": probe_summary} if timeout_probe else None,
        },
    )


def _benchmark_expectation_check(benchmark: dict[str, Any] | None) -> dict[str, Any]:
    if benchmark is None:
        return _check("benchmark_expectations", "not_evaluated", "benchmark diff report was not provided")
    count = int(benchmark.get("expected_group_count") or 0)
    return _check(
        "benchmark_expectations",
        "pass" if 10 <= count <= 20 else "fail",
        "benchmark should contain 10 to 20 representative bursts",
        {"expected_group_count": count},
    )


def _subjective_benchmark_check(benchmark: dict[str, Any] | None, review_packet: dict[str, Any] | None) -> dict[str, Any]:
    packet_review = _review_packet_status(review_packet)
    if benchmark is None:
        return _check("subjective_benchmark", "needs_review", "no human-verified benchmark diff was provided", {"review_packet": packet_review})
    if not bool(benchmark.get("human_verified")):
        return _check(
            "subjective_benchmark",
            "needs_review",
            "benchmark diff was generated from a machine draft and still needs human visual verification",
            {
                "expected_group_count": int(benchmark.get("expected_group_count") or 0),
                "mismatch_count": int(benchmark.get("mismatch_count") or 0),
                "metrics": benchmark.get("metrics", {}),
                "review_packet": packet_review,
            },
        )
    mismatch_count = int(benchmark.get("mismatch_count") or 0)
    expected_group_count = int(benchmark.get("expected_group_count") or 0)
    status = "pass" if expected_group_count >= 10 and mismatch_count == 0 else "fail"
    return _check(
        "subjective_benchmark",
        status,
        "human-verified benchmark should have no mismatches across at least 10 bursts",
        {"expected_group_count": expected_group_count, "mismatch_count": mismatch_count, "metrics": benchmark.get("metrics", {}), "review_packet": packet_review},
    )


def _review_packet_status(review_packet: dict[str, Any] | None) -> dict[str, Any]:
    groups = review_packet.get("groups", []) if isinstance(review_packet, dict) and isinstance(review_packet.get("groups"), list) else []
    missing_overmerge = 0
    missing_subjective = 0
    failed_overmerge = 0
    failed_subjective = 0
    for group in groups:
        if not isinstance(group, dict):
            continue
        overmerge = group.get("human_overmerge_ok")
        subjective = group.get("human_subjective_ok")
        if overmerge is None:
            missing_overmerge += 1
        elif overmerge is not True:
            failed_overmerge += 1
        if subjective is None:
            missing_subjective += 1
        elif subjective is not True:
            failed_subjective += 1
    return {
        "provided": review_packet is not None,
        "group_count": len(groups),
        "missing_overmerge_count": missing_overmerge,
        "missing_subjective_count": missing_subjective,
        "failed_overmerge_count": failed_overmerge,
        "failed_subjective_count": failed_subjective,
    }


def _scenario(diagnostics: dict[str, Any], name: str) -> dict[str, Any] | None:
    for item in diagnostics.get("scenarios", []):
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _ai_rate(diagnostics: dict[str, Any] | None, key: str) -> float | None:
    if diagnostics is None:
        return None
    ai = diagnostics.get("ai_evaluation") or {}
    response_count = int(ai.get("response_count") or 0)
    if response_count <= 0:
        return None
    return round(int(ai.get(key) or 0) / response_count, 4)


def _check(name: str, status: str, detail: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail, "evidence": evidence or {}}


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# SkySort Acceptance Gate",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- pass: {report['summary']['pass']}",
        f"- fail: {report['summary']['fail']}",
        f"- needs_review: {report['summary']['needs_review']}",
        f"- not_evaluated: {report['summary']['not_evaluated']}",
        "",
        "| check | status | detail |",
        "|---|---|---|",
    ]
    for item in report["checks"]:
        lines.append(f"| {item['name']} | {item['status']} | {item['detail']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate real-data SkySort acceptance evidence from diagnostics and optional benchmark diff reports.")
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--baseline-diagnostics", type=Path, default=None)
    parser.add_argument("--benchmark-diff", type=Path, default=None)
    parser.add_argument("--review-packet", type=Path, default=None)
    parser.add_argument("--timeout-probe", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("var/tmp"))
    parser.add_argument("--stem", default="acceptance-gate")
    parser.add_argument("--max-star1-or-reject-rate", type=float, default=0.6)
    parser.add_argument("--max-json-parse-failure-rate", type=float, default=0.1)
    parser.add_argument("--max-timeout-rate", type=float, default=0.05)
    args = parser.parse_args()

    report = evaluate_acceptance(
        args.diagnostics,
        baseline_diagnostics_path=args.baseline_diagnostics,
        benchmark_diff_path=args.benchmark_diff,
        review_packet_path=args.review_packet,
        timeout_probe_path=args.timeout_probe,
        max_star1_or_reject_rate=args.max_star1_or_reject_rate,
        max_json_parse_failure_rate=args.max_json_parse_failure_rate,
        max_timeout_rate=args.max_timeout_rate,
    )
    print(json.dumps(write_reports(report, args.output_dir, stem=args.stem), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
