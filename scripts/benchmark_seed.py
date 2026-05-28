from __future__ import annotations

import argparse
import html
import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CandidatePhoto:
    photo_id: str
    file_path: str
    relative_path: str
    thumb_path: str | None
    preview_path: str | None
    rating: int | None
    selection_status: str
    pick_flag: bool
    best_cut_flag: bool
    candidate_quality_score: float | None = None
    reject_risk_score: float | None = None


@dataclass(frozen=True)
class CandidateGroup:
    group_id: str
    group_size: int
    queue_hint: str
    photos: list[CandidatePhoto]


def build_expectation_draft(
    db_path: Path,
    *,
    job_id: str | None = None,
    root: Path | None = None,
    limit: int = 20,
    score_fixture_path: Path | None = None,
) -> dict[str, Any]:
    score_overrides = _score_overrides(score_fixture_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        resolved_job_id = job_id or _latest_job_id(connection)
        if resolved_job_id is None:
            raise ValueError("no jobs found in database")
        root_path = root or _job_root(connection, resolved_job_id)
        candidates = _candidate_groups(connection, resolved_job_id, root_path, limit, score_overrides)
    return {
        "schema_version": "v1",
        "human_verified": False,
        "description": "Draft generated from current SkySort results. Review each burst visually before treating expected_best, expected_reject, or expected_pick as ground truth.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "db_path": str(db_path),
            "job_id": resolved_job_id,
            "root": str(root_path) if root_path else None,
            "score_fixture": str(score_fixture_path) if score_fixture_path else None,
        },
        "groups": [_candidate_to_expectation(item) for item in candidates],
    }


def write_draft(draft: dict[str, Any], output: Path) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output)


def write_review_html(draft: dict[str, Any], output: Path) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_review_html(draft), encoding="utf-8")
    return str(output)


def strip_review_items(draft: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(draft)
    source = sanitized.get("source")
    if isinstance(source, dict):
        sanitized["source"] = {
            key: value
            for key, value in source.items()
            if key not in {"db_path", "root"}
        }
    sanitized["groups"] = [
        {key: value for key, value in group.items() if key != "review_items"}
        for group in draft.get("groups", [])
        if isinstance(group, dict)
    ]
    return sanitized


def _latest_job_id(connection: sqlite3.Connection) -> str | None:
    row = connection.execute("select id from jobs order by updated_at desc limit 1").fetchone()
    return str(row["id"]) if row else None


def _job_root(connection: sqlite3.Connection, job_id: str) -> Path | None:
    row = connection.execute("select root_path from jobs where id = ?", (job_id,)).fetchone()
    return Path(str(row["root_path"])) if row and row["root_path"] else None


def _candidate_groups(
    connection: sqlite3.Connection,
    job_id: str,
    root: Path | None,
    limit: int,
    score_overrides: dict[str, dict[str, Any]],
) -> list[CandidateGroup]:
    rows = connection.execute(
        """
        select
          g.id,
          g.group_size,
          g.merge_suggested,
          g.stale_flag,
          sum(case when pe.evaluation_status = 'ai_eval_failed' then 1 else 0 end) as ai_failed_count,
          sum(case when pe.selection_status = 'rejected' or pe.rating = 1 then 1 else 0 end) as reject_count,
          sum(case when pe.pick_flag = 1 then 1 else 0 end) as pick_count,
          sum(case when pe.best_cut_flag = 1 then 1 else 0 end) as best_count
        from groups g
        join group_members gm on gm.group_id = g.id
        left join photo_evaluations pe on pe.photo_id = gm.photo_id and pe.job_id = g.job_id and pe.is_current = 1
        where g.job_id = ?
        group by g.id
        order by
          case
            when g.group_size >= 7 then 0
            when g.merge_suggested = 1 then 1
            when ai_failed_count > 0 then 2
            when reject_count > 0 then 3
            when g.group_size between 3 and 6 then 4
            else 5
          end,
          g.group_size desc,
          g.created_at asc
        limit ?
        """,
        (job_id, max(1, limit)),
    ).fetchall()
    return [
        CandidateGroup(
            group_id=str(row["id"]),
            group_size=int(row["group_size"]),
            queue_hint=_queue_hint(row),
            photos=_candidate_photos(connection, str(row["id"]), job_id, root, score_overrides),
        )
        for row in rows
    ]


def _candidate_photos(
    connection: sqlite3.Connection,
    group_id: str,
    job_id: str,
    root: Path | None,
    score_overrides: dict[str, dict[str, Any]],
) -> list[CandidatePhoto]:
    rows = connection.execute(
        """
        select
          p.id as photo_id,
          p.file_path,
          p.thumb_path,
          p.preview_path,
          pe.rating,
          pe.selection_status,
          pe.pick_flag,
          pe.best_cut_flag
        from group_members gm
        join photos p on p.id = gm.photo_id
        left join photo_evaluations pe on pe.photo_id = p.id and pe.job_id = ? and pe.is_current = 1
        where gm.group_id = ?
        order by gm.sort_order
        """,
        (job_id, group_id),
    ).fetchall()
    photos = []
    for row in rows:
        photo_id = str(row["photo_id"])
        score = score_overrides.get(photo_id)
        rating = int(row["rating"]) if row["rating"] is not None else None
        selection_status = str(row["selection_status"] or "normal")
        pick_flag = bool(row["pick_flag"])
        best_cut_flag = bool(row["best_cut_flag"])
        candidate_quality_score = None
        reject_risk_score = None
        if score is not None:
            candidate_quality_score = _optional_float(score.get("candidate_quality_score") if score.get("candidate_quality_score") is not None else score.get("technical_score_total"))
            reject_risk_score = _optional_float(score.get("reject_risk_score"))
            rating, selection_status = _rating_from_score(candidate_quality_score, reject_risk_score)
            pick_flag = selection_status != "rejected" and rating is not None and rating >= 4
            best_cut_flag = False
        photos.append(
            CandidatePhoto(
                photo_id=photo_id,
                file_path=str(row["file_path"]),
                relative_path=_relative_path(str(row["file_path"]), root),
                thumb_path=str(row["thumb_path"]) if row["thumb_path"] else None,
                preview_path=str(row["preview_path"]) if row["preview_path"] else None,
                rating=rating,
                selection_status=selection_status,
                pick_flag=pick_flag,
                best_cut_flag=best_cut_flag,
                candidate_quality_score=candidate_quality_score,
                reject_risk_score=reject_risk_score,
            )
        )
    if score_overrides:
        best = max(
            (photo for photo in photos if photo.selection_status != "rejected"),
            key=lambda photo: (photo.candidate_quality_score if photo.candidate_quality_score is not None else -1.0, photo.rating or 0),
            default=None,
        )
        if best is not None:
            photos = [
                replace(photo, best_cut_flag=photo.photo_id == best.photo_id, pick_flag=photo.pick_flag or photo.photo_id == best.photo_id)
                for photo in photos
            ]
    return photos


def _candidate_to_expectation(group: CandidateGroup) -> dict[str, Any]:
    expected_best = next((photo.relative_path for photo in group.photos if photo.best_cut_flag), None)
    expected_reject = [photo.relative_path for photo in group.photos if photo.selection_status == "rejected" or photo.rating == 1]
    expected_pick = [photo.relative_path for photo in group.photos if photo.pick_flag]
    return {
        "name": group.group_id,
        "match": {
            "group_id": group.group_id,
            "relative_paths": [photo.relative_path for photo in group.photos],
        },
        "expected_best": expected_best,
        "expected_reject": expected_reject,
        "expected_pick": expected_pick,
        "review_items": [
            {
                "photo_id": photo.photo_id,
                "relative_path": photo.relative_path,
                "file_path": photo.file_path,
                "thumb_path": photo.thumb_path,
                "preview_path": photo.preview_path,
                "rating": photo.rating,
                "selection_status": photo.selection_status,
                "pick_flag": photo.pick_flag,
                "best_cut_flag": photo.best_cut_flag,
                "candidate_quality_score": photo.candidate_quality_score,
                "reject_risk_score": photo.reject_risk_score,
            }
            for photo in group.photos
        ],
        "notes": f"Draft candidate: {group.group_size} photos; queue_hint={group.queue_hint}; verify visually before use.",
    }


def _score_overrides(score_fixture_path: Path | None) -> dict[str, dict[str, Any]]:
    if score_fixture_path is None:
        return {}
    fixture = json.loads(score_fixture_path.read_text(encoding="utf-8"))
    scores = fixture.get("technical_scores", [])
    if not isinstance(scores, list):
        return {}
    return {
        str(score["photo_id"]): score
        for score in scores
        if isinstance(score, dict) and score.get("photo_id")
    }


def _rating_from_score(candidate_quality_score: float | None, reject_risk_score: float | None) -> tuple[int | None, str]:
    if reject_risk_score is not None and reject_risk_score >= 78.0:
        return None, "rejected"
    total = candidate_quality_score if candidate_quality_score is not None else 0.0
    if total < 22.0:
        return None, "rejected"
    if total < 42.0:
        return 1, "normal"
    if total < 58.0:
        return 2, "normal"
    if total < 74.0:
        return 3, "normal"
    if total < 83.0:
        return 4, "normal"
    return 5, "normal"


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _queue_hint(row: sqlite3.Row) -> str:
    if bool(row["merge_suggested"]):
        return "merge_suggested"
    if int(row["ai_failed_count"] or 0) > 0:
        return "ai_failed"
    if int(row["reject_count"] or 0) > 0:
        return "reject_candidate"
    if int(row["group_size"]) == 1:
        return "singleton"
    if int(row["group_size"]) >= 7:
        return "large_burst"
    if bool(row["stale_flag"]):
        return "stale"
    return "representative"


def _relative_path(file_path: str, root: Path | None) -> str:
    if root is None:
        return file_path
    try:
        return Path(file_path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return file_path


def _review_html(draft: dict[str, Any]) -> str:
    groups = draft.get("groups", [])
    lines = [
        "<!doctype html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        f"<title>{html.escape(str(draft.get('source', {}).get('job_id', 'SkySort')))} Benchmark Draft</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:24px;background:#f6f7f4;color:#182127}",
        "h1{font-size:22px;margin:0 0 8px}.meta{color:#62706c;font-size:13px;margin-bottom:18px}",
        ".group{border:1px solid #d8ddd7;border-radius:8px;background:white;margin:0 0 16px;padding:12px}",
        ".head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}",
        ".strip{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px}",
        ".photo{flex:0 0 150px;border:1px solid #d8ddd7;border-radius:8px;padding:6px;background:#fbfcfa}",
        ".photo.best{outline:3px solid #2f7d63}.photo.reject{opacity:.58}.photo.pick{border-color:#2f7d63}",
        "img{width:100%;height:100px;object-fit:cover;border-radius:6px;background:#e8ece8}",
        ".name{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:4px}",
        ".tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}.tag{font-size:11px;border:1px solid #d8ddd7;border-radius:999px;padding:2px 6px;background:#f0f3ef}",
        "code{font-size:12px}",
        "</style>",
        "</head>",
        "<body>",
        "<h1>SkySort Benchmark Draft</h1>",
        f"<div class=\"meta\">Generated {html.escape(str(draft.get('generated_at', '')))} from {html.escape(str(draft.get('source', {})))}. Verify visually before using as ground truth.</div>",
    ]
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        expected_best = str(group.get("expected_best") or "")
        expected_reject = set(_string_list(group.get("expected_reject")))
        expected_pick = set(_string_list(group.get("expected_pick")))
        lines.extend(
            [
                "<section class=\"group\">",
                "<div class=\"head\">",
                f"<div><strong>{html.escape(str(group.get('name', 'unnamed')))}</strong><div class=\"meta\">{html.escape(str(group.get('notes', '')))}</div></div>",
                f"<code>best={html.escape(expected_best or '-')}</code>",
                "</div>",
                "<div class=\"strip\">",
            ]
        )
        for item in group.get("review_items", []):
            if not isinstance(item, dict):
                continue
            relative_path = str(item.get("relative_path") or "")
            classes = ["photo"]
            if relative_path == expected_best:
                classes.append("best")
            if relative_path in expected_reject:
                classes.append("reject")
            if relative_path in expected_pick:
                classes.append("pick")
            image_src = _image_src(item)
            lines.extend(
                [
                    f"<article class=\"{' '.join(classes)}\">",
                    f"<img src=\"{html.escape(image_src)}\" alt=\"{html.escape(relative_path)}\">",
                    f"<div class=\"name\" title=\"{html.escape(relative_path)}\">{html.escape(relative_path)}</div>",
                    "<div class=\"tags\">",
                    f"<span class=\"tag\">rating {html.escape(str(item.get('rating') if item.get('rating') is not None else '-'))}</span>",
                    f"<span class=\"tag\">{html.escape(str(item.get('selection_status') or 'normal'))}</span>",
                    "<span class=\"tag\">best</span>" if item.get("best_cut_flag") else "",
                    "<span class=\"tag\">pick</span>" if item.get("pick_flag") else "",
                    "</div>",
                    "</article>",
                ]
            )
        lines.extend(["</div>", "</section>"])
    lines.extend(["</body>", "</html>"])
    return "\n".join(line for line in lines if line != "")


def _image_src(item: dict[str, Any]) -> str:
    for key in ("thumb_path", "preview_path", "file_path"):
        value = item.get(key)
        if not value:
            continue
        path = Path(str(value))
        if path.exists():
            return path.resolve().as_uri()
    return ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a human-review benchmark expectation draft from a SkySort SQLite DB.")
    parser.add_argument("--db", type=Path, default=Path("var/data/skysort.db"))
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--score-fixture", type=Path, default=None, help="Optional grouping diagnostics fixture with current-code technical_scores.")
    parser.add_argument("--output", type=Path, default=Path("var/tmp/benchmark-expectations-draft.json"))
    parser.add_argument("--html-output", type=Path, default=None)
    parser.add_argument("--strip-review-items", action="store_true", help="Write expectation-compatible JSON without local file review metadata.")
    args = parser.parse_args()

    draft = build_expectation_draft(args.db, job_id=args.job_id, root=args.root, limit=args.limit, score_fixture_path=args.score_fixture)
    output_draft = strip_review_items(draft) if args.strip_review_items else draft
    html_output = args.html_output or args.output.with_suffix(".html")
    print(
        json.dumps(
            {
                "output": write_draft(output_draft, args.output),
                "html": write_review_html(draft, html_output),
                "group_count": len(draft["groups"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
