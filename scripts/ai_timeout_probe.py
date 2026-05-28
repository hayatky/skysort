from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def build_timeout_probe_report(
    db_path: Path,
    *,
    diagnostics_path: Path | None = None,
    job_id: str | None = None,
    limit: int = 10,
    phase: str | None = None,
    execute: bool = False,
    allow_remote_ai_probe: bool = False,
    timeout_seconds: float | None = None,
    payload_mode: str = "stored",
) -> dict[str, Any]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        resolved_job_id = job_id or _latest_job_id(connection)
        if resolved_job_id is None:
            raise ValueError("no jobs found in database")
        rows = _sample_ai_responses(connection, resolved_job_id, limit=limit, phase=phase)
        photo_paths = _photo_paths(connection, resolved_job_id)
        photo_records = _photo_records(connection, resolved_job_id) if payload_mode == "current" else {}
        technical_scores = _technical_score_totals(connection, resolved_job_id) if payload_mode == "current" else {}

    baseline = _baseline_timeout(diagnostics_path)
    cases = []
    for row in rows:
        case = _case_from_row(row)
        case["payload_mode"] = payload_mode
        if payload_mode == "current":
            case["request_payload"] = _build_current_payload(case, photo_paths, photo_records, technical_scores)
        case["replayable"] = _can_restore_payload(case, photo_paths)
        cases.append(case)

    if execute:
        for case in cases:
            if not case["replayable"]:
                case["probe_status"] = "not_replayable"
                continue
            case.update(
                _execute_case(
                    case,
                    photo_paths,
                    allow_remote_ai_probe=allow_remote_ai_probe,
                    timeout_seconds=timeout_seconds,
                )
            )
    executed = [case for case in cases if case.get("probe_status") not in {None, "not_replayable"}]
    timeout_count = sum(1 for case in executed if case.get("probe_status") == "timeout")
    json_schema_failure_count = sum(1 for case in executed if _is_json_schema_failure(case))
    timeout_rate = round(timeout_count / len(executed), 4) if executed else None
    json_schema_failure_rate = round(json_schema_failure_count / len(executed), 4) if executed else None
    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "job_id": resolved_job_id,
        "execute": execute,
        "payload_mode": payload_mode,
        "timeout_seconds_override": timeout_seconds,
        "baseline": baseline,
        "summary": {
            "sample_count": len(cases),
            "replayable_count": sum(1 for case in cases if case.get("replayable")),
            "executed_count": len(executed),
            "timeout_count": timeout_count,
            "timeout_rate": timeout_rate,
            "json_schema_failure_count": json_schema_failure_count,
            "json_schema_failure_rate": json_schema_failure_rate,
            "improved_vs_baseline": (timeout_rate is not None and baseline.get("timeout_rate") is not None and timeout_rate < baseline["timeout_rate"]),
        },
        "cases": cases,
    }


def write_reports(report: dict[str, Any], output_dir: Path, stem: str = "ai-timeout-probe") -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _sample_ai_responses(connection: sqlite3.Connection, job_id: str, *, limit: int, phase: str | None) -> list[sqlite3.Row]:
    phase_clause = "and phase = ?" if phase else ""
    params: list[Any] = [job_id]
    if phase:
        params.append(phase)
    params.append(max(1, limit))
    return list(
        connection.execute(
            f"""
            select id, phase, response_status, request_payload, target_photo_ids_json, latency_ms
            from ai_responses
            where job_id = ? and request_payload is not null {phase_clause}
            order by
              case when response_status = 'ai_eval_failed' then 0 else 1 end,
              latency_ms desc,
              requested_at asc
            limit ?
            """,
            params,
        )
    )


def _photo_paths(connection: sqlite3.Connection, job_id: str) -> dict[str, Path]:
    rows = connection.execute(
        """
        select id, coalesce(preview_path, file_path) as path
        from photos
        where job_id = ?
        """,
        (job_id,),
    ).fetchall()
    return {str(row["id"]): Path(str(row["path"])) for row in rows if row["path"]}


def _photo_records(connection: sqlite3.Connection, job_id: str) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        select id, capture_time
        from photos
        where job_id = ?
        """,
        (job_id,),
    ).fetchall()
    return {str(row["id"]): {"capture_time": row["capture_time"]} for row in rows}


def _technical_score_totals(connection: sqlite3.Connection, job_id: str) -> dict[str, float]:
    rows = connection.execute(
        """
        select photo_id, technical_score_total
        from technical_scores
        where job_id = ?
        """,
        (job_id,),
    ).fetchall()
    return {str(row["photo_id"]): float(row["technical_score_total"]) for row in rows}


def _case_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "ai_response_id": row["id"],
        "phase": row["phase"],
        "prior_status": row["response_status"],
        "prior_latency_ms": row["latency_ms"],
        "target_photo_ids": _json_string_list(row["target_photo_ids_json"]),
        "request_payload": _json_object(row["request_payload"]),
    }


def _build_current_payload(
    case: dict[str, Any],
    photo_paths: dict[str, Path],
    photo_records: dict[str, dict[str, Any]],
    technical_scores: dict[str, float],
) -> dict[str, Any]:
    from skysort_api.infra.ai_client import json_schema_response_format
    from skysort_api.infra.image_tools import build_contact_sheet_data_url, build_data_url
    from skysort_api.infra.prompt_store import load_prompt
    from skysort_api.infra.settings import get_settings
    from skysort_api.services.analysis_service import GROUP_COMPARE_RESPONSE_SCHEMA, SINGLE_IMAGE_RESPONSE_SCHEMA

    settings = get_settings()
    phase = str(case.get("phase"))
    photo_ids = [photo_id for photo_id in case.get("target_photo_ids", []) if photo_id in photo_paths]
    if phase == "group_compare" and photo_ids:
        prompt, _prompt_hash = load_prompt("group_compare_v1")
        sheet_items = [(photo_id, photo_paths[photo_id]) for photo_id in photo_ids]
        contact_sheet_url, label_map = build_contact_sheet_data_url(sheet_items, settings.compare_preview_size, settings.preview_jpeg_quality)
        label_map_text = "\n".join(f"{label}: {photo_id}" for label, photo_id in label_map.items())
        text = prompt.replace("{{ candidate_photo_ids }}", ", ".join(photo_ids)).replace("{{ label_photo_id_map }}", label_map_text)
        return {
            "model": settings.ai_model_name,
            "max_tokens": settings.ai_max_tokens,
            "response_format": json_schema_response_format("group_compare_review", GROUP_COMPARE_RESPONSE_SCHEMA),
            "messages": [{"role": "user", "content": [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": contact_sheet_url}}]}],
        }
    if phase == "single" and len(photo_ids) == 1:
        photo_id = photo_ids[0]
        prompt, _prompt_hash = load_prompt("single_image_v1")
        text = (
            prompt.replace("{{ photo_id }}", photo_id)
            .replace("{{ technical_score_total }}", str(technical_scores.get(photo_id, 0)))
            .replace("{{ capture_time }}", str(photo_records.get(photo_id, {}).get("capture_time") or ""))
        )
        return {
            "model": settings.ai_model_name,
            "max_tokens": settings.ai_max_tokens,
            "response_format": json_schema_response_format("single_image_review", SINGLE_IMAGE_RESPONSE_SCHEMA),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image_url", "image_url": {"url": build_data_url(photo_paths[photo_id], max_side=settings.preview_size)}},
                    ],
                }
            ],
        }
    return dict(case.get("request_payload") or {})


def _can_restore_payload(case: dict[str, Any], photo_paths: dict[str, Path]) -> bool:
    if not case.get("request_payload"):
        return False
    target_ids = case.get("target_photo_ids") or []
    return bool(target_ids) and all(photo_id in photo_paths and photo_paths[photo_id].exists() for photo_id in target_ids)


def _execute_case(
    case: dict[str, Any],
    photo_paths: dict[str, Path],
    *,
    allow_remote_ai_probe: bool,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    import httpx

    from skysort_api.infra.ai_client import VisionLanguageModelClient

    client = VisionLanguageModelClient()
    if timeout_seconds is not None:
        client.settings = client.settings.model_copy(update={"ai_timeout_seconds": timeout_seconds})
    if not _is_localhost_url(client.settings.ai_base_url) and not allow_remote_ai_probe:
        return {
            "probe_status": "remote_ai_blocked",
            "probe_latency_ms": 0,
            "error": "AI timeout probe execution is blocked unless ai_base_url is localhost or --allow-remote-ai-probe is set.",
        }
    payload = _restore_payload_images(dict(case["request_payload"]), str(case["phase"]), list(case["target_photo_ids"]), photo_paths)
    started = time.perf_counter()
    try:
        result = client.evaluate(str(case["phase"]), payload)
    except httpx.TimeoutException as exc:
        return {"probe_status": "timeout", "probe_latency_ms": int((time.perf_counter() - started) * 1000), "error": str(exc)}
    except Exception as exc:
        return {"probe_status": "error", "probe_latency_ms": int((time.perf_counter() - started) * 1000), "error": str(exc)}
    normalized = None
    if result.parsed_json is not None:
        from skysort_api.services.analysis_service import normalize_and_validate_ai_payload

        normalized = normalize_and_validate_ai_payload(str(case["phase"]), result.parsed_json, list(case["target_photo_ids"]))
    schema_valid = normalized is not None
    details: dict[str, Any] = {}
    if result.parsed_json is None or not schema_valid:
        details["raw_response_excerpt"] = _excerpt(result.raw_response_text)
    if result.parsed_json is not None and not schema_valid:
        details["parsed_payload"] = result.parsed_json
    return {
        "probe_status": result.status,
        "probe_latency_ms": result.latency_ms,
        "parsed_json": result.parsed_json is not None,
        "schema_valid": schema_valid,
        **details,
    }


def _restore_payload_images(payload: dict[str, Any], phase: str, target_photo_ids: list[str], photo_paths: dict[str, Path]) -> dict[str, Any]:
    from skysort_api.infra.image_tools import build_contact_sheet_data_url, build_data_url
    from skysort_api.infra.settings import get_settings

    settings = get_settings()
    if phase == "group_compare":
        items = [(photo_id, photo_paths[photo_id]) for photo_id in target_photo_ids]
        data_url, _mapping = build_contact_sheet_data_url(items, settings.compare_preview_size, settings.preview_jpeg_quality)
        image_urls = [data_url]
    else:
        image_urls = [build_data_url(photo_paths[photo_id], max_side=settings.compare_preview_size) for photo_id in target_photo_ids]
    image_index = 0
    messages = []
    for message in payload.get("messages", []):
        if not isinstance(message, dict):
            continue
        restored_message = dict(message)
        content = []
        for item in restored_message.get("content", []):
            if isinstance(item, dict) and item.get("image_ref"):
                if image_index < len(image_urls):
                    content.append({"type": "image_url", "image_url": {"url": image_urls[image_index]}})
                    image_index += 1
                continue
            content.append(item)
        restored_message["content"] = content
        messages.append(restored_message)
    payload["messages"] = messages
    return payload


def _baseline_timeout(diagnostics_path: Path | None) -> dict[str, Any]:
    if diagnostics_path is None:
        return {"timeout_count": None, "response_count": None, "timeout_rate": None}
    diagnostics = _json_object(diagnostics_path.read_text(encoding="utf-8"))
    ai = diagnostics.get("ai_evaluation") or {}
    response_count = int(ai.get("response_count") or 0)
    timeout_count = int(ai.get("timeout_count") or 0)
    return {
        "timeout_count": timeout_count,
        "response_count": response_count,
        "timeout_rate": round(timeout_count / response_count, 4) if response_count else None,
    }


def _latest_job_id(connection: sqlite3.Connection) -> str | None:
    row = connection.execute("select id from jobs order by coalesce(finished_at, updated_at, started_at) desc, id desc limit 1").fetchone()
    return str(row["id"]) if row else None


def _is_json_schema_failure(case: dict[str, Any]) -> bool:
    if case.get("probe_status") in {"timeout", "not_replayable", "remote_ai_blocked"}:
        return False
    if case.get("probe_status") in {"error", "ai_eval_failed"}:
        return True
    if case.get("parsed_json") is False:
        return True
    if case.get("schema_valid") is False:
        return True
    return False


def _excerpt(value: str, *, limit: int = 800) -> str:
    normalized = " ".join(value.split())
    return normalized[:limit] + ("..." if len(normalized) > limit else "")


def _is_localhost_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _json_object(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_string_list(payload: str | None) -> list[str]:
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, str)] if isinstance(parsed, list) else []


def _markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    baseline = report.get("baseline", {})
    lines = [
        "# SkySort AI Timeout Probe",
        "",
        f"- generated_at: {report.get('generated_at')}",
        f"- job_id: {report.get('job_id')}",
        f"- execute: {report.get('execute')}",
        f"- payload_mode: {report.get('payload_mode')}",
        f"- timeout_seconds_override: {report.get('timeout_seconds_override')}",
        f"- baseline_timeout_rate: {baseline.get('timeout_rate')}",
        f"- sample_count: {summary.get('sample_count')}",
        f"- replayable_count: {summary.get('replayable_count')}",
        f"- executed_count: {summary.get('executed_count')}",
        f"- timeout_count: {summary.get('timeout_count')}",
        f"- timeout_rate: {summary.get('timeout_rate')}",
        f"- json_schema_failure_count: {summary.get('json_schema_failure_count')}",
        f"- json_schema_failure_rate: {summary.get('json_schema_failure_rate')}",
        f"- improved_vs_baseline: {summary.get('improved_vs_baseline')}",
        "",
        "## Cases",
        "",
        "| id | phase | prior | replayable | probe status | latency ms |",
        "|---|---|---|---|---|---:|",
    ]
    for case in report.get("cases", []):
        lines.append(
            f"| {case.get('ai_response_id')} | {case.get('phase')} | {case.get('prior_status')} | {case.get('replayable')} | {case.get('probe_status', '-')} | {case.get('probe_latency_ms', '')} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe stored SkySort AI payloads with the current AI timeout setting.")
    parser.add_argument("--db", type=Path, default=Path("var/data/skysort.db"))
    parser.add_argument("--diagnostics", type=Path, default=None)
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--phase", choices=["single", "group_compare"], default=None)
    parser.add_argument("--execute", action="store_true", help="Actually send replayable payloads to the configured AI endpoint.")
    parser.add_argument("--allow-remote-ai-probe", action="store_true", help="Permit --execute against a non-localhost AI endpoint.")
    parser.add_argument("--timeout-seconds", type=float, default=None, help="Probe-only AI timeout override. Does not persist app settings.")
    parser.add_argument("--payload-mode", choices=["stored", "current"], default="stored", help="Use stored request payloads or rebuild payloads with current prompt/schema/image shape.")
    parser.add_argument("--output-dir", type=Path, default=Path("var/tmp"))
    parser.add_argument("--stem", default="ai-timeout-probe")
    args = parser.parse_args()

    report = build_timeout_probe_report(
        args.db,
        diagnostics_path=args.diagnostics,
        job_id=args.job_id,
        limit=args.limit,
        phase=args.phase,
        execute=args.execute,
        allow_remote_ai_probe=args.allow_remote_ai_probe,
        timeout_seconds=args.timeout_seconds,
        payload_mode=args.payload_mode,
    )
    print(json.dumps(write_reports(report, args.output_dir, stem=args.stem), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
