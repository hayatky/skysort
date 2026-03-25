import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Link, useSearchParams } from "react-router-dom";
import { formatScore } from "@/lib/format";
export function GroupCard({ group }) {
    const [searchParams] = useSearchParams();
    const job = searchParams.get("job") ?? "";
    return (_jsxs(Link, { className: "list-card", to: `/groups/${group.id}?job=${job}`, children: [group.representative_thumb_url ? _jsx("img", { src: group.representative_thumb_url, alt: group.id }) : _jsx("div", { className: "empty", children: "No preview" }), _jsxs("header", { children: [_jsxs("div", { children: [_jsx("strong", { children: group.id }), _jsxs("div", { className: "panel-copy", children: [group.group_size, " photos"] })] }), _jsxs("span", { className: "pill", children: [group.unreviewed_count, " pending"] })] }), _jsxs("div", { className: "score-row", children: [_jsxs("span", { className: "score-chip", children: ["Best ", group.best_photo_id ?? "pending"] }), _jsxs("span", { className: "score-chip", children: ["Tech ", formatScore(group.technical_score_total)] }), _jsxs("span", { className: "score-chip", children: ["AI ", formatScore(group.semantic_score)] })] })] }));
}
