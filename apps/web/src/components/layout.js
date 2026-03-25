import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Sidebar } from "./sidebar";
export function AppLayout({ children }) {
    return (_jsx("div", { className: "shell", children: _jsxs("div", { className: "shell-grid", children: [_jsx(Sidebar, {}), _jsx("main", { className: "content", children: children })] }) }));
}
