import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { GroupCard } from "@/components/group-card";
import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { useGroups } from "@/features/groups/use-groups";
import { useMergeGroup } from "@/features/review/use-review-actions";
import { useJobId } from "@/hooks/use-job-id";

export function GroupsRoute() {
  const jobId = useJobId();
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [mergeSourceId, setMergeSourceId] = useState("");
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [page, setPage] = useState(1);
  const mergeGroup = useMergeGroup(jobId);
  const apiFilter = useMemo(() => withSearchAndDates(groupFilterPayload(filter), search, dateFrom, dateTo), [filter, search, dateFrom, dateTo]);
  const groups = useGroups(jobId, { filter: apiFilter, page, pageSize: 48 });
  const items = groups.data?.items ?? [];

  const changeFilter = (nextFilter: string) => {
    setFilter(nextFilter);
    setPage(1);
  };
  const changeSearch = (nextSearch: string) => {
    setSearch(nextSearch);
    setPage(1);
  };
  const changeDateFrom = (nextDate: string) => {
    setDateFrom(nextDate);
    setPage(1);
  };
  const changeDateTo = (nextDate: string) => {
    setDateTo(nextDate);
    setPage(1);
  };

  if (!jobId) {
    return (
      <>
        <Hero title="Groups" />
        <Panel title="No Job Selected" copy="Choose a project before opening groups.">
          <Link className="button" to="/">Open Projects</Link>
        </Panel>
      </>
    );
  }

  return (
    <>
      <Hero
        title="Groups"
        right={<Link className="button" to={`/review?job=${jobId}`}>Global Review</Link>}
      />

      <Panel title="Groups" copy={`${groups.data?.total ?? items.length} groups`}>
        <div className="field-grid" style={{ marginBottom: 16 }}>
          <div className="field">
            <label htmlFor="group-search">Search</label>
            <input
              id="group-search"
              value={search}
              onChange={(event) => changeSearch(event.target.value)}
              placeholder="filename, path, camera, lens, reason"
            />
          </div>
          <div className="field">
            <label htmlFor="group-date-from">From</label>
            <input id="group-date-from" type="date" value={dateFrom} onChange={(event) => changeDateFrom(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="group-date-to">To</label>
            <input id="group-date-to" type="date" value={dateTo} onChange={(event) => changeDateTo(event.target.value)} />
          </div>
        </div>
        <div className="actions" style={{ marginBottom: 16 }}>
          <button className="button secondary" type="button" onClick={() => changeFilter("all")}>All</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("pending")}>Pending</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("reject")}>Reject</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("pick")}>Pick</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("stale")}>Stale</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("ai_failed")}>AI Failed</button>
        </div>
        <div className="field-grid" style={{ marginBottom: 16 }}>
          <div className="field">
            <label htmlFor="merge-source-group">Merge Source</label>
            <input id="merge-source-group" value={mergeSourceId} onChange={(event) => setMergeSourceId(event.target.value)} placeholder="group to merge" />
          </div>
          <div className="field">
            <label htmlFor="merge-target-group">Merge Target</label>
            <input id="merge-target-group" value={mergeTargetId} onChange={(event) => setMergeTargetId(event.target.value)} placeholder="group to keep" />
          </div>
          <div className="field">
            <label htmlFor="merge-action">Action</label>
            <button
              id="merge-action"
              className="button warning"
              type="button"
              disabled={!mergeSourceId.trim() || !mergeTargetId.trim()}
              onClick={() => mergeGroup.mutate({ groupId: mergeSourceId.trim(), targetGroupId: mergeTargetId.trim() })}
            >
              Merge Groups
            </button>
          </div>
        </div>
        <div className="group-list">
          {items.map((group) => <GroupCard key={group.id} group={group} />)}
        </div>
        <div className="actions" style={{ marginTop: 16 }}>
          <button className="button secondary" type="button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button>
          <span className="pill">Page {groups.data?.page ?? page} / {groups.data?.total_pages ?? 1}</span>
          <button className="button secondary" type="button" disabled={page >= (groups.data?.total_pages ?? 1)} onClick={() => setPage((value) => value + 1)}>Next</button>
        </div>
        {!items.length ? <div className="empty">No groups yet.</div> : null}
      </Panel>
    </>
  );
}

function groupFilterPayload(filter: string): Record<string, unknown> {
  if (filter === "pending") return { reviewed: false };
  if (filter === "reject") return { reject: true };
  if (filter === "pick") return { pick: true };
  if (filter === "stale") return { stale: true };
  if (filter === "ai_failed") return { evaluation_status: "ai_eval_failed" };
  return {};
}

function withSearchAndDates(filter: Record<string, unknown>, search: string, dateFrom: string, dateTo: string): Record<string, unknown> {
  const query = search.trim();
  return {
    ...filter,
    ...(query ? { q: query } : {}),
    ...(dateFrom ? { date_from: `${dateFrom}T00:00:00+00:00` } : {}),
    ...(dateTo ? { date_to: `${dateTo}T23:59:59+00:00` } : {}),
  };
}
