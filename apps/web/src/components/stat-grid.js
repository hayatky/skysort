import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function StatGrid({ items }) {
    return (_jsx("dl", { className: "stats", children: items.map((item) => (_jsxs("div", { className: "stat-card", children: [_jsx("dt", { children: item.label }), _jsx("dd", { children: item.value })] }, item.label))) }));
}
