import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { StatGrid } from "@/components/stat-grid";
import { useAIHealth, useImportJob } from "@/features/import/use-import";
import { storeJobId } from "@/hooks/use-job-id";

export function ImportRoute() {
  const navigate = useNavigate();
  const [rootPath, setRootPath] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [reuseCache, setReuseCache] = useState(true);
  const health = useAIHealth();
  const importJob = useImportJob();

  const healthSummary = useMemo(
    () => [
      { label: "Reachable", value: health.data?.reachable ? "YES" : "NO" },
      { label: "Model", value: health.data?.configured_model ?? "n/a" },
      { label: "Vision", value: health.data?.vision_capable ? "OK" : "WAIT" },
    ],
    [health.data],
  );

  return (
    <>
      <Hero
        title="Burst intake with local AI preflight."
        copy="取り込み前に LM Studio 疎通を確認し、そのまま解析を起動します。MVP ではパス入力を正本にし、フォルダ選択ダイアログには依存しません。"
        badge="Phase 1 Intake"
        right={<StatGrid items={healthSummary} />}
      />

      <Panel title="Import Folder" copy="ARW / JPEG / PNG を対象に再帰走査します。">
        <div className="field-grid">
          <div className="field">
            <label htmlFor="rootPath">Root Path</label>
            <input id="rootPath" value={rootPath} onChange={(event) => setRootPath(event.target.value)} placeholder="/Volumes/photo-burst/2026-03-25" />
          </div>
          <div className="field">
            <label htmlFor="recursive">Recursive</label>
            <select id="recursive" value={String(recursive)} onChange={(event) => setRecursive(event.target.value === "true")}>
              <option value="true">Enabled</option>
              <option value="false">Disabled</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="reuseCache">Reuse Cache</label>
            <select id="reuseCache" value={String(reuseCache)} onChange={(event) => setReuseCache(event.target.value === "true")}>
              <option value="true">Enabled</option>
              <option value="false">Disabled</option>
            </select>
          </div>
        </div>
        <div className="actions" style={{ marginTop: 20 }}>
          <button
            className="button"
            type="button"
            disabled={!rootPath || importJob.isPending || !health.data?.reachable}
            onClick={async () => {
              const response = await importJob.mutateAsync({
                rootPath,
                recursive,
                reuseCache,
                fileTypes: [".arw", ".jpg", ".jpeg", ".png"],
              });
              storeJobId(response.job_id);
              navigate(`/progress?job=${response.job_id}`);
            }}
          >
            Start Analysis
          </button>
          {importJob.error ? <span className="pill">{String(importJob.error)}</span> : null}
        </div>
      </Panel>

      <Panel title="AI Health" copy="解析開始前の必須チェックです。未起動ならここで止めます。">
        <div className="score-row">
          <span className={`pill`}>{health.data?.reachable ? "reachable" : "offline"}</span>
          <span className="pill">{health.data?.configured_model_exists ? "model ready" : "model missing"}</span>
          <span className="pill">{health.data?.structured_json_capable ? "json mode" : "json uncertain"}</span>
        </div>
        {health.data?.error_detail ? <p className="panel-copy">{health.data.error_detail}</p> : null}
      </Panel>
    </>
  );
}
