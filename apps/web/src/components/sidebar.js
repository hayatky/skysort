import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { NavLink, useLocation } from "react-router-dom";
const links = [
    { path: "/", label: "Import" },
    { path: "/progress", label: "Progress" },
    { path: "/groups", label: "Groups" },
    { path: "/review", label: "Review" },
    { path: "/export", label: "Export" },
    { path: "/settings", label: "Settings" },
];
export function Sidebar() {
    const location = useLocation();
    const jobId = new URLSearchParams(location.search).get("job");
    return (_jsxs("aside", { className: "sidebar", children: [_jsxs("div", { className: "brand", children: [_jsx("div", { className: "brand-kicker", children: "Local Photo Culling" }), _jsx("div", { className: "brand-title", children: "SkySort" }), _jsx("div", { className: "brand-subtitle", children: "Aviation burst review cockpit for local VLM culling." })] }), _jsx("nav", { className: "nav", children: links.map((link) => (_jsx(NavLink, { to: jobId && link.path !== "/"
                    ? { pathname: link.path, search: `?job=${encodeURIComponent(jobId)}` }
                    : link.path, end: true, children: link.label }, link.path))) })] }));
}
