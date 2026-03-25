import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/layout";
import { ExportRoute } from "@/routes/export-route";
import { GroupDetailRoute } from "@/routes/group-detail-route";
import { GroupsRoute } from "@/routes/groups-route";
import { ImportRoute } from "@/routes/import-route";
import { ProgressRoute } from "@/routes/progress-route";
import { ReviewRoute } from "@/routes/review-route";
import { SettingsRoute } from "@/routes/settings-route";
export function AppRouter() {
    return (_jsx(AppLayout, { children: _jsxs(Routes, { children: [_jsx(Route, { path: "/", element: _jsx(ImportRoute, {}) }), _jsx(Route, { path: "/progress", element: _jsx(ProgressRoute, {}) }), _jsx(Route, { path: "/groups", element: _jsx(GroupsRoute, {}) }), _jsx(Route, { path: "/groups/:groupId", element: _jsx(GroupDetailRoute, {}) }), _jsx(Route, { path: "/review", element: _jsx(ReviewRoute, {}) }), _jsx(Route, { path: "/export", element: _jsx(ExportRoute, {}) }), _jsx(Route, { path: "/settings", element: _jsx(SettingsRoute, {}) }), _jsx(Route, { path: "*", element: _jsx(Navigate, { to: "/", replace: true }) })] }) }));
}
