import { NavLink, useLocation } from "react-router-dom";

import { getStoredJobId } from "@/hooks/use-job-id";
import type { NavLinkItem } from "@/types/ui";

const links: NavLinkItem[] = [
  { path: "/", label: "Import" },
  { path: "/progress", label: "Progress" },
  { path: "/groups", label: "Groups" },
  { path: "/review", label: "Review" },
  { path: "/delete-candidates", label: "Delete Candidates" },
  { path: "/export", label: "Export" },
  { path: "/settings", label: "Settings" },
];

export function Sidebar() {
  const location = useLocation();
  const jobId = new URLSearchParams(location.search).get("job") ?? getStoredJobId();

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-title">SkySort</div>
      </div>
      <nav className="nav">
        {links.map((link) => (
          <NavLink
            key={link.path}
            to={
              jobId && link.path !== "/"
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
