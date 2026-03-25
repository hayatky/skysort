import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { StatGrid } from "@/components/stat-grid";
import { useAIHealth, useImportJob } from "@/features/import/use-import";
export function ImportRoute() {
    const navigate = useNavigate();
    const [rootPath, setRootPath] = useState("");
    const [recursive, setRecursive] = useState(true);
    const [reuseCache, setReuseCache] = useState(true);
    const health = useAIHealth();
    const importJob = useImportJob();
    const healthSummary = useMemo(() => [
        { label: "Reachable", value: health.data?.reachable ? "YES" : "NO" },
        { label: "Model", value: health.data?.configured_model ?? "n/a" },
        { label: "Vision", value: health.data?.vision_capable ? "OK" : "WAIT" },
    ], [health.data]);
    return (_jsxs(_Fragment, { children: [_jsx(Hero, { title: "Burst intake with local AI preflight.", copy: "\u53D6\u308A\u8FBC\u307F\u524D\u306B LM Studio \u758E\u901A\u3092\u78BA\u8A8D\u3057\u3001\u305D\u306E\u307E\u307E\u89E3\u6790\u3092\u8D77\u52D5\u3057\u307E\u3059\u3002MVP \u3067\u306F\u30D1\u30B9\u5165\u529B\u3092\u6B63\u672C\u306B\u3057\u3001\u30D5\u30A9\u30EB\u30C0\u9078\u629E\u30C0\u30A4\u30A2\u30ED\u30B0\u306B\u306F\u4F9D\u5B58\u3057\u307E\u305B\u3093\u3002", badge: "Phase 1 Intake", right: _jsx(StatGrid, { items: healthSummary }) }), _jsxs(Panel, { title: "Import Folder", copy: "ARW / JPEG / PNG \u3092\u5BFE\u8C61\u306B\u518D\u5E30\u8D70\u67FB\u3057\u307E\u3059\u3002", children: [_jsxs("div", { className: "field-grid", children: [_jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "rootPath", children: "Root Path" }), _jsx("input", { id: "rootPath", value: rootPath, onChange: (event) => setRootPath(event.target.value), placeholder: "/Volumes/photo-burst/2026-03-25" })] }), _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "recursive", children: "Recursive" }), _jsxs("select", { id: "recursive", value: String(recursive), onChange: (event) => setRecursive(event.target.value === "true"), children: [_jsx("option", { value: "true", children: "Enabled" }), _jsx("option", { value: "false", children: "Disabled" })] })] }), _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "reuseCache", children: "Reuse Cache" }), _jsxs("select", { id: "reuseCache", value: String(reuseCache), onChange: (event) => setReuseCache(event.target.value === "true"), children: [_jsx("option", { value: "true", children: "Enabled" }), _jsx("option", { value: "false", children: "Disabled" })] })] })] }), _jsxs("div", { className: "actions", style: { marginTop: 20 }, children: [_jsx("button", { className: "button", type: "button", disabled: !rootPath || importJob.isPending || !health.data?.reachable, onClick: async () => {
                                    const response = await importJob.mutateAsync({
                                        rootPath,
                                        recursive,
                                        reuseCache,
                                        fileTypes: [".arw", ".jpg", ".jpeg", ".png"],
                                    });
                                    navigate(`/progress?job=${response.job_id}`);
                                }, children: "Start Analysis" }), importJob.error ? _jsx("span", { className: "pill", children: String(importJob.error) }) : null] })] }), _jsxs(Panel, { title: "AI Health", copy: "\u89E3\u6790\u958B\u59CB\u524D\u306E\u5FC5\u9808\u30C1\u30A7\u30C3\u30AF\u3067\u3059\u3002\u672A\u8D77\u52D5\u306A\u3089\u3053\u3053\u3067\u6B62\u3081\u307E\u3059\u3002", children: [_jsxs("div", { className: "score-row", children: [_jsx("span", { className: `pill`, children: health.data?.reachable ? "reachable" : "offline" }), _jsx("span", { className: "pill", children: health.data?.configured_model_exists ? "model ready" : "model missing" }), _jsx("span", { className: "pill", children: health.data?.structured_json_capable ? "json mode" : "json uncertain" })] }), health.data?.error_detail ? _jsx("p", { className: "panel-copy", children: health.data.error_detail }) : null] })] }));
}
