import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { ReanalyzeScope } from "@skysort/client";

import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { PhotoCard } from "@/components/photo-card";
import { usePhotos } from "@/features/groups/use-groups";
import { usePhotoMutation, useReanalyzePhoto } from "@/features/review/use-review-actions";
import { useJobId } from "@/hooks/use-job-id";
import { useReviewShortcuts } from "@/hooks/use-review-shortcuts";

export function ReviewRoute() {
  const jobId = useJobId();
  const mutate = usePhotoMutation(jobId);
  const reanalyzePhoto = useReanalyzePhoto(jobId);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [reanalyzeScope, setReanalyzeScope] = useState<ReanalyzeScope>("full");
  const [page, setPage] = useState(1);
  const parentRef = useRef<HTMLDivElement | null>(null);
  const apiFilter = useMemo(() => withSearchAndDates(photoFilterPayload(filter), search, dateFrom, dateTo), [filter, search, dateFrom, dateTo]);
  const photos = usePhotos(jobId, { filter: apiFilter, page, pageSize: 80 });
  const items = photos.data?.items ?? [];
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

  const counts = useMemo(
    () => ({
      visible: items.length,
      total: photos.data?.total ?? items.length,
    }),
    [items.length, photos.data?.total],
  );

  const changeFilter = (nextFilter: string) => {
    setFilter(nextFilter);
    setSelectedIndex(0);
    setPage(1);
  };
  const changeSearch = (nextSearch: string) => {
    setSearch(nextSearch);
    setSelectedIndex(0);
    setPage(1);
  };
  const changeDateFrom = (nextDate: string) => {
    setDateFrom(nextDate);
    setSelectedIndex(0);
    setPage(1);
  };
  const changeDateTo = (nextDate: string) => {
    setDateTo(nextDate);
    setSelectedIndex(0);
    setPage(1);
  };

  return (
    <>
      <Hero
        title="Global review for star tiers and reject lanes."
        copy="大量件数向けに仮想スクロールを前提にした全体レビューです。未確認、reject、pick を横断で拾います。"
        badge="Global Review"
        right={
          <>
            <div className="pill">Visible {counts.visible}</div>
            <div className="pill">Total {counts.total}</div>
          </>
        }
      />
      <Panel title="All Photos" copy={`${items.length} frames`}>
        <div className="field-grid" style={{ marginBottom: 16 }}>
          <div className="field">
            <label htmlFor="review-search">Search</label>
            <input
              id="review-search"
              value={search}
              onChange={(event) => changeSearch(event.target.value)}
              placeholder="filename, path, camera, lens, reason"
            />
          </div>
          <div className="field">
            <label htmlFor="review-date-from">From</label>
            <input id="review-date-from" type="date" value={dateFrom} onChange={(event) => changeDateFrom(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="review-date-to">To</label>
            <input id="review-date-to" type="date" value={dateTo} onChange={(event) => changeDateTo(event.target.value)} />
          </div>
        </div>
        <div className="actions" style={{ marginBottom: 16 }}>
          <button className="button secondary" type="button" onClick={() => changeFilter("all")}>All</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("pending")}>Unreviewed</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("reject")}>Reject</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("drop")}>Delete Candidates</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("pick")}>Pick</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("best")}>Best Cut</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("stale")}>Stale</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("missing")}>Missing</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("ai_failed")}>AI Failed</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("star:5")}>★5</button>
          <button className="button secondary" type="button" onClick={() => changeFilter("star:4")}>★4</button>
        </div>
        {selected ? (
          <div className="actions" style={{ marginBottom: 16 }}>
            {selected.group_id ? (
              <Link className="button secondary" to={`/groups/${selected.group_id}?job=${jobId}`}>
                Open Group
              </Link>
            ) : null}
            <button className="button secondary" type="button" onClick={() => mutate.mutate({ photoId: selected.photo_id, best_cut_flag: !selected.best_cut_flag })}>Toggle Best Cut</button>
            <button className="button secondary" type="button" onClick={() => mutate.mutate({ photoId: selected.photo_id, reviewed_flag: !selected.reviewed_flag })}>Toggle Reviewed</button>
            <select value={reanalyzeScope} onChange={(event) => setReanalyzeScope(event.target.value as ReanalyzeScope)}>
              <option value="full">full</option>
              <option value="technical_only">technical_only</option>
              <option value="ai_only">ai_only</option>
            </select>
            <button className="button secondary" type="button" onClick={() => reanalyzePhoto.mutate({ photoId: selected.photo_id, scope: reanalyzeScope })}>Reanalyze Photo</button>
          </div>
        ) : null}
        <div ref={parentRef} className="virtual-list">
          <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: "relative" }}>
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const photo = items[virtualRow.index];
              return (
                <div
                  key={photo.photo_id}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <PhotoCard photo={photo} active={photo.photo_id === selected?.photo_id} onSelect={() => setSelectedIndex(virtualRow.index)} />
                </div>
              );
            })}
          </div>
        </div>
        <div className="actions" style={{ marginTop: 16 }}>
          <button className="button secondary" type="button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button>
          <span className="pill">Page {photos.data?.page ?? page} / {photos.data?.total_pages ?? 1}</span>
          <button className="button secondary" type="button" disabled={page >= (photos.data?.total_pages ?? 1)} onClick={() => setPage((value) => value + 1)}>Next</button>
        </div>
      </Panel>
    </>
  );
}

function photoFilterPayload(filter: string): Record<string, unknown> {
  if (filter === "pending") return { reviewed: false };
  if (filter === "reject") return { reject: true };
  if (filter === "drop") return { delete_candidate: true };
  if (filter === "pick") return { pick: true };
  if (filter === "best") return { best: true };
  if (filter === "stale") return { stale: true };
  if (filter === "missing") return { is_missing: true };
  if (filter === "ai_failed") return { evaluation_status: "ai_eval_failed" };
  if (filter.startsWith("star:")) return { rating: Number(filter.split(":")[1]) };
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
