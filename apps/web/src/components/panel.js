import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function Panel({ title, copy, actions, children }) {
    return (_jsxs("section", { className: "panel", children: [_jsxs("header", { className: "panel-header", children: [_jsxs("div", { children: [_jsx("h2", { className: "panel-title", children: title }), copy ? _jsx("p", { className: "panel-copy", children: copy }) : null] }), actions] }), children] }));
}
