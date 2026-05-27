import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { useProjects } from "@/features/projects/use-projects";
import type { NavLinkItem } from "@/types/ui";

const links: NavLinkItem[] = [
  { path: "/", label: "Projects" },
  { path: "/import", label: "Import" },
  { path: "/progress", label: "Progress" },
  { path: "/groups", label: "Groups" },
  { path: "/review", label: "Review" },
  { path: "/delete-candidates", label: "Delete Candidates" },
  { path: "/export", label: "Export" },
  { path: "/settings", label: "Settings" },
];

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const projects = useProjects();
  const queryJobId = new URLSearchParams(location.search).get("job") ?? "";
  const fallbackJobId = projects.data?.items.find((project) => project.latest_job)?.latest_job?.job_id ?? "";
  const jobId = queryJobId || fallbackJobId;

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-title">SkySort</div>
      </div>
      <div className="field sidebar-project">
        <label htmlFor="project-select">Project</label>
        <select
          id="project-select"
          value={jobId}
          onChange={(event) => {
            if (event.target.value) navigate(`/progress?job=${encodeURIComponent(event.target.value)}`);
          }}
        >
          <option value="">No project</option>
          {projects.data?.items.map((project) =>
            project.latest_job ? (
              <option key={project.project_id} value={project.latest_job.job_id}>
                {project.name}
              </option>
            ) : null,
          )}
        </select>
      </div>
      <nav className="nav">
        {links.map((link) => (
          <NavLink
            key={link.path}
            to={
              jobId && !["/", "/import", "/settings"].includes(link.path)
                ? { pathname: link.path, search: `?job=${encodeURIComponent(jobId)}` }
                : link.path
            }
            end
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
