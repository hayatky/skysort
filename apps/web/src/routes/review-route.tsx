import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { PhotoReviewItem, ReanalyzeScope } from "@skysort/client";

import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { usePhotos } from "@/features/groups/use-groups";
import { usePhotoMutation, useReanalyzePhoto } from "@/features/review/use-review-actions";
import { useJobId } from "@/hooks/use-job-id";
import { useReviewShortcuts } from "@/hooks/use-review-shortcuts";
import { formatRating, formatScore } from "@/lib/format";

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
    estimateSize: () => 112,
    overscan: 8,
  });
  useEffect(() => {
    if (items.length) {
      rowVirtualizer.scrollToIndex(selectedIndex, { align: "auto" });
    }
  }, [items.length, rowVirtualizer, selectedIndex]);

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

  if (!jobId) {
    return (
      <>
        <Hero title="Review" />
        <Panel title="No Job Selected" copy="Choose a project before opening review.">
          <Link className="button" to="/">Open Projects</Link>
        </Panel>
      </>
    );
  }

  return (
    <>
      <Hero
        title="Review"
        right={
          <>
            <div className="pill">Visible {counts.visible}</div>
            <div className="pill">Total {counts.total}</div>
          </>
        }
      />
      <Panel title="All Photos">
        <div className="field-grid" style={{ marginBottom: 12 }}>
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
          <div className="field">
            <label htmlFor="review-filter">Filter</label>
            <select id="review-filter" className="filter-select" value={filter} onChange={(event) => changeFilter(event.target.value)}>
              <option value="all">All</option>
              <option value="pending">Unreviewed</option>
              <option value="reject">Reject</option>
              <option value="drop">Delete Candidates</option>
              <option value="pick">Pick</option>
              <option value="best">Best Cut</option>
              <option value="star:5">⊅5</option>
              <option value="star:4">⊅4</option>
              <option value="star:3">⊅3</option>
              <option value="star:2">⊅2</option>
              <option value="star:1">⊅1</option>
              <option value="stale">Stale</option>
              <option value="missing">Missing</option>
              <option value="ai_failed">AI Failed</option>
              <option value="queue:ai_failed">AI Failure Queue</option>
              <option value="queue:low_confidence">Low Confidence Queue</option>
              <option value="queue:stale">Stale Queue</option>
              <option value="queue:reject_candidate">Reject Queue</option>
              <option value="queue:ai_review">AI Review Queue</option>
              <option value="ai_complete">AI Complete</option>
              <option value="user_override">User Overrides</option>
              <option value="problem:motion_blur">Motion Blur Tag</option>
              <option value="problem:bad_crop">Bad Crop Tag</option>
            </select>
          </div>
        </div>
        <div className="review-workspace">
          <div ref={parentRef} className="virtual-list review-list">
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
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    <ReviewListRow photo={photo} active={photo.photo_id === selected?.photo_id} onSelect={() => setSelectedIndex(virtualRow.index)} />
                  </div>
                );
              })}
            </div>
          </div>
          <aside className="review-preview">
            {selected ? (
              <>
                {selected.preview_url ? <img src={selected.preview_url} alt={selected.file_name} /> : <div className="empty">No preview</div>}
                <div>
                  <h3>{selected.file_name}</h3>
                  <p className="panel-copy">{selected.file_path}</p>
                </div>
                <div className="score-row">
                  <span className="score-chip">{formatRating(selected.rating, selected.selection_status)}</span>
                  <span className="score-chip">Tech {formatScore(selected.technical_score_total)}</span>
                  <span className="score-chip">AI {formatScore(selected.semantic_score)}</span>
                  {selected.ai_confidence_score != null ? <span className="score-chip">Confidence {formatConfidence(selected.ai_confidence_score)}</span> : null}
                  {selected.pick_flag ? <span className="score-chip">Pick</span> : null}
                  {selected.best_cut_flag ? <span className="score-chip">Best Cut</span> : null}
                  {selected.reviewed_flag ? <span className="score-chip">Reviewed</span> : null}
                  {selected.stale_flag ? <span className="score-chip">Stale {selected.stale_reason ?? ""}</span> : null}
                  {selected.review_queue === "low_confidence" ? <span className="score-chip">Low Confidence</span> : null}
                  {selected.problem_tags?.map((tag) => <span key={tag} className="score-chip">{tag}</span>)}
                </div>
                {selected.ai_reason ? <p className="panel-copy">{selected.ai_reason}</p> : null}
                <div className="rating-controls" aria-label="Rating controls">
                  {[1, 2, 3, 4, 5].map((rating) => (
                    <button
                      key={rating}
                      type="button"
                      className={selected.rating === rating && selected.selection_status !== "rejected" ? "active" : undefined}
                      onClick={() => mutate.mutate({ photoId: selected.photo_id, rating, selection_status: "normal" })}
                    >
                      ★{rating}
                    </button>
                  ))}
                  <button
                    type="button"
                    className={selected.selection_status === "rejected" ? "active" : undefined}
                    style={selected.selection_status === "rejected" ? { background: "var(--danger)", color: "white", borderColor: "var(--danger)" } : undefined}
                    onClick={() => mutate.mutate({ photoId: selected.photo_id, selection_status: "rejected", rating: null })}
                  >Reject</button>
                </div>
                <div className="actions">
                  {selected.group_id ? (
                    <Link className="button secondary" to={`/groups/${selected.group_id}?job=${jobId}`}>
                      Open Group
                    </Link>
                  ) : null}
                  <button className="button secondary" type="button" onClick={() => mutate.mutate({ photoId: selected.photo_id, pick_flag: !selected.pick_flag })}>Toggle Pick</button>
                  <button className="button secondary" type="button" onClick={() => mutate.mutate({ photoId: selected.photo_id, best_cut_flag: !selected.best_cut_flag })}>Toggle Best Cut</button>
                  <button className="button secondary" type="button" onClick={() => mutate.mutate({ photoId: selected.photo_id, reviewed_flag: !selected.reviewed_flag })}>Toggle Reviewed</button>
                </div>
                <div className="actions">
                  <select value={reanalyzeScope} onChange={(event) => setReanalyzeScope(event.target.value as ReanalyzeScope)}>
                    <option value="full">full</option>
                    <option value="technical_only">technical_only</option>
                    <option value="ai_only">ai_only</option>
                  </select>
                  <button className="button secondary" type="button" onClick={() => reanalyzePhoto.mutate({ photoId: selected.photo_id, scope: reanalyzeScope })}>Reanalyze Photo</button>
                </div>
              </>
            ) : (
              <div className="empty">No photos match this filter.</div>
            )}
          </aside>
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

function ReviewListRow({ photo, active, onSelect }: { photo: PhotoReviewItem; active: boolean; onSelect: () => void }) {
  return (
    <button type="button" className={`review-list-row${active ? " active" : ""}`} onClick={onSelect}>
      {photo.thumb_url ? <img src={photo.thumb_url} alt={photo.file_name} /> : <div className="review-thumb-placeholder">No preview</div>}
      <div className="review-row-main">
        <div className="review-row-title">
          <strong>{photo.file_name}</strong>
          <span>{formatRating(photo.rating, photo.selection_status)}</span>
        </div>
        <div className="review-row-meta">
          <span>Tech {formatScore(photo.technical_score_total)}</span>
          <span>AI {formatScore(photo.semantic_score)}</span>
          {photo.ai_confidence_score != null ? <span>Conf {formatConfidence(photo.ai_confidence_score)}</span> : null}
          <span>{photo.evaluation_status}</span>
          {photo.is_missing ? <span>Missing</span> : null}
          {photo.stale_flag ? <span>Stale</span> : null}
          {photo.review_queue && photo.review_queue !== "reviewed" ? <span>{photo.review_queue}</span> : null}
          {photo.pick_flag ? <span>Pick</span> : null}
          {photo.best_cut_flag ? <span>Best Cut</span> : null}
          {photo.reviewed_flag ? <span>Reviewed</span> : null}
        </div>
        <div className="review-row-path">{photo.file_path}</div>
      </div>
    </button>
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
  if (filter === "ai_complete") return { ai_complete: true };
  if (filter.startsWith("queue:")) return { review_queue: filter.split(":")[1] };
  if (filter.startsWith("problem:")) return { problem_tag: filter.split(":")[1] };
  if (filter === "user_override") return { user_override_only: true };
  if (filter.startsWith("star:")) return { rating: Number(filter.split(":")[1]) };
  return {};
}

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
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
