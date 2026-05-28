from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


def build_review_packet(
    expectations_path: Path,
    benchmark_diff_path: Path,
    acceptance_gate_path: Path,
    *,
    review_html_path: Path | None = None,
    review_montage_dir: Path | None = None,
    diagnostics_path: Path | None = None,
) -> dict[str, Any]:
    expectations = _load_json(expectations_path)
    benchmark = _load_json(benchmark_diff_path)
    acceptance = _load_json(acceptance_gate_path)
    diagnostics = _load_json(diagnostics_path) if diagnostics_path else None
    groups = expectations.get("groups", []) if isinstance(expectations.get("groups"), list) else []
    comparisons = {
        str(item.get("name")): item
        for item in benchmark.get("comparisons", [])
        if isinstance(item, dict) and item.get("name")
    }
    review_items = [
        _group_review_item(group, comparisons.get(str(group.get("name"))), review_montage_dir=review_montage_dir)
        for group in groups
        if isinstance(group, dict)
    ]
    acceptance_checks = _acceptance_checks_by_name(acceptance)
    return {
        "schema_version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "expectations": str(expectations_path),
            "benchmark_diff": str(benchmark_diff_path),
            "acceptance_gate": str(acceptance_gate_path),
            "review_html": str(review_html_path) if review_html_path else None,
            "review_montage_dir": str(review_montage_dir) if review_montage_dir else None,
            "diagnostics": str(diagnostics_path) if diagnostics_path else None,
        },
        "human_verified": bool(expectations.get("human_verified")),
        "summary": {
            "expected_group_count": len(groups),
            "benchmark_mismatch_count": int(benchmark.get("mismatch_count") or 0),
            "group_overmerged_count": int((benchmark.get("metrics") or {}).get("group_overmerged_count") or 0),
            "acceptance_summary": acceptance.get("summary", {}),
            "acceptance_checks": {name: item.get("status") for name, item in acceptance_checks.items()},
            "timeout_rate": _timeout_rate(diagnostics),
        },
        "required_human_actions": _required_human_actions(acceptance_checks),
        "groups": review_items,
    }


def write_packet(packet: dict[str, Any], output_dir: Path, stem: str = "human-review-packet") -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    html_path = output_dir / f"{stem}.html"
    json_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(packet), encoding="utf-8")
    html_path.write_text(_html_review_form(packet), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path), "html": str(html_path)}


def validate_review_packet(packet: dict[str, Any]) -> dict[str, Any]:
    groups = packet.get("groups", []) if isinstance(packet.get("groups"), list) else []
    missing_overmerge = []
    missing_subjective = []
    failed_overmerge = []
    failed_subjective = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        name = str(group.get("name") or "unnamed")
        overmerge = group.get("human_overmerge_ok")
        subjective = group.get("human_subjective_ok")
        if overmerge is None:
            missing_overmerge.append(name)
        elif overmerge is not True:
            failed_overmerge.append(name)
        if subjective is None:
            missing_subjective.append(name)
        elif subjective is not True:
            failed_subjective.append(name)
    errors = []
    if missing_overmerge:
        errors.append(f"{len(missing_overmerge)} groups are missing human_overmerge_ok")
    if missing_subjective:
        errors.append(f"{len(missing_subjective)} groups are missing human_subjective_ok")
    if failed_overmerge:
        errors.append(f"{len(failed_overmerge)} groups failed human_overmerge_ok")
    if failed_subjective:
        errors.append(f"{len(failed_subjective)} groups failed human_subjective_ok")
    return {
        "ready": not errors and bool(groups),
        "group_count": len(groups),
        "missing_overmerge_count": len(missing_overmerge),
        "missing_subjective_count": len(missing_subjective),
        "failed_overmerge_count": len(failed_overmerge),
        "failed_subjective_count": len(failed_subjective),
        "errors": errors,
    }


def apply_review_packet(packet_path: Path, expectations_path: Path, output_path: Path) -> dict[str, Any]:
    packet = _load_json(packet_path)
    validation = validate_review_packet(packet)
    if not validation["ready"]:
        raise ValueError("; ".join(validation["errors"]) or "review packet is not ready")
    expectations = _load_json(expectations_path)
    promoted = dict(expectations)
    promoted["human_verified"] = True
    promoted["human_verified_at"] = datetime.now(timezone.utc).isoformat()
    promoted["human_review_packet"] = str(packet_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(promoted, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "output": str(output_path),
        "validation": validation,
    }


def _group_review_item(group: dict[str, Any], comparison: dict[str, Any] | None, *, review_montage_dir: Path | None = None) -> dict[str, Any]:
    match = group.get("match") if isinstance(group.get("match"), dict) else {}
    issues = comparison.get("issues", []) if comparison else ["not_compared"]
    name = str(group.get("name") or match.get("group_id") or "unnamed")
    montage_path = _review_montage_path(review_montage_dir, name)
    return {
        "name": name,
        "photo_count": len(match.get("relative_paths", [])) if isinstance(match.get("relative_paths"), list) else None,
        "expected_best": group.get("expected_best"),
        "expected_reject_count": len(group.get("expected_reject", [])) if isinstance(group.get("expected_reject"), list) else 0,
        "expected_pick_count": len(group.get("expected_pick", [])) if isinstance(group.get("expected_pick"), list) else 0,
        "benchmark_issues": issues,
        "actual_group_ids": comparison.get("actual_group_ids", []) if comparison else [],
        "extra_group_photos": comparison.get("extra_group_photos", []) if comparison else [],
        "review_montage": str(montage_path) if montage_path else None,
        "human_overmerge_ok": None,
        "human_subjective_ok": None,
    }


def _review_montage_path(review_montage_dir: Path | None, group_name: str) -> Path | None:
    if review_montage_dir is None:
        return None
    path = review_montage_dir / f"{group_name}.jpg"
    return path if path.exists() else None


def _timeout_rate(diagnostics: dict[str, Any] | None) -> float | None:
    if not diagnostics:
        return None
    ai = diagnostics.get("ai_evaluation") or {}
    response_count = int(ai.get("response_count") or 0)
    timeout_count = int(ai.get("timeout_count") or 0)
    if response_count <= 0:
        return None
    return round(timeout_count / response_count, 4)


def _acceptance_checks_by_name(acceptance: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("name")): item
        for item in acceptance.get("checks", [])
        if isinstance(item, dict) and item.get("name")
    }


def _required_human_actions(acceptance_checks: dict[str, dict[str, Any]]) -> list[str]:
    actions = [
        "Open the review HTML and visually inspect every group for unrelated-scene over-merge.",
        "Edit expected_best, expected_reject, and expected_pick to match human judgement.",
        "Set human_verified=true only after every listed group is reviewed.",
        "Run benchmark_diff and acceptance_gate again after editing the expectation file.",
    ]
    timeout_status = (acceptance_checks.get("ai_timeout_rate") or {}).get("status")
    if timeout_status != "pass":
        actions.append("Run a fresh AI analysis or current-payload timeout probe with ai_timeout_seconds >= 60 and compare timeout rate against the old diagnostics.")
    return actions


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _markdown(packet: dict[str, Any]) -> str:
    summary = packet.get("summary", {})
    inputs = packet.get("inputs", {}) if isinstance(packet.get("inputs"), dict) else {}
    acceptance_checks = summary.get("acceptance_checks", {}) if isinstance(summary.get("acceptance_checks"), dict) else {}
    lines = [
        "# SkySort Human Review Packet",
        "",
        f"- generated_at: {packet.get('generated_at')}",
        f"- human_verified: {packet.get('human_verified')}",
        f"- review_html: {inputs.get('review_html')}",
        f"- review_montage_dir: {inputs.get('review_montage_dir')}",
        f"- expected_group_count: {summary.get('expected_group_count')}",
        f"- benchmark_mismatch_count: {summary.get('benchmark_mismatch_count')}",
        f"- group_overmerged_count: {summary.get('group_overmerged_count')}",
        f"- timeout_rate: {summary.get('timeout_rate')}",
        "",
        "## Acceptance Checks",
        "",
    ]
    if acceptance_checks:
        lines.extend(f"- {name}: {status}" for name, status in sorted(acceptance_checks.items()))
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
        "## Required Human Actions",
        "",
        ]
    )
    lines.extend(f"- {item}" for item in packet.get("required_human_actions", []))
    lines.extend(
        [
            "",
            "## Groups",
            "",
            "| group | photos | expected best | reject | pick | issues | extra group photos | montage |",
            "|---|---:|---|---:|---:|---|---|---|",
        ]
    )
    for group in packet.get("groups", []):
        if not isinstance(group, dict):
            continue
        lines.append(
            "| {name} | {photos} | {best} | {reject} | {pick} | {issues} | {extra} | {montage} |".format(
                name=group.get("name", ""),
                photos=group.get("photo_count", ""),
                best=group.get("expected_best") or "-",
                reject=group.get("expected_reject_count", 0),
                pick=group.get("expected_pick_count", 0),
                issues=", ".join(str(item) for item in group.get("benchmark_issues", [])) or "-",
                extra=", ".join(str(item) for item in group.get("extra_group_photos", [])) or "-",
                montage=group.get("review_montage") or "-",
            )
        )
    return "\n".join(lines) + "\n"


def _html_review_form(packet: dict[str, Any]) -> str:
    packet_json = json.dumps(packet, ensure_ascii=False)
    rows = []
    for index, group in enumerate(packet.get("groups", []) if isinstance(packet.get("groups"), list) else []):
        if not isinstance(group, dict):
            continue
        montage = str(group.get("review_montage") or "")
        montage_src = Path(montage).as_posix() if montage else ""
        rows.append(
            """
            <section class="group" data-index="{index}">
              <div class="group-head">
                <div>
                  <h2>{name}</h2>
                  <p>{photos} photos · best {best} · reject {reject} · pick {pick}</p>
                  <p class="issues">{issues}</p>
                </div>
                <div class="checks">
                  <label><input type="checkbox" data-field="human_overmerge_ok"> over-merge ok</label>
                  <label><input type="checkbox" data-field="human_subjective_ok"> subjective ok</label>
                </div>
              </div>
              {image}
              <label class="notes">review notes<textarea data-field="human_review_notes"></textarea></label>
            </section>
            """.format(
                index=index,
                name=escape(str(group.get("name") or "")),
                photos=escape(str(group.get("photo_count") or "")),
                best=escape(str(group.get("expected_best") or "-")),
                reject=escape(str(group.get("expected_reject_count") or 0)),
                pick=escape(str(group.get("expected_pick_count") or 0)),
                issues=escape(", ".join(str(item) for item in group.get("benchmark_issues", [])) or "no benchmark issues"),
                image=f'<img src="{escape(montage_src)}" alt="{escape(str(group.get("name") or ""))} montage">' if montage_src else '<p class="missing">No montage image found.</p>',
            )
        )
    safe_packet_json = packet_json.replace("</", "<\\/")
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SkySort Human Review Packet</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:24px;background:#f6f7f4;color:#182127}}
h1{{font-size:24px;margin:0 0 6px}}h2{{font-size:18px;margin:0 0 4px}}p{{margin:0 0 4px}}
.meta{{color:#62706c;font-size:13px;margin-bottom:18px}}.toolbar{{position:sticky;top:0;z-index:1;background:#f6f7f4;border-bottom:1px solid #d8ddd7;padding:10px 0;margin-bottom:16px;display:flex;gap:8px;align-items:center}}
button{{border:1px solid #9aa7a1;background:#fff;border-radius:6px;padding:8px 12px;cursor:pointer}}button.primary{{background:#2f7d63;color:#fff;border-color:#2f7d63}}
.group{{border:1px solid #d8ddd7;border-radius:8px;background:#fff;margin:0 0 18px;padding:12px}}.group-head{{display:flex;justify-content:space-between;gap:16px;margin-bottom:10px}}
.checks{{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start}}.checks label{{white-space:nowrap}}.issues{{color:#7b4b2a;font-size:13px}}
img{{max-width:100%;height:auto;border:1px solid #d8ddd7;border-radius:6px;background:#e8ece8}}.notes{{display:block;margin-top:10px;color:#62706c;font-size:12px}}
textarea{{display:block;width:100%;min-height:54px;margin-top:4px;border:1px solid #d8ddd7;border-radius:6px;font:inherit}}.missing{{color:#9a4d4d}}
</style>
</head>
<body>
<h1>SkySort Human Review Packet</h1>
<div class="meta">Check each montage before exporting a reviewed packet. Promotion still requires both checkboxes for every group.</div>
<div class="toolbar">
  <button class="primary" id="download">Download reviewed packet JSON</button>
  <span id="status"></span>
</div>
{rows}
<script type="application/json" id="packet-data">{packet_json}</script>
<script>
const packet = JSON.parse(document.getElementById('packet-data').textContent);
const statusEl = document.getElementById('status');
function updateStatus() {{
  const groups = packet.groups || [];
  const overmerge = groups.filter(group => group.human_overmerge_ok === true).length;
  const subjective = groups.filter(group => group.human_subjective_ok === true).length;
  statusEl.textContent = `${{overmerge}}/${{groups.length}} over-merge, ${{subjective}}/${{groups.length}} subjective`;
}}
for (const section of document.querySelectorAll('.group')) {{
  const index = Number(section.dataset.index);
  for (const field of section.querySelectorAll('[data-field]')) {{
    const key = field.dataset.field;
    if (field.type === 'checkbox') {{
      field.checked = packet.groups[index][key] === true;
      field.addEventListener('change', () => {{
        packet.groups[index][key] = field.checked ? true : null;
        updateStatus();
      }});
    }} else {{
      field.value = packet.groups[index][key] || '';
      field.addEventListener('input', () => {{
        packet.groups[index][key] = field.value;
      }});
    }}
  }}
}}
document.getElementById('download').addEventListener('click', () => {{
  const blob = new Blob([JSON.stringify(packet, null, 2)], {{type: 'application/json'}});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'human-review-packet.reviewed.json';
  link.click();
  URL.revokeObjectURL(url);
}});
updateStatus();
</script>
</body>
</html>
""".format(rows="\n".join(rows), packet_json=safe_packet_json)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a human review packet for final SkySort acceptance evidence.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-packet", type=Path, default=None)
    mode.add_argument("--apply-reviewed", type=Path, default=None, help="Reviewed packet JSON to promote an expectation file.")
    parser.add_argument("--expectations", type=Path, default=None)
    parser.add_argument("--benchmark-diff", type=Path, default=None)
    parser.add_argument("--acceptance-gate", type=Path, default=None)
    parser.add_argument("--review-html", type=Path, default=None)
    parser.add_argument("--review-montage-dir", type=Path, default=None)
    parser.add_argument("--diagnostics", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("var/tmp"))
    parser.add_argument("--output-expectations", type=Path, default=None)
    parser.add_argument("--stem", default="human-review-packet")
    args = parser.parse_args()

    if args.validate_packet:
        print(json.dumps(validate_review_packet(_load_json(args.validate_packet)), ensure_ascii=False, indent=2))
        return
    if args.apply_reviewed:
        if args.expectations is None or args.output_expectations is None:
            raise SystemExit("--apply-reviewed requires --expectations and --output-expectations")
        print(json.dumps(apply_review_packet(args.apply_reviewed, args.expectations, args.output_expectations), ensure_ascii=False, indent=2))
        return
    if args.expectations is None or args.benchmark_diff is None or args.acceptance_gate is None:
        raise SystemExit("--expectations, --benchmark-diff, and --acceptance-gate are required when building a packet")
    packet = build_review_packet(
        args.expectations,
        args.benchmark_diff,
        args.acceptance_gate,
        review_html_path=args.review_html,
        review_montage_dir=args.review_montage_dir,
        diagnostics_path=args.diagnostics,
    )
    print(json.dumps(write_packet(packet, args.output_dir, stem=args.stem), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
