import { Link, useNavigate } from "react-router-dom";

import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { StatGrid } from "@/components/stat-grid";
import { useAIHealth } from "@/features/import/use-import";
import { useCancelJob, useFailures, useProgress, useRetryJob } from "@/features/progress/use-progress";
import { useRetryFailure } from "@/features/review/use-review-actions";
import { useJobId } from "@/hooks/use-job-id";

export function ProgressRoute() {
  const jobId = useJobId();
  const navigate = useNavigate();
  const progress = useProgress(jobId);
  const failures = useFailures(jobId);
  const health = useAIHealth();
  const cancelJob = useCancelJob(jobId);
  const retryJob = useRetryJob(jobId);
  const retryFailure = useRetryFailure(jobId);
  const canCancel = progress.data?.status === "running" || progress.data?.status === "canceling";
  const canRetry = progress.data?.status === "failed" || progress.data?.status === "canceled";

  if (!jobId) {
    return (
      <>
        <Hero title="Progress" />
        <Panel title="No Job Selected" copy="Open a server-backed project to view persisted progress.">
          <Link className="button" to="/">Open Projects</Link>
        </Panel>
      </>
    );
  }

  return (
    <>
      <Hero
        title="Progress"
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
            { label: "Stage", value: progress.data?.active_stage_label ?? "Queued" },
            { label: "Overall", value: `${progress.data?.percent ?? 0}%` },
            { label: "Stage Done", value: `${progress.data?.stage_done ?? 0}/${progress.data?.stage_total ?? 0}` },
            { label: "AI Photos", value: `${progress.data?.ai_photo_done ?? 0}/${progress.data?.ai_photo_total ?? 0}` },
            { label: "AI Groups", value: `${progress.data?.ai_group_done ?? 0}/${progress.data?.ai_group_total ?? 0}` },
            { label: "Provisional", value: progress.data?.provisional_rated_files ?? 0 },
            { label: "Final", value: progress.data?.final_rated_files ?? 0 },
          ]}
        />
        <div className="progress-stack">
          <ProgressBar label="Overall" done={progress.data?.percent ?? 0} />
          <ProgressBar label="Current Stage" done={percentage(progress.data?.stage_done ?? 0, progress.data?.stage_total ?? 0)} />
          <ProgressBar label="AI Photos" done={percentage(progress.data?.ai_photo_done ?? 0, progress.data?.ai_photo_total ?? 0)} />
          <ProgressBar label="AI Groups" done={percentage(progress.data?.ai_group_done ?? 0, progress.data?.ai_group_total ?? 0)} />
        </div>
        <div className="actions" style={{ marginTop: 20 }}>
          <Link className="button" to={`/groups?job=${jobId}`}>
            Open Groups
          </Link>
          <Link className="button secondary" to={`/review?job=${jobId}`}>
            Open Review
          </Link>
          <button className="button warning" type="button" disabled={!canCancel || cancelJob.isPending} onClick={() => cancelJob.mutate()}>
            {progress.data?.status === "canceling" ? "Canceling" : "Cancel Job"}
          </button>
          <button
            className="button secondary"
            type="button"
            disabled={!canRetry || retryJob.isPending}
            onClick={async () => {
              const response = await retryJob.mutateAsync();
              navigate(`/progress?job=${response.job_id}`);
            }}
          >
            Retry Job
          </button>
        </div>
      </Panel>

      <Panel title="Failures">
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
      <Panel title="AI Health">
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

function percentage(done: number, total: number) {
  return total ? Math.round((done / total) * 100) : 0;
}

function ProgressBar({ label, done }: { label: string; done: number }) {
  const bounded = Math.min(100, Math.max(0, done));
  return (
    <div>
      <div className="progress-label">
        <span>{label}</span>
        <span>{bounded}%</span>
      </div>
      <div className="progress-bar">
        <span style={{ width: `${bounded}%` }} />
      </div>
    </div>
  );
}
