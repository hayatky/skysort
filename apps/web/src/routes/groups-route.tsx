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

  return (
    <>
      <Hero
        title="Burst groups sorted for human review."
        copy="Phase 1 では結合・分割を実装せず、未確認グループを先に潰せる一覧に集中します。"
        badge="Group Overview"
        right={<Link className="button" to={`/review?job=${jobId}`}>Global Review</Link>}
      />

      <Panel title="Groups" copy={`${filtered.length} groups`}>
        <div className="actions" style={{ marginBottom: 16 }}>
          <button className="button secondary" type="button" onClick={() => setFilter("all")}>All</button>
          <button className="button secondary" type="button" onClick={() => setFilter("pending")}>Pending</button>
          <button className="button secondary" type="button" onClick={() => setFilter("reject")}>Reject</button>
          <button className="button secondary" type="button" onClick={() => setFilter("pick")}>Pick</button>
        </div>
        <div className="group-list">
          {filtered.map((group) => <GroupCard key={group.id} group={group} />)}
        </div>
        {!filtered.length ? <div className="empty">No groups yet.</div> : null}
      </Panel>
    </>
  );
}
