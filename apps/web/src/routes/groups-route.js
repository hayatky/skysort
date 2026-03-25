import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { GroupCard } from "@/components/group-card";
import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { useGroups } from "@/features/groups/use-groups";
import { useJobId } from "@/hooks/use-job-id";
export function GroupsRoute() {
    const jobId = useJobId();
    const groups = useGroups(jobId);
    const [filter, setFilter] = useState("all");
    const filtered = useMemo(() => {
        const items = groups.data ?? [];
        if (filter === "pending") {
            return items.filter((group) => group.unreviewed_count > 0);
        }
        if (filter === "reject") {
            return items.filter((group) => group.items?.some((photo) => photo.selection_status === "rejected"));
        }
        if (filter === "pick") {
            return items.filter((group) => group.items?.some((photo) => photo.pick_flag));
        }
        return items;
    }, [filter, groups.data]);
    return (_jsxs(_Fragment, { children: [_jsx(Hero, { title: "Burst groups sorted for human review.", copy: "Phase 1 \u3067\u306F\u7D50\u5408\u30FB\u5206\u5272\u3092\u5B9F\u88C5\u305B\u305A\u3001\u672A\u78BA\u8A8D\u30B0\u30EB\u30FC\u30D7\u3092\u5148\u306B\u6F70\u305B\u308B\u4E00\u89A7\u306B\u96C6\u4E2D\u3057\u307E\u3059\u3002", badge: "Group Overview", right: _jsx(Link, { className: "button", to: `/review?job=${jobId}`, children: "Global Review" }) }), _jsxs(Panel, { title: "Groups", copy: `${filtered.length} groups`, children: [_jsxs("div", { className: "actions", style: { marginBottom: 16 }, children: [_jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("all"), children: "All" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("pending"), children: "Pending" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("reject"), children: "Reject" }), _jsx("button", { className: "button secondary", type: "button", onClick: () => setFilter("pick"), children: "Pick" })] }), _jsx("div", { className: "group-list", children: filtered.map((group) => _jsx(GroupCard, { group: group }, group.id)) }), !filtered.length ? _jsx("div", { className: "empty", children: "No groups yet." }) : null] })] }));
}
