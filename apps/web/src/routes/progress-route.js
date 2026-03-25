import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { Link } from "react-router-dom";
import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { StatGrid } from "@/components/stat-grid";
import { useAIHealth } from "@/features/import/use-import";
import { useFailures, useProgress } from "@/features/progress/use-progress";
import { useJobId } from "@/hooks/use-job-id";
export function ProgressRoute() {
    const jobId = useJobId();
    const progress = useProgress(jobId);
    const failures = useFailures(jobId);
    const health = useAIHealth();
    return (_jsxs(_Fragment, { children: [_jsx(Hero, { title: "Pipeline telemetry for long local runs.", copy: "\u30DD\u30FC\u30EA\u30F3\u30B0\u3092\u6B63\u672C\u306B\u3057\u3066\u9032\u6357\u3092\u76E3\u8996\u3057\u307E\u3059\u3002SSE \u3092\u5165\u308C\u3066\u3082\u3001\u3053\u306E\u753B\u9762\u306E\u30D5\u30A9\u30FC\u30EB\u30D0\u30C3\u30AF\u306F\u5909\u3048\u307E\u305B\u3093\u3002", badge: "Job Progress", right: _jsx(StatGrid, { items: [
                        { label: "Stage", value: progress.data?.current_stage ?? "idle" },
                        { label: "Status", value: progress.data?.status ?? "queued" },
                        { label: "Failures", value: progress.data?.failed_files ?? 0 },
                    ] }) }), _jsxs(Panel, { title: "Progress", copy: jobId ? `Job ${jobId}` : "No job selected", children: [_jsx(StatGrid, { items: [
                            { label: "Total", value: progress.data?.total_files ?? 0 },
                            { label: "Imported", value: progress.data?.imported_files ?? 0 },
                            { label: "Grouped", value: progress.data?.grouped_files ?? 0 },
                            { label: "Technical", value: progress.data?.technically_scored_files ?? 0 },
                            { label: "AI", value: progress.data?.semantically_scored_files ?? 0 },
                            { label: "Provisional", value: progress.data?.provisional_rated_files ?? 0 },
                            { label: "Final", value: progress.data?.final_rated_files ?? 0 },
                        ] }), _jsxs("div", { className: "actions", style: { marginTop: 20 }, children: [_jsx(Link, { className: "button", to: `/groups?job=${jobId}`, children: "Open Groups" }), _jsx(Link, { className: "button secondary", to: `/review?job=${jobId}`, children: "Open Review" })] })] }), _jsx(Panel, { title: "Failures", copy: "\u753B\u50CF\u5358\u4F4D\u306E\u5931\u6557\u306F\u5168\u4F53\u505C\u6B62\u306B\u3057\u307E\u305B\u3093\u3002", children: failures.data?.items?.length ? (_jsx("div", { className: "grid", children: failures.data.items.map((item) => (_jsxs("div", { className: "list-card", children: [_jsx("strong", { children: item.stage }), _jsx("p", { className: "panel-copy", children: item.reason })] }, `${item.stage}-${item.reason}`))) })) : (_jsx("div", { className: "empty", children: "No failures recorded." })) }), _jsx(Panel, { title: "AI Health", copy: "\u89E3\u6790\u524D\u63D0\u306E LM Studio \u63A5\u7D9A\u72B6\u614B", children: _jsx(StatGrid, { items: [
                        { label: "Reachable", value: health.data?.reachable ? "YES" : "NO" },
                        { label: "Model", value: health.data?.configured_model_exists ? "READY" : "MISSING" },
                        { label: "Vision", value: health.data?.vision_capable ? "OK" : "NO" },
                        { label: "JSON", value: health.data?.structured_json_capable ? "OK" : "NO" },
                    ] }) })] }));
}
