import { jsxs as _jsxs, Fragment as _Fragment, jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { PhotoCard } from "@/components/photo-card";
import { usePhotos } from "@/features/groups/use-groups";
import { usePhotoMutation, useReanalyzePhoto } from "@/features/review/use-review-actions";
import { useJobId } from "@/hooks/use-job-id";
import { useReviewShortcuts } from "@/hooks/use-review-shortcuts";
export function ReviewRoute() {
    const jobId = useJobId();
    const photos = usePhotos(jobId);
    const mutate = usePhotoMutation(jobId);
    const reanalyzePhoto = useReanalyzePhoto(jobId);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [filter, setFilter] = useState("all");
    const parentRef = useRef(null);
    const rawItems = photos.data?.items ?? [];
    const items = useMemo(() => {
        if (filter === "reject") {
            return rawItems.filter((item) => item.selection_status === "rejected");
        }
        if (filter === "pending") {
            return rawItems.filter((item) => !item.reviewed_flag);
        }
        if (filter === "pick") {
            return rawItems.filter((item) => item.pick_flag);
        }
        if (filter === "best") {
            return rawItems.filter((item) => item.best_cut_flag);
        }
        if (filter === "drop") {
            return rawItems.filter((item) => item.rating === 1 || item.selection_status === "rejected");
        }
        if (filter.startsWith("star:")) {
            const target = Number(filter.split(":")[1]);
            return rawItems.filter((item) => item.rating === target);
        }
        return rawItems;
    }, [filter, rawItems]);
    const selected = items[selectedIndex];
    useEffect(() => {
        if (selectedIndex >= items.length) {
            setSelectedIndex(0);
        }
    }, [items.length, selectedIndex]);
    const rowVirtualizer = useVirtualizer({
        count: items.length,
        getScrollElement: () => parentRef.current,
        estimateSize: () => 260,
        overscan: 4,
    });
    useReviewShortcuts({
        enabled: Boolean(selected),
        onRate: (rating) => selected && mutate.mutate({ photoId: selected.photo_id, rating }),
        onReject: () => selected && mutate.mutate({ photoId: selected.photo_id, selection_status: "rejected", rating: null }),
        onPick: () => selected && mutate.mutate({ photoId: selected.photo_id, pick_flag: !selected.pick_flag }),
        onNext: () => setSelectedIndex((value) => Math.min(items.length - 1, value + 1)),
        onPrev: () => setSelectedIndex((value) => Math.max(0, value - 1)),
        onTogglePreview: () => undefined,
    });
    const counts = useMemo(() => ({
        picks: rawItems.filter((item) => item.pick_flag).length,
        rejected: rawItems.filter((item) => item.selection_status === "rejected").length,
        pending: rawItems.filter((item) => item.evaluation_status !== "final").length,
    }), [rawItems]);
    return (_jsxs(_Fragment, { children: [_jsx(Hero, { title: "Global review for star tiers and reject lanes.", copy: "\u5927\u91CF\u4EF6\u6570\u5411\u3051\u306B\u4EEE\u60F3\u30B9\u30AF\u30ED\u30FC\u30EB\u3092\u524D\u63D0\u306B\u3057\u305F\u5168\u4F53\u30EC\u30D3\u30E5\u30FC\u3067\u3059\u3002\u672A\u78BA\u8A8D\u3001reject\u3001pick \u3092\u6A2A\u65AD\u3067\u62FE\u3044\u307E\u3059\u3002", badge: "Global Review", right: _jsxs(_Fragment, { children: [_jsxs("div", { className: "pill", children: ["Picks ", counts.picks] }), _jsxs("div", { className: "pill", children: ["Reject ", counts.rejected] }), _jsxs("div", { className: "pill", children: ["Pending ", counts.pending] })] }) }), _jsxs(Panel, { title: "All Photos", copy: `${items.length} frames`, children: [_jsxs("div", { className: "actions", style: { marginBottom: 16 }, children: [_jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("all"), children: "All" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("pending"), children: "Unreviewed" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("reject"), children: "Reject" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("drop"), children: "Delete Candidates" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("pick"), children: "Pick" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("best"), children: "Best Cut" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("star:5"), children: "\u26055" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("star:4"), children: "\u26054" })] }), selected ? (_jsxs("div", { className: "actions", style: { marginBottom: 16 }, children: [_jsx("button", { className: "button secondary", type: "button", onClick: () => mutate.mutate({ photoId: selected.photo_id, best_cut_flag: !selected.best_cut_flag }), children: "Toggle Best Cut" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => mutate.mutate({ photoId: selected.photo_id, reviewed_flag: !selected.reviewed_flag }), children: "Toggle Reviewed" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => reanalyzePhoto.mutate(selected.photo_id), children: "Reanalyze Photo" })] })) : null, _jsx("div", { ref: parentRef, className: "virtual-list", children: _jsx("div", { style: { height: `${rowVirtualizer.getTotalSize()}px`, position: "relative" }, children: rowVirtualizer.getVirtualItems().map((virtualRow) => {
                                const photo = items[virtualRow.index];
                                return (_jsx("div", { style: {
                                        position: "absolute",
                                        top: 0,
                                        left: 0,
                                        width: "100%",
                                        transform: `translateY(${virtualRow.start}px)`,
                                    }, children: _jsx(PhotoCard, { photo: photo, active: photo.photo_id === selected?.photo_id, onSelect: () => setSelectedIndex(virtualRow.index) }) }, photo.photo_id));
                            }) }) })] })] }));
}
