import { NavLink } from "react-router-dom";

import type { NavLinkItem } from "@/types/ui";

const links: NavLinkItem[] = [
  { path: "/", label: "Import" },
  { path: "/progress", label: "Progress" },
  { path: "/groups", label: "Groups" },
  { path: "/review", label: "Review" },
  { path: "/export", label: "Export" },
  { path: "/settings", label: "Settings" },
];

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-kicker">Local Photo Culling</div>
        <div className="brand-title">SkySort</div>
        <div className="brand-subtitle">Aviation burst review cockpit for local VLM culling.</div>
      </div>
      <nav className="nav">
        {links.map((link) => (
          <NavLink key={link.path} to={link.path} end>
            {link.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
