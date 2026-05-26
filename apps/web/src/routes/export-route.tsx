import { useState } from "react";

import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { useResultsExport, useXmpExport } from "@/features/export/use-export";
import { useJobId } from "@/hooks/use-job-id";

export function ExportRoute() {
  const jobId = useJobId();
  const [format, setFormat] = useState<"csv" | "json">("csv");
  const [conflictPolicy, setConflictPolicy] = useState<"skip" | "fail" | "overwrite_safe_fields">("skip");
  const xmpExport = useXmpExport();
  const resultsExport = useResultsExport();

  return (
    <>
      <Hero
        title="Dry-run first, then commit metadata writes."
        copy="ARW はサイドカー前提、JPEG は評価タグのみ保守的更新です。ExifTool 未導入時はここだけ止めます。"
        badge="Export"
      />

      <div className="grid cols-2">
        <Panel title="XMP Write-back" copy="`dry_run=true` が既定です。">
          <div className="field-grid" style={{ marginBottom: 16 }}>
            <div className="field">
              <label htmlFor="conflict_policy">Conflict Policy</label>
              <select id="conflict_policy" value={conflictPolicy} onChange={(event) => setConflictPolicy(event.target.value as "skip" | "fail" | "overwrite_safe_fields")}>
                <option value="skip">skip</option>
                <option value="fail">fail</option>
                <option value="overwrite_safe_fields">overwrite_safe_fields</option>
              </select>
            </div>
          </div>
          <div className="actions">
            <button className="button secondary" type="button" onClick={() => xmpExport.mutate({ jobId, dryRun: true, conflictPolicy })}>
              Run Dry-Run
            </button>
            <button className="button warning" type="button" onClick={() => xmpExport.mutate({ jobId, dryRun: false, conflictPolicy })}>
              Commit XMP
            </button>
          </div>
          {xmpExport.data ? (
            <div className="grid" style={{ marginTop: 20 }}>
              <div className="score-row">
                <span className="score-chip">Target {xmpExport.data.target_count}</span>
                <span className="score-chip">Writable {xmpExport.data.writable_count ?? xmpExport.data.written_count ?? 0}</span>
                <span className="score-chip">Blocked {xmpExport.data.blocked_count ?? xmpExport.data.failed_count ?? 0}</span>
                <span className="score-chip">Conflicts {xmpExport.data.conflict_count ?? xmpExport.data.conflicts?.length ?? 0}</span>
                <span className="score-chip">Skipped {xmpExport.data.skipped_count ?? xmpExport.data.skipped_items?.length ?? 0}</span>
              </div>
              {[...(xmpExport.data.write_candidates ?? []), ...(xmpExport.data.written_items ?? [])].map((item) => (
                <div key={item.photo_id} className="list-card">
                  <strong>{item.photo_id}</strong>
                  <p className="panel-copy">{item.summary}</p>
                </div>
              ))}
              {[...(xmpExport.data.blocked_items ?? []), ...(xmpExport.data.failed_items ?? []), ...(xmpExport.data.skipped_items ?? [])].map((item, index) => (
                <div key={`${item.photo_id}-${item.result_code}-${index}`} className="list-card">
                  <strong>{item.result_code ?? "blocked"}</strong>
                  <p className="panel-copy">{item.summary}</p>
                </div>
              ))}
              {xmpExport.data.conflicts?.map((item, index) => (
                <div key={`${item.result_code}-${index}`} className="list-card">
                  <strong>{item.result_code ?? "conflict"}</strong>
                  <p className="panel-copy">{item.summary}</p>
                </div>
              ))}
            </div>
          ) : null}
        </Panel>

        <Panel title="Result Export" copy="レビュー結果を CSV / JSON で持ち出します。">
          <div className="field-grid">
            <div className="field">
              <label htmlFor="format">Format</label>
              <select id="format" value={format} onChange={(event) => setFormat(event.target.value as "csv" | "json")}>
                <option value="csv">CSV</option>
                <option value="json">JSON</option>
              </select>
            </div>
          </div>
          <div className="actions" style={{ marginTop: 20 }}>
            <button className="button" type="button" onClick={() => resultsExport.mutate({ jobId, format })}>
              Export Results
            </button>
          </div>
          {resultsExport.data ? <p className="panel-copy">{resultsExport.data.export_path}</p> : null}
        </Panel>
      </div>
    </>
  );
}
