import { Link, useNavigate } from "react-router-dom";

import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { StatGrid } from "@/components/stat-grid";
import { useProjects, useStartProjectAnalysis } from "@/features/projects/use-projects";

export function ProjectsRoute() {
  const projects = useProjects();
  const startAnalysis = useStartProjectAnalysis();
  const navigate = useNavigate();

  return (
    <>
      <Hero
        title="Projects"
        right={<Link className="button" to="/import">Import Folder</Link>}
      />

      <Panel title="Recent Projects" copy="Server-backed projects keep their jobs and progress after navigation or reload.">
        {projects.data?.items.length ? (
          <div className="grid">
            {projects.data.items.map((project) => {
              const latest = project.latest_job;
              const canRetry = latest?.status === "failed" || latest?.status === "canceled";
              const canOpen = Boolean(latest?.job_id);
              return (
                <div key={project.project_id} className="list-card">
                  <header style={{ marginTop: 0 }}>
                    <div>
                      <strong>{project.name}</strong>
                      <p className="panel-copy">{project.root_path}</p>
                    </div>
                    <span className="pill">{latest?.status ?? "no jobs"}</span>
                  </header>
                  <div className="progress-bar" aria-label={`${latest?.percent ?? 0}% complete`}>
                    <span style={{ width: `${latest?.percent ?? 0}%` }} />
                  </div>
                  <StatGrid
                    items={[
                      { label: "Stage", value: latest?.active_stage_label ?? "Not analyzed" },
                      { label: "Files", value: latest?.total_files ?? 0 },
                      { label: "Progress", value: `${latest?.percent ?? 0}%` },
                    ]}
                  />
                  <div className="actions" style={{ marginTop: 12 }}>
                    {canOpen ? <Link className="button" to={`/progress?job=${latest!.job_id}`}>Open Progress</Link> : null}
                    {canOpen ? <Link className="button secondary" to={`/groups?job=${latest!.job_id}`}>Open Groups</Link> : null}
                    <button
                      className="button secondary"
                      type="button"
                      disabled={startAnalysis.isPending || latest?.status === "running" || latest?.status === "canceling"}
                      onClick={async () => {
                        const response = await startAnalysis.mutateAsync(project.project_id);
                        navigate(`/progress?job=${response.job_id}`);
                      }}
                    >
                      {canRetry ? "Retry Project" : "Analyze Again"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="empty">
            No projects yet. <Link to="/import">Import a folder</Link>
          </div>
        )}
      </Panel>
    </>
  );
}
