from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

API_SRC = Path(__file__).resolve().parents[1] / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from skysort_api.domain.evaluation import (  # noqa: E402
    TechnicalMetrics,
    compute_technical_total,
    provisional_rating_from_technical_decision,
    technical_candidate_quality,
    technical_reject_risk,
)
from skysort_api.domain.grouping import PhotoCandidate, grouping_boundary_reason  # noqa: E402


DEFAULT_TIME_PROXIMITY_SECONDS = 8
DEFAULT_SIMILARITY_THRESHOLD = 0.8
TIME_GAP_BUCKETS = [1, 2, 4, 8, 12, 30, 60]
TECHNICAL_FIELDS = [
    "sharpness_score",
    "motion_blur_score",
    "highlight_clip_ratio",
    "shadow_clip_ratio",
    "technical_score_total",
    "sharpness_rank",
    "exposure_rank",
    "candidate_quality_score",
    "reject_risk_score",
]


@dataclass(frozen=True)
class Scenario:
    name: str
    time_proximity_seconds: int
    similarity_threshold: float


def validate_grouping(fixture_path: Path) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    return build_validation_report(fixture)


def build_validation_report(fixture: dict[str, Any]) -> dict[str, Any]:
    if fixture.get("schema_version") != "v1":
        raise ValueError("grouping validation schema_version must be v1")
    candidates = [_candidate(item) for item in fixture.get("photos", []) if isinstance(item, dict)]
    scenarios = [_scenario(item) for item in fixture.get("scenarios", []) if isinstance(item, dict)]
    if not scenarios:
        scenarios = [Scenario(name="default", time_proximity_seconds=DEFAULT_TIME_PROXIMITY_SECONDS, similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD)]

    report: dict[str, Any] = {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": fixture.get("source") or {"type": "fixture"},
        "photo_count": len(candidates),
        "scenarios": [_evaluate_scenario(candidates, scenario) for scenario in scenarios],
    }
    current_grouping = _current_grouping_report(fixture.get("photos", []))
    if current_grouping:
        report["current_grouping"] = current_grouping
    technical_report = _technical_score_report(fixture.get("technical_scores", []), fixture.get("photos", []))
    if technical_report:
        report["technical_scores"] = technical_report
    ai_report = _ai_evaluation_report(fixture.get("ai_responses", []), fixture.get("job_failures", []), fixture.get("photo_evaluations", []))
    if ai_report:
        report["ai_evaluation"] = ai_report
    rating_report = _rating_distribution_report(fixture.get("photo_evaluations", []))
    if rating_report:
        report["rating_distribution"] = rating_report
    simulated_rating_report = _simulated_rating_distribution_report(
        fixture.get("technical_scores", []),
        str(fixture.get("technical_score_source") or "stored_technical_scores"),
    )
    if simulated_rating_report:
        report["simulated_rating_distribution"] = simulated_rating_report
    return report


def load_fixture_from_db(
    db_path: Path,
    job_id: str | None = None,
    scenarios: list[Scenario] | None = None,
    *,
    rescore_technical: bool = False,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        selected_job_id = job_id or _latest_job_id(connection)
        settings_snapshot = _job_settings_snapshot(connection, selected_job_id)
        fixture_scenarios = scenarios or _default_scenarios(settings_snapshot)
        photos = _photos_from_db(connection, selected_job_id)
        technical_scores = _rescore_technical_scores(photos) if rescore_technical else _technical_scores_from_db(connection, selected_job_id)
        return {
            "schema_version": "v1",
            "source": {"type": "db", "db_path": str(db_path), "job_id": selected_job_id},
            "photos": photos,
            "technical_scores": technical_scores,
            "technical_score_source": "rescored_current_code" if rescore_technical else "stored_technical_scores",
            "ai_responses": _ai_responses_from_db(connection, selected_job_id),
            "job_failures": _job_failures_from_db(connection, selected_job_id),
            "photo_evaluations": _photo_evaluations_from_db(connection, selected_job_id),
            "scenarios": [
                {
                    "name": scenario.name,
                    "time_proximity_seconds": scenario.time_proximity_seconds,
                    "similarity_threshold": scenario.similarity_threshold,
                }
                for scenario in fixture_scenarios
            ],
        }


def write_report(report: dict[str, Any], output_dir: Path, stem: str = "grouping-validation") -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report, md_path)
    return {"json": str(json_path), "markdown": str(md_path)}


def write_fixture(fixture: dict[str, Any], output_dir: Path, stem: str = "grouping-fixture") -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{stem}.json"
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _latest_job_id(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        """
        SELECT id
        FROM jobs
        ORDER BY COALESCE(finished_at, updated_at, started_at) DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise ValueError("No jobs found in DB")
    return str(row["id"])


def _job_settings_snapshot(connection: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    row = connection.execute("SELECT settings_snapshot_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"Job not found: {job_id}")
    try:
        return json.loads(row["settings_snapshot_json"] or "{}")
    except json.JSONDecodeError:
        return {}


def _default_scenarios(settings_snapshot: dict[str, Any]) -> list[Scenario]:
    base_time = int(settings_snapshot.get("time_proximity_seconds") or DEFAULT_TIME_PROXIMITY_SECONDS)
    base_similarity = float(settings_snapshot.get("similarity_threshold") or DEFAULT_SIMILARITY_THRESHOLD)
    return [
        Scenario("current", base_time, base_similarity),
        Scenario("time-8s", 8, base_similarity),
        Scenario("time-12s", 12, base_similarity),
        Scenario("looser-similarity", base_time, max(0.0, round(base_similarity - 0.06, 3))),
        Scenario("stricter-similarity", base_time, min(1.0, round(base_similarity + 0.06, 3))),
    ]


def _photos_from_db(connection: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            p.id AS photo_id,
            p.file_path,
            p.file_name,
            p.capture_timestamp_ms,
            p.capture_order_index,
            p.capture_time,
            p.camera_model,
            p.lens_model,
            p.focal_length,
            p.is_missing,
            p.visual_features_json,
            gm.group_id,
            gm.sort_order AS group_sort_order,
            gm.similarity_score,
            g.boundary_reason,
            g.merge_suggested,
            g.merge_suggestion_reason
        FROM photos p
        LEFT JOIN group_members gm ON gm.photo_id = p.id
        LEFT JOIN groups g ON g.id = gm.group_id
        WHERE p.job_id = ?
        ORDER BY
            CASE WHEN p.capture_timestamp_ms IS NULL THEN 1 ELSE 0 END,
            p.capture_timestamp_ms,
            p.capture_order_index,
            p.file_path
        """,
        (job_id,),
    ).fetchall()
    return [_photo_row_to_fixture(row) for row in rows]


def _photo_row_to_fixture(row: sqlite3.Row) -> dict[str, Any]:
    similarity_score = row["similarity_score"]
    visual_features = _parse_json_object(row["visual_features_json"])
    return {
        "photo_id": row["photo_id"],
        "relative_path": row["file_name"],
        "file_path": row["file_path"],
        "capture_timestamp_ms": row["capture_timestamp_ms"],
        "capture_order_index": row["capture_order_index"],
        "capture_time": row["capture_time"],
        "camera_model": row["camera_model"],
        "lens_model": row["lens_model"],
        "focal_length": row["focal_length"],
        "is_missing": bool(row["is_missing"]),
        "current_group_id": row["group_id"],
        "current_group_sort_order": row["group_sort_order"],
        "current_group_similarity_score": similarity_score,
        "boundary_reason": row["boundary_reason"],
        "merge_suggested": bool(row["merge_suggested"]) if row["merge_suggested"] is not None else False,
        "merge_suggestion_reason": row["merge_suggestion_reason"],
        "visual_features": visual_features,
        "similarity_seed": _seed_from_visual_features(visual_features, similarity_score),
    }


def _seed_from_stored_similarity(similarity_score: float | None) -> float:
    if similarity_score is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - float(similarity_score)))


def _seed_from_visual_features(visual_features: dict[str, object], similarity_score: float | None) -> float:
    phash = visual_features.get("phash")
    if phash:
        try:
            return int(str(phash)[:4], 16) / 65535.0
        except ValueError:
            pass
    return _seed_from_stored_similarity(similarity_score)


def _parse_json_object(payload: str | None) -> dict[str, object]:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _technical_scores_from_db(connection: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            photo_id,
            sharpness_score,
            motion_blur_score,
            highlight_clip_ratio,
            shadow_clip_ratio,
            technical_score_total,
            sharpness_rank,
            exposure_rank,
            candidate_quality_score,
            reject_risk_score
        FROM technical_scores
        WHERE job_id = ?
        """,
        (job_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _rescore_technical_scores(photos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from skysort_api.infra.image_tools import compute_technical_metrics
    from skysort_api.infra.settings import get_settings

    settings = get_settings()
    rows: list[dict[str, Any]] = []
    for photo in photos:
        file_path = photo.get("file_path")
        if photo.get("is_missing") or not file_path:
            continue
        path = Path(str(file_path))
        if not path.exists():
            continue
        metrics_raw = compute_technical_metrics(path, settings.highlight_threshold, settings.shadow_threshold)
        metrics = TechnicalMetrics(
            sharpness_score=float(metrics_raw["sharpness_score"]),
            motion_blur_score=float(metrics_raw["motion_blur_score"]),
            highlight_clip_ratio=float(metrics_raw["highlight_clip_ratio"]),
            shadow_clip_ratio=float(metrics_raw["shadow_clip_ratio"]),
        )
        rows.append(
            {
                "photo_id": photo["photo_id"],
                "current_group_id": photo.get("current_group_id"),
                "sharpness_score": metrics.sharpness_score,
                "motion_blur_score": metrics.motion_blur_score,
                "highlight_clip_ratio": metrics.highlight_clip_ratio,
                "shadow_clip_ratio": metrics.shadow_clip_ratio,
                "technical_score_total": compute_technical_total(metrics),
                "sharpness_rank": None,
                "exposure_rank": None,
                "candidate_quality_score": None,
                "reject_risk_score": None,
            }
        )

    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[str(row.get("current_group_id") or row["photo_id"])].append(row)

    for group_rows in by_group.values():
        sharpness_ranks = _rank_percentiles({str(row["photo_id"]): float(row["sharpness_score"]) for row in group_rows})
        exposure_ranks = _rank_percentiles(
            {
                str(row["photo_id"]): max(
                    0.0,
                    100.0 - (float(row["highlight_clip_ratio"]) * 180.0) - (float(row["shadow_clip_ratio"]) * 140.0),
                )
                for row in group_rows
            }
        )
        for row in group_rows:
            photo_id = str(row["photo_id"])
            sharpness_rank = sharpness_ranks[photo_id]
            exposure_rank = exposure_ranks[photo_id]
            row["sharpness_rank"] = sharpness_rank
            row["exposure_rank"] = exposure_rank
            row["candidate_quality_score"] = technical_candidate_quality(
                float(row["technical_score_total"]),
                sharpness_rank,
                exposure_rank,
                float(row["motion_blur_score"]),
            )
            row["reject_risk_score"] = technical_reject_risk(
                float(row["highlight_clip_ratio"]),
                float(row["shadow_clip_ratio"]),
                float(row["motion_blur_score"]),
                sharpness_rank,
            )
    return rows


def _rank_percentiles(values_by_photo_id: dict[str, float]) -> dict[str, float]:
    if not values_by_photo_id:
        return {}
    if len(values_by_photo_id) == 1:
        return {next(iter(values_by_photo_id)): 100.0}
    ordered = sorted(values_by_photo_id.items(), key=lambda item: item[1])
    denominator = len(ordered) - 1
    return {
        photo_id: round((index / denominator) * 100.0, 2)
        for index, (photo_id, _value) in enumerate(ordered)
    }


def _ai_responses_from_db(connection: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT phase, response_status, group_id, photo_id, latency_ms, target_photo_ids_json, raw_response_text
        FROM ai_responses
        WHERE job_id = ?
        """,
        (job_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _job_failures_from_db(connection: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT stage, reason_code, retryable, group_id, photo_id
        FROM job_failures
        WHERE job_id = ?
        """,
        (job_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _photo_evaluations_from_db(connection: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT photo_id, group_id, evaluation_status, semantic_score, selection_status, rating, is_current
        FROM photo_evaluations
        WHERE job_id = ? AND is_current = 1
        """,
        (job_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _candidate(item: dict[str, Any]) -> PhotoCandidate:
    return PhotoCandidate(
        photo_id=str(item.get("photo_id") or item.get("id") or item.get("relative_path")),
        capture_timestamp_ms=int(item["capture_timestamp_ms"]) if item.get("capture_timestamp_ms") is not None else None,
        capture_order_index=int(item.get("capture_order_index") or 0),
        similarity_seed=float(item.get("similarity_seed") or 0.0),
        visual_features=item.get("visual_features") if isinstance(item.get("visual_features"), dict) else None,
    )


def _scenario(item: dict[str, Any]) -> Scenario:
    return Scenario(
        name=str(item.get("name") or "scenario"),
        time_proximity_seconds=int(item.get("time_proximity_seconds", DEFAULT_TIME_PROXIMITY_SECONDS)),
        similarity_threshold=float(item.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)),
    )


def _evaluate_scenario(candidates: list[PhotoCandidate], scenario: Scenario) -> dict[str, Any]:
    groups, boundaries = _group_candidates(candidates, scenario)
    group_sizes = [len(group) for group in groups]
    adjacency = _adjacent_time_gap_summary(_ordered_candidates(candidates))
    boundary_reasons = Counter(boundary["reason"] for boundary in boundaries)
    return {
        "name": scenario.name,
        "time_proximity_seconds": scenario.time_proximity_seconds,
        "similarity_threshold": scenario.similarity_threshold,
        "group_count": len(groups),
        "single_group_count": sum(1 for size in group_sizes if size == 1),
        "small_group_count_2_to_4": sum(1 for size in group_sizes if 2 <= size <= 4),
        "average_group_size": round(sum(group_sizes) / len(group_sizes), 3) if group_sizes else 0,
        "group_size_distribution": _size_distribution(group_sizes),
        "adjacent_time_gap_seconds": adjacency,
        "split_boundary_count": len(boundaries),
        "split_within_time_threshold_count": sum(1 for boundary in boundaries if boundary.get("gap_seconds") is not None and boundary["gap_seconds"] <= scenario.time_proximity_seconds),
        "boundary_reason_counts": dict(sorted(boundary_reasons.items())),
        "internal_gap_risk": _internal_gap_risk([[_candidate_to_dict(candidate) for candidate in group] for group in groups]),
        "groups": [[candidate.photo_id for candidate in group] for group in groups],
    }


def _group_candidates(candidates: list[PhotoCandidate], scenario: Scenario) -> tuple[list[list[PhotoCandidate]], list[dict[str, Any]]]:
    ordered = _ordered_candidates(candidates)
    groups: list[list[PhotoCandidate]] = []
    current: list[PhotoCandidate] = []
    boundaries: list[dict[str, Any]] = []
    for candidate in ordered:
        reason = grouping_boundary_reason(current, candidate, scenario.time_proximity_seconds, scenario.similarity_threshold)
        if reason is not None and current:
            previous = current[-1]
            boundaries.append(
                {
                    "previous_photo_id": previous.photo_id,
                    "current_photo_id": candidate.photo_id,
                    "gap_seconds": _time_gap_seconds(previous, candidate),
                    "reason": reason,
                }
            )
            groups.append(current)
            current = []
        current.append(candidate)
    if current:
        groups.append(current)
    return groups, boundaries


def _candidate_to_dict(candidate: PhotoCandidate) -> dict[str, Any]:
    return {
        "photo_id": candidate.photo_id,
        "capture_timestamp_ms": candidate.capture_timestamp_ms,
        "capture_order_index": candidate.capture_order_index,
    }


def _ordered_candidates(candidates: list[PhotoCandidate]) -> list[PhotoCandidate]:
    return sorted(
        candidates,
        key=lambda item: (
            item.capture_timestamp_ms if item.capture_timestamp_ms is not None else float("inf"),
            item.capture_order_index,
            item.photo_id,
        ),
    )


def _time_gap_seconds(previous: PhotoCandidate | None, current: PhotoCandidate) -> float | None:
    if previous is None or previous.capture_timestamp_ms is None or current.capture_timestamp_ms is None:
        return None
    return abs(current.capture_timestamp_ms - previous.capture_timestamp_ms) / 1000.0


def _current_grouping_report(photos: list[dict[str, Any]]) -> dict[str, Any] | None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for photo in photos:
        group_id = photo.get("current_group_id")
        if group_id:
            grouped[str(group_id)].append(photo)
    if not grouped:
        return None
    sizes = [len(items) for items in grouped.values()]
    ordered_groups = sorted(grouped.values(), key=_group_sort_key)
    boundary_gaps = []
    for previous, current in zip(ordered_groups, ordered_groups[1:], strict=False):
        previous_end = _group_end_timestamp(previous)
        current_start = _group_start_timestamp(current)
        gap = None if previous_end is None or current_start is None else max(0.0, (current_start - previous_end) / 1000.0)
        boundary_gaps.append(gap)
    return {
        "group_count": len(grouped),
        "single_group_count": sum(1 for size in sizes if size == 1),
        "small_group_count_2_to_4": sum(1 for size in sizes if 2 <= size <= 4),
        "average_group_size": round(sum(sizes) / len(sizes), 3) if sizes else 0,
        "group_size_distribution": _size_distribution(sizes),
        "adjacent_group_time_gap_seconds": _numeric_summary([gap for gap in boundary_gaps if gap is not None], buckets=TIME_GAP_BUCKETS),
        "adjacent_group_boundaries_within_4s": sum(1 for gap in boundary_gaps if gap is not None and gap <= 4),
        "adjacent_group_boundaries_within_8s": sum(1 for gap in boundary_gaps if gap is not None and gap <= 8),
        "adjacent_group_boundaries_within_12s": sum(1 for gap in boundary_gaps if gap is not None and gap <= 12),
        "boundary_reason_counts": _current_boundary_reason_counts(ordered_groups),
        "merge_suggested_count": sum(1 for items in grouped.values() if any(item.get("merge_suggested") for item in items)),
        "internal_gap_risk": _internal_gap_risk(ordered_groups),
    }


def _current_boundary_reason_counts(ordered_groups: list[list[dict[str, Any]]]) -> dict[str, int]:
    counts = Counter()
    for group in ordered_groups:
        reasons = {str(item.get("boundary_reason")) for item in group if item.get("boundary_reason")}
        for reason in reasons:
            counts[reason] += 1
    return dict(sorted(counts.items()))


def _group_sort_key(items: list[dict[str, Any]]) -> tuple[float, int, str]:
    timestamps = [item.get("capture_timestamp_ms") for item in items if item.get("capture_timestamp_ms") is not None]
    orders = [int(item.get("capture_order_index") or 0) for item in items]
    return (min(timestamps) if timestamps else float("inf"), min(orders) if orders else 0, str(items[0].get("current_group_id")))


def _group_start_timestamp(items: list[dict[str, Any]]) -> int | None:
    timestamps = [item.get("capture_timestamp_ms") for item in items if item.get("capture_timestamp_ms") is not None]
    return int(min(timestamps)) if timestamps else None


def _group_end_timestamp(items: list[dict[str, Any]]) -> int | None:
    timestamps = [item.get("capture_timestamp_ms") for item in items if item.get("capture_timestamp_ms") is not None]
    return int(max(timestamps)) if timestamps else None


def _internal_gap_risk(groups: list[list[dict[str, Any]]]) -> dict[str, Any]:
    max_gaps = []
    for items in groups:
        ordered = sorted(
            items,
            key=lambda item: (
                item.get("capture_timestamp_ms") if item.get("capture_timestamp_ms") is not None else float("inf"),
                int(item.get("capture_order_index") or 0),
                str(item.get("photo_id")),
            ),
        )
        gaps = []
        for previous, current in zip(ordered, ordered[1:], strict=False):
            previous_ts = previous.get("capture_timestamp_ms")
            current_ts = current.get("capture_timestamp_ms")
            if previous_ts is not None and current_ts is not None:
                gaps.append(max(0.0, (float(current_ts) - float(previous_ts)) / 1000.0))
        if gaps:
            max_gaps.append(max(gaps))
    return {
        "groups_with_internal_gap_over_4s": sum(1 for gap in max_gaps if gap > 4),
        "groups_with_internal_gap_over_8s": sum(1 for gap in max_gaps if gap > 8),
        "groups_with_internal_gap_over_12s": sum(1 for gap in max_gaps if gap > 12),
        "groups_with_internal_gap_over_30s": sum(1 for gap in max_gaps if gap > 30),
        "max_internal_gap_seconds": round(max(max_gaps), 4) if max_gaps else None,
    }


def _technical_score_report(scores: list[dict[str, Any]], photos: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not scores:
        return None
    by_photo_id = {str(item["photo_id"]): item for item in scores}
    group_ranks = _group_rank_summary(by_photo_id, photos)
    return {
        "scored_photo_count": len(scores),
        "fields": {field: _numeric_summary([float(item[field]) for item in scores if item.get(field) is not None]) for field in TECHNICAL_FIELDS},
        "group_rank": group_ranks,
    }


def _group_rank_summary(scores_by_photo_id: dict[str, dict[str, Any]], photos: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for photo in photos:
        group_id = photo.get("current_group_id")
        if group_id and str(photo.get("photo_id")) in scores_by_photo_id:
            grouped[str(group_id)].append(photo)
    spreads = []
    ranked_groups = 0
    for group_photos in grouped.values():
        totals = [float(scores_by_photo_id[str(photo["photo_id"])]["technical_score_total"]) for photo in group_photos]
        if len(totals) < 2:
            continue
        ranked_groups += 1
        spreads.append(max(totals) - min(totals))
    return {
        "ranked_group_count": ranked_groups,
        "technical_total_spread": _numeric_summary(spreads),
    }


def _ai_evaluation_report(ai_responses: list[dict[str, Any]], failures: list[dict[str, Any]], evaluations: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not ai_responses and not failures and not evaluations:
        return None
    status_by_phase: dict[str, Counter[str]] = defaultdict(Counter)
    for response in ai_responses:
        status_by_phase[str(response.get("phase") or "unknown")][str(response.get("response_status") or "unknown")] += 1
    failure_reasons = Counter(str(item.get("reason_code") or "unknown") for item in failures)
    evaluation_statuses = Counter(str(item.get("evaluation_status") or "unknown") for item in evaluations)
    semantic_scored = sum(1 for item in evaluations if item.get("semantic_score") is not None)
    replay = _ai_failure_replay_report(ai_responses)
    json_parse_failure_count = failure_reasons.get("json_parse_failed", 0)
    replay_recovered_count = replay.get("schema_valid_count", 0) if replay else 0
    projected_json_schema_failure_count = max(0, json_parse_failure_count - replay_recovered_count)
    return {
        "response_count": len(ai_responses),
        "response_status_by_phase": {phase: dict(sorted(counter.items())) for phase, counter in sorted(status_by_phase.items())},
        "failure_reason_counts": dict(sorted(failure_reasons.items())),
        "json_parse_failure_count": json_parse_failure_count,
        "projected_json_schema_failure_count_after_replay": projected_json_schema_failure_count,
        "projected_json_schema_failure_rate_after_replay": round(projected_json_schema_failure_count / len(ai_responses), 4) if ai_responses else None,
        "timeout_count": failure_reasons.get("ai_timeout", 0),
        "ai_eval_failed_count": evaluation_statuses.get("ai_eval_failed", 0),
        "group_compare_success_rate": _phase_success_rate(ai_responses, "group_compare"),
        "single_success_rate": _phase_success_rate(ai_responses, "single"),
        "semantic_scored_photo_count": semantic_scored,
        "evaluation_status_counts": dict(sorted(evaluation_statuses.items())),
        "failed_response_replay": replay,
    }


def _ai_failure_replay_report(ai_responses: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [item for item in ai_responses if item.get("response_status") == "ai_eval_failed"]
    raw_items = [item for item in failed if item.get("raw_response_text")]
    json_recovered = 0
    schema_valid = 0
    by_phase: dict[str, Counter[str]] = defaultdict(Counter)
    if raw_items:
        from skysort_api.services.analysis_service import normalize_and_validate_ai_payload
    else:
        normalize_and_validate_ai_payload = None
    for item in raw_items:
        phase = str(item.get("phase") or "unknown")
        parsed = _recover_json_payload(str(item.get("raw_response_text") or ""))
        if parsed is None:
            by_phase[phase]["json_unrecoverable"] += 1
            continue
        json_recovered += 1
        target_ids = _json_string_list(item.get("target_photo_ids_json"))
        normalized = normalize_and_validate_ai_payload(phase, parsed, target_ids) if normalize_and_validate_ai_payload else None
        if normalized is None:
            by_phase[phase]["schema_invalid"] += 1
            continue
        schema_valid += 1
        by_phase[phase]["schema_valid"] += 1
    return {
        "failed_response_count": len(failed),
        "raw_response_count": len(raw_items),
        "json_recovered_count": json_recovered,
        "schema_valid_count": schema_valid,
        "by_phase": {phase: dict(sorted(counter.items())) for phase, counter in sorted(by_phase.items())},
    }


def _json_string_list(value: object) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, str)] if isinstance(parsed, list) else []


def _recover_json_payload(raw_text: str) -> dict[str, object] | None:
    for candidate in (raw_text, _extract_json_payload(raw_text)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_json_payload(raw_text: str) -> str | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return raw_text[start : end + 1]


def _phase_success_rate(ai_responses: list[dict[str, Any]], phase_name: str) -> float | None:
    phase_items = [item for item in ai_responses if str(item.get("phase") or "").startswith(phase_name)]
    if not phase_items:
        return None
    successes = sum(1 for item in phase_items if item.get("response_status") == "success")
    return round(successes / len(phase_items), 4)


def _rating_distribution_report(evaluations: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not evaluations:
        return None
    current = [item for item in evaluations if item.get("is_current") in {1, True, "1"}]
    if not current:
        current = evaluations
    rating_counts = Counter(str(item.get("rating")) if item.get("rating") is not None else "none" for item in current)
    selection_counts = Counter(str(item.get("selection_status") or "unknown") for item in current)
    final_count = sum(1 for item in current if item.get("evaluation_status") == "final")
    provisional_count = sum(1 for item in current if item.get("evaluation_status") == "provisional")
    star1_count = rating_counts.get("1", 0)
    reject_count = selection_counts.get("rejected", 0)
    star1_or_reject = sum(
        1
        for item in current
        if item.get("rating") == 1 or str(item.get("selection_status") or "") == "rejected"
    )
    return {
        "evaluated_photo_count": len(current),
        "rating_counts": dict(sorted(rating_counts.items())),
        "selection_status_counts": dict(sorted(selection_counts.items())),
        "final_count": final_count,
        "provisional_count": provisional_count,
        "star1_count": star1_count,
        "reject_count": reject_count,
        "star1_or_reject_count": star1_or_reject,
        "star1_or_reject_rate": round(star1_or_reject / len(current), 4) if current else None,
    }


def _simulated_rating_distribution_report(scores: list[dict[str, Any]], score_source: str) -> dict[str, Any] | None:
    if not scores:
        return None
    simulated = []
    for score in scores:
        decision_score = score.get("candidate_quality_score")
        if decision_score is None:
            decision_score = score.get("technical_score_total")
        if decision_score is None:
            continue
        reject_risk_score = score.get("reject_risk_score")
        rating, selection_status = provisional_rating_from_technical_decision(
            float(decision_score),
            reject_risk_score=float(reject_risk_score) if reject_risk_score is not None else None,
        )
        simulated.append(
            {
                "photo_id": score.get("photo_id"),
                "rating": rating,
                "selection_status": selection_status,
                "evaluation_status": "provisional",
                "is_current": True,
            }
        )
    report = _rating_distribution_report(simulated)
    if report is None:
        return None
    report["source"] = f"current_scoring_from_{score_source}"
    return report


def _adjacent_time_gap_summary(candidates: list[PhotoCandidate]) -> dict[str, Any]:
    gaps = [_time_gap_seconds(previous, current) for previous, current in zip(candidates, candidates[1:], strict=False)]
    return _numeric_summary([gap for gap in gaps if gap is not None], buckets=TIME_GAP_BUCKETS)


def _size_distribution(sizes: Iterable[int]) -> dict[str, int]:
    buckets = Counter()
    for size in sizes:
        if size <= 1:
            buckets["1"] += 1
        elif size <= 4:
            buckets["2-4"] += 1
        elif size <= 6:
            buckets["5-6"] += 1
        elif size <= 10:
            buckets["7-10"] += 1
        else:
            buckets["11+"] += 1
    return dict(buckets)


def _numeric_summary(values: list[float], buckets: list[int] | None = None) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    summary: dict[str, Any] = {
        "count": len(ordered),
        "min": round(ordered[0], 4),
        "median": round(median(ordered), 4),
        "average": round(mean(ordered), 4),
        "p90": round(_percentile(ordered, 0.9), 4),
        "max": round(ordered[-1], 4),
    }
    if buckets:
        summary["buckets"] = _bucket_counts(ordered, buckets)
    return summary


def _percentile(ordered_values: list[float], percentile: float) -> float:
    if not ordered_values:
        return 0.0
    index = (len(ordered_values) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered_values) - 1)
    weight = index - lower
    return ordered_values[lower] * (1 - weight) + ordered_values[upper] * weight


def _bucket_counts(values: list[float], buckets: list[int]) -> dict[str, int]:
    counts: dict[str, int] = {}
    remaining = list(values)
    lower_label = "0"
    for bucket in buckets:
        count = sum(1 for value in remaining if value <= bucket)
        counts[f"{lower_label}-{bucket}"] = count
        remaining = [value for value in remaining if value > bucket]
        lower_label = str(bucket)
    counts[f">{buckets[-1]}"] = len(remaining)
    return counts


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# SkySort Grouping Validation",
        "",
        f"- source: {_source_label(report.get('source'))}",
        f"- photo_count: {report['photo_count']}",
        "",
    ]
    if report.get("current_grouping"):
        current = report["current_grouping"]
        lines.extend(
            [
                "## Current DB Grouping",
                "",
                f"- groups: {current['group_count']}",
                f"- single groups: {current['single_group_count']}",
                f"- 2-4 photo groups: {current['small_group_count_2_to_4']}",
                f"- average group size: {current['average_group_size']}",
                f"- adjacent group boundaries <= 4s: {current['adjacent_group_boundaries_within_4s']}",
                f"- adjacent group boundaries <= 8s: {current['adjacent_group_boundaries_within_8s']}",
                f"- adjacent group boundaries <= 12s: {current['adjacent_group_boundaries_within_12s']}",
                f"- boundary reasons: {_compact_counts(current.get('boundary_reason_counts', {}))}",
                f"- merge suggested groups: {current.get('merge_suggested_count', 0)}",
                f"- internal gap risk: {_compact_counts(current.get('internal_gap_risk', {}))}",
                "",
            ]
        )
    lines.extend(
        [
            "## Scenario Sweep",
            "",
            "| scenario | time proximity | similarity | groups | singles | 2-4 groups | average size | split boundaries | within threshold splits | boundary reasons |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in report["scenarios"]:
        lines.append(
            f"| {item['name']} | {item['time_proximity_seconds']} | {item['similarity_threshold']} | {item['group_count']} | {item['single_group_count']} | {item.get('small_group_count_2_to_4', '')} | {item['average_group_size']} | {item.get('split_boundary_count', '')} | {item.get('split_within_time_threshold_count', '')} | {_compact_counts(item.get('boundary_reason_counts', {}))} |"
        )
    if report.get("technical_scores"):
        technical = report["technical_scores"]
        lines.extend(["", "## Technical Score Distribution", "", f"- scored photos: {technical['scored_photo_count']}", ""])
        lines.extend(["| field | count | min | median | average | p90 | max |", "|---|---:|---:|---:|---:|---:|---:|"])
        for field, summary in technical["fields"].items():
            lines.append(
                f"| {field} | {summary.get('count', 0)} | {summary.get('min', '')} | {summary.get('median', '')} | {summary.get('average', '')} | {summary.get('p90', '')} | {summary.get('max', '')} |"
            )
        spread = technical["group_rank"]["technical_total_spread"]
        lines.extend(
            [
                "",
                f"- ranked groups: {technical['group_rank']['ranked_group_count']}",
                f"- group total-score spread median: {spread.get('median', '')}",
            ]
        )
    if report.get("rating_distribution"):
        ratings = report["rating_distribution"]
        lines.extend(
            [
                "",
                "## Rating Distribution",
                "",
                f"- evaluated photos: {ratings['evaluated_photo_count']}",
                f"- rating counts: {_compact_counts(ratings['rating_counts'])}",
                f"- selection counts: {_compact_counts(ratings['selection_status_counts'])}",
                f"- final/provisional: {ratings['final_count']} / {ratings['provisional_count']}",
                f"- star1 or reject: {ratings['star1_or_reject_count']} ({ratings['star1_or_reject_rate']})",
            ]
        )
    if report.get("simulated_rating_distribution"):
        ratings = report["simulated_rating_distribution"]
        lines.extend(
            [
                "",
                "## Simulated Current-Code Rating Distribution",
                "",
                f"- source: {ratings['source']}",
                f"- evaluated photos: {ratings['evaluated_photo_count']}",
                f"- rating counts: {_compact_counts(ratings['rating_counts'])}",
                f"- selection counts: {_compact_counts(ratings['selection_status_counts'])}",
                f"- star1 or reject: {ratings['star1_or_reject_count']} ({ratings['star1_or_reject_rate']})",
            ]
        )
    if report.get("ai_evaluation"):
        ai = report["ai_evaluation"]
        lines.extend(
            [
                "",
                "## AI Evaluation",
                "",
                f"- responses: {ai['response_count']}",
                f"- json parse failures: {ai['json_parse_failure_count']}",
                f"- projected json/schema failures after replay: {ai['projected_json_schema_failure_count_after_replay']} ({ai['projected_json_schema_failure_rate_after_replay']})",
                f"- timeouts: {ai['timeout_count']}",
                f"- ai_eval_failed photos: {ai['ai_eval_failed_count']}",
                f"- group compare success rate: {ai['group_compare_success_rate']}",
                f"- single success rate: {ai['single_success_rate']}",
                f"- semantic scored photos: {ai['semantic_scored_photo_count']}",
                f"- failure reasons: {_compact_counts(ai['failure_reason_counts'])}",
                f"- failed response replay: {_compact_counts(ai.get('failed_response_replay', {}))}",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _source_label(source: object) -> str:
    if isinstance(source, dict) and source.get("type") == "db":
        return f"db job {source.get('job_id')} ({source.get('db_path')})"
    return "fixture"


def _compact_counts(counts: dict[str, Any]) -> str:
    if not counts:
        return ""
    return ", ".join(f"{key}:{value}" for key, value in counts.items())


def _parse_scenario_specs(values: list[str]) -> list[Scenario]:
    scenarios = []
    for value in values:
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError("--scenario must use name:time_proximity_seconds:similarity_threshold")
        scenarios.append(Scenario(parts[0], int(parts[1]), float(parts[2])))
    return scenarios


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare SkySort grouping settings and emit DB-backed diagnostics.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", type=Path)
    source.add_argument("--db", type=Path)
    parser.add_argument("--job-id")
    parser.add_argument("--scenario", action="append", default=[], help="Scenario as name:time_proximity_seconds:similarity_threshold. Repeatable.")
    parser.add_argument("--output-dir", type=Path, default=Path("var/tmp"))
    parser.add_argument("--stem", default="grouping-validation")
    parser.add_argument("--rescore-technical", action="store_true", help="Recompute technical metrics from DB photo paths without writing them back.")
    parser.add_argument("--write-fixture", action="store_true", help="When --db is used, also write the generated fixture JSON.")
    args = parser.parse_args()

    scenarios = _parse_scenario_specs(args.scenario)
    fixture = (
        load_fixture_from_db(args.db, job_id=args.job_id, scenarios=scenarios or None, rescore_technical=args.rescore_technical)
        if args.db
        else json.loads(args.fixture.read_text(encoding="utf-8"))
    )
    report = build_validation_report(fixture)
    paths = write_report(report, args.output_dir, stem=args.stem)
    if args.write_fixture:
        paths["fixture"] = write_fixture(fixture, args.output_dir, stem=f"{args.stem}-fixture")
    print(json.dumps(paths, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
