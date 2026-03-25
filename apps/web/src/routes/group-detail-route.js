import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { PhotoCard } from "@/components/photo-card";
import { useGroup } from "@/features/groups/use-groups";
import { usePhotoMutation, useReanalyzeGroup, useReanalyzePhoto } from "@/features/review/use-review-actions";
import { useJobId } from "@/hooks/use-job-id";
import { useReviewShortcuts } from "@/hooks/use-review-shortcuts";
export function GroupDetailRoute() {
    const { groupId = "" } = useParams();
    const jobId = useJobId();
    const group = useGroup(groupId);
    const mutate = usePhotoMutation(jobId);
    const reanalyzeGroup = useReanalyzeGroup(jobId);
    const reanalyzePhoto = useReanalyzePhoto(jobId);
    const [index, setIndex] = useState(0);
    const [expanded, setExpanded] = useState(false);
    const selected = group.data?.photos[index];
    useReviewShortcuts({
        enabled: Boolean(selected),
        onRate: (rating) => selected && mutate.mutate({ photoId: selected.photo_id, rating }),
        onReject: () => selected && mutate.mutate({ photoId: selected.photo_id, rating: null, selection_status: "rejected" }),
        onPick: () => selected && mutate.mutate({ photoId: selected.photo_id, pick_flag: !selected.pick_flag }),
        onNext: () => setIndex((value) => Math.min((group.data?.photos.length ?? 1) - 1, value + 1)),
        onPrev: () => setIndex((value) => Math.max(0, value - 1)),
        onTogglePreview: () => setExpanded((value) => !value),
    });
    const actionButtons = useMemo(() => (_jsxs("div", { className: "toolbar", children: [_jsx("button", { type: "button", onClick: () => selected && mutate.mutate({ photoId: selected.photo_id, rating: 5 }), children: "\u26055" }), _jsx("button", { type: "button", onClick: () => selected && mutate.mutate({ photoId: selected.photo_id, rating: 4 }), children: "\u26054" }), _jsx("button", { type: "button", onClick: () => selected && mutate.mutate({ photoId: selected.photo_id, selection_status: "rejected", rating: null }), children: "Reject" }), _jsx("button", { type: "button", onClick: () => selected && mutate.mutate({ photoId: selected.photo_id, pick_flag: !selected.pick_flag }), children: "Pick" }), _jsx("button", { type: "button", onClick: () => selected && mutate.mutate({ photoId: selected.photo_id, best_cut_flag: !selected.best_cut_flag }), children: "Best Cut" }), _jsx("button", { type: "button", onClick: () => selected && mutate.mutate({ photoId: selected.photo_id, reviewed_flag: !selected.reviewed_flag }), children: "Reviewed" }), _jsx("button", { type: "button", onClick: () => selected && reanalyzePhoto.mutate(selected.photo_id), children: "Reanalyze Photo" }), _jsx("button", { type: "button", onClick: () => groupId && reanalyzeGroup.mutate(groupId), children: "Reanalyze Group" })] })), [groupId, mutate, reanalyzeGroup, reanalyzePhoto, selected]);
    return (_jsxs(_Fragment, { children: [_jsx(Hero, { title: "Frame-by-frame burst review.", copy: "\u30B0\u30EB\u30FC\u30D7\u8A73\u7D30\u3067\u306F\u30B7\u30E7\u30FC\u30C8\u30AB\u30C3\u30C8\u3092\u512A\u5148\u3057\u3001AI \u672A\u5B8C\u4E86\u3067\u3082\u66AB\u5B9A\u8A55\u4FA1\u3092\u7DAD\u6301\u3057\u307E\u3059\u3002", badge: "Group Detail", right: _jsx("div", { className: "pill", children: "1-5 / X / P / arrows / Space" }) }), _jsxs("div", { className: "review-layout", children: [_jsx(Panel, { title: group.data?.id ?? "Group", copy: `${group.data?.photos.length ?? 0} photos`, actions: actionButtons, children: _jsx("div", { className: "photo-grid", children: group.data?.photos.map((photo, photoIndex) => (_jsx(PhotoCard, { photo: photo, active: selected?.photo_id === photo.photo_id, onSelect: () => setIndex(photoIndex) }, photo.photo_id))) }) }), _jsx("div", { className: "preview-panel", children: _jsxs(Panel, { title: selected?.file_name ?? "Preview", copy: selected?.ai_reason ?? "Select a frame", children: [selected?.preview_url ? _jsx("img", { src: selected.preview_url, alt: selected.file_name, style: expanded ? { aspectRatio: "16 / 10" } : undefined }) : _jsx("div", { className: "empty", children: "No preview" }), selected ? (_jsxs("div", { className: "meta-row", children: [_jsxs("span", { className: "score-chip", children: ["Status ", selected.evaluation_status] }), _jsxs("span", { className: "score-chip", children: ["Rating ", selected.rating ?? "n/a"] }), _jsxs("span", { className: "score-chip", children: ["Provisional ", selected.provisional_rating ?? "n/a"] }), _jsxs("span", { className: "score-chip", children: ["Tech ", selected.technical_score_total ?? "n/a"] }), _jsxs("span", { className: "score-chip", children: ["AI ", selected.semantic_score ?? "n/a"] }), _jsxs("span", { className: "score-chip", children: ["Reviewed ", selected.reviewed_flag ? "yes" : "no"] })] })) : null] }) })] })] }));
}
