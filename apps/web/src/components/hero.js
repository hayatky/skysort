import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function Hero({ title, copy, badge, right, children }) {
    return (_jsxs("section", { className: "hero", children: [_jsxs("div", { children: [_jsx("div", { className: "hero-badge", children: badge }), _jsx("h1", { className: "hero-title", children: title }), _jsx("p", { className: "hero-copy", children: copy }), children] }), _jsx("div", { className: "hero-stack", children: right })] }));
}
