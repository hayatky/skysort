import { Link } from "react-router-dom";

import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { StatGrid } from "@/components/stat-grid";
import { useAIHealth } from "@/features/import/use-import";
import { useFailures, useProgress } from "@/features/progress/use-progress";
import { useRetryFailure } from "@/features/review/use-review-actions";
import { useJobId } from "@/hooks/use-job-id";

export function ProgressRoute() {
  const jobId = useJobId();
  const progress = useProgress(jobId);
  const failures = useFailures(jobId);
  const health = useAIHealth();
  const retryFailure = useRetryFailure(jobId);

  return (
    <>
      <Hero
        title="Pipeline telemetry for long local runs."
        copy="ポーリングを正本にして進捗を監視します。SSE を入れても、この画面のフォールバックは変えません。"
        badge="Job Progress"
        right={
          <StatGrid
            items={[
              { label: "Stage", value: progress.data?.current_stage ?? "idle" },
              { label: "Status", value: progress.data?.status ?? "queued" },
              { label: "Failures", value: progress.data?.failed_files ?? 0 },
            ]}
          />
        }
      />

      <Panel title="Progress" copy={jobId ? `Job ${jobId}` : "No job selected"}>
        <StatGrid
          items={[
            { label: "Total", value: progress.data?.total_files ?? 0 },
            { label: "Imported", value: progress.data?.imported_files ?? 0 },
            { label: "Grouped", value: progress.data?.grouped_files ?? 0 },
            { label: "Technical", value: progress.data?.technically_scored_files ?? 0 },
            { label: "AI", value: progress.data?.semantically_scored_files ?? 0 },
            { label: "Provisional", value: progress.data?.provisional_rated_files ?? 0 },
            { label: "Final", value: progress.data?.final_rated_files ?? 0 },
          ]}
        />
        <div className="actions" style={{ marginTop: 20 }}>
          <Link className="button" to={`/groups?job=${jobId}`}>
            Open Groups
          </Link>
          <Link className="button secondary" to={`/review?job=${jobId}`}>
            Open Review
          </Link>
        </div>
      </Panel>

      <Panel title="Failures" copy="画像単位の失敗は全体停止にしません。">
        {failures.data?.items?.length ? (
          <div className="grid">
            {failures.data.items.map((item) => (
              <div key={`${item.stage}-${item.photo_id ?? item.group_id ?? item.reason}`} className="list-card">
                <strong>{item.stage}</strong>
                <p className="panel-copy">{item.file_name ?? item.photo_id ?? item.group_id ?? "job-level failure"}</p>
                <p className="panel-copy">{item.reason}</p>
                <div className="score-row">
                  {item.photo_id ? <span className="score-chip">Photo {item.photo_id}</span> : null}
                  {item.group_id ? <span className="score-chip">Group {item.group_id}</span> : null}
                  {item.reason_code ? <span className="score-chip">Reason {item.reason_code}</span> : null}
                  <span className="score-chip">Retryable {item.retryable ? "yes" : "no"}</span>
                  {item.retry_scope ? <span className="score-chip">Scope {item.retry_scope}</span> : null}
                </div>
                {item.id && item.retryable ? (
                  <div className="actions" style={{ marginTop: 12 }}>
                    <button className="button secondary" type="button" onClick={() => retryFailure.mutate(item.id!)}>
                      Retry Item
                    </button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="empty">No failures recorded.</div>
        )}
      </Panel>
      <Panel title="AI Health" copy="解析前提の LM Studio 接続状態">
        <StatGrid
          items={[
            { label: "Reachable", value: health.data?.reachable ? "YES" : "NO" },
            { label: "Model", value: health.data?.configured_model_exists ? "READY" : "MISSING" },
            { label: "Vision", value: health.data?.vision_capable ? "OK" : "NO" },
            { label: "JSON", value: health.data?.structured_json_capable ? "OK" : "NO" },
          ]}
        />
      </Panel>
    </>
  );
}
