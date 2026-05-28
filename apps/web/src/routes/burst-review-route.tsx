import { useEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { GroupListItem, PhotoReviewItem } from "@skysort/client";

import { Panel } from "@/components/panel";
import { useGroups } from "@/features/groups/use-groups";
import { useMergeGroup, usePhotoMutation, useSplitGroup } from "@/features/review/use-review-actions";
import { useJobId } from "@/hooks/use-job-id";
import { formatRating, formatScore } from "@/lib/format";

const PAGE_SIZE = 3000;

export function BurstReviewRoute() {
  const jobId = useJobId();
  const [queue, setQueue] = useState("all");
  const [activeGroupIndex, setActiveGroupIndex] = useState(0);
  const [activePhotoId, setActivePhotoId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const groupsQuery = useGroups(jobId, { filter: queueFilter(queue), pageSize: PAGE_SIZE });
  const mutatePhoto = usePhotoMutation(jobId);
  const mergeGroup = useMergeGroup(jobId);
  const splitGroup = useSplitGroup(jobId);
  const groups = groupsQuery.data?.items ?? [];
  const summary = groupsQuery.data?.review_summary;
  const activeGroup = groups[activeGroupIndex] ?? null;
  const activePhoto = activeGroup?.items?.find((photo) => photo.photo_id === activePhotoId) ?? activeGroup?.items?.[0] ?? null;
  const adjacentGap = activeGroup?.previous_gap_seconds ?? null;
  const rowVirtualizer = useVirtualizer({
    count: groups.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 190,
    overscan: 6,
  });

  useEffect(() => {
    setActiveGroupIndex((index) => Math.min(Math.max(0, index), Math.max(0, groups.length - 1)));
  }, [groups.length]);

  useEffect(() => {
    if (!activeGroup?.items?.length) {
      setActivePhotoId(null);
      return;
    }
    if (!activeGroup.items.some((photo) => photo.photo_id === activePhotoId)) {
      setActivePhotoId(activeGroup.items[0].photo_id);
    }
  }, [activeGroup, activePhotoId]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.target instanceof HTMLElement && ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveGroupIndex((index) => {
          const next = Math.min(groups.length - 1, index + 1);
          rowVirtualizer.scrollToIndex(next);
          return next;
        });
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveGroupIndex((index) => {
          const next = Math.max(0, index - 1);
          rowVirtualizer.scrollToIndex(next);
          return next;
        });
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        movePhoto(1);
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        movePhoto(-1);
      }
      if (event.key === "Enter") acceptAI();
      if (event.key.toLowerCase() === "b") setBest();
      if (["k", "p"].includes(event.key.toLowerCase())) keepAlso();
      if (event.key.toLowerCase() === "x") rejectPhoto();
      if (event.key.toLowerCase() === "m") mergePrev();
      if (event.key.toLowerCase() === "s") splitHere();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  function movePhoto(direction: number) {
    const photos = activeGroup?.items ?? [];
    if (!photos.length) return;
    const currentIndex = Math.max(0, photos.findIndex((photo) => photo.photo_id === activePhoto?.photo_id));
    const nextIndex = Math.min(photos.length - 1, Math.max(0, currentIndex + direction));
    setActivePhotoId(photos[nextIndex].photo_id);
  }

  function acceptAI() {
    for (const photo of activeGroup?.items ?? []) {
      mutatePhoto.mutate({ photoId: photo.photo_id, reviewed_flag: true });
    }
  }

  function setBest() {
    if (!activePhoto) return;
    mutatePhoto.mutate({ photoId: activePhoto.photo_id, selection_status: "normal", best_cut_flag: true });
  }

  function keepAlso() {
    if (!activePhoto) return;
    mutatePhoto.mutate({ photoId: activePhoto.photo_id, pick_flag: true });
  }

  function rejectPhoto() {
    if (!activePhoto) return;
    mutatePhoto.mutate({ photoId: activePhoto.photo_id, rating: null, selection_status: "rejected", pick_flag: false, best_cut_flag: false });
  }

  function markReviewed() {
    if (!activePhoto) return;
    mutatePhoto.mutate({ photoId: activePhoto.photo_id, reviewed_flag: !activePhoto.reviewed_flag });
  }

  function mergePrev() {
    const previous = groups[activeGroupIndex - 1];
    if (!activeGroup || !previous) return;
    mergeGroup.mutate({ groupId: activeGroup.id, targetGroupId: previous.id });
  }

  function mergeNext() {
    const next = groups[activeGroupIndex + 1];
    if (!activeGroup || !next) return;
    mergeGroup.mutate({ groupId: next.id, targetGroupId: activeGroup.id });
  }

  function splitHere() {
    if (!activeGroup || !activePhoto) return;
    splitGroup.mutate({ groupId: activeGroup.id, photoIds: [activePhoto.photo_id] });
  }

  return (
    <Panel
      title="Burst Review"
      copy={`${groupsQuery.data?.total ?? 0} groups`}
      actions={
        <select className="filter-select" value={queue} onChange={(event) => setQueue(event.target.value)}>
          <option value="all">All</option>
          <option value="ai_review">AI Review</option>
          <option value="merge_suggested">Merge Suggested</option>
          <option value="singleton">Single Photo</option>
          <option value="ai_failed">AI Failed</option>
          <option value="low_confidence">Low Confidence</option>
          <option value="reject_candidate">Reject Candidate</option>
          <option value="best_missing">Best Missing</option>
          <option value="stale">Stale</option>
        </select>
      }
    >
      {summary ? (
        <div className="score-row" style={{ marginBottom: 12 }}>
          <span className="score-chip">Reviewed {summary.reviewed_groups}/{summary.total_groups}</span>
          <span className="score-chip">Accepted AI {summary.accepted_ai_groups}</span>
          <span className="score-chip">Manual {summary.manually_changed_groups}</span>
          <span className="score-chip">Unresolved {summary.unresolved_groups}</span>
        </div>
      ) : null}
      <div className="burst-layout">
        <div ref={listRef} className="burst-list virtual-list">
          <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: "relative" }}>
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const group = groups[virtualRow.index];
              return (
                <div
                  key={group.id}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    minHeight: `${virtualRow.size}px`,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <BurstGroupRow
                    group={group}
                    active={virtualRow.index === activeGroupIndex}
                    activePhotoId={activePhotoId}
                    onSelect={() => setActiveGroupIndex(virtualRow.index)}
                    onPhotoSelect={setActivePhotoId}
                  />
                </div>
              );
            })}
          </div>
          {!groups.length ? <div className="empty">No groups match this queue.</div> : null}
        </div>
        <aside className="burst-tools">
          <div>
            <h3>{activeGroup?.id ?? "No group"}</h3>
            <p className="panel-copy">{activePhoto?.file_name ?? "No active photo"}</p>
          </div>
          <div className="score-row">
            {activeGroup ? <span className="score-chip">{activeGroup.group_size} photos</span> : null}
            {activeGroup?.review_queue ? <span className="score-chip">{activeGroup.review_queue}</span> : null}
            {activeGroup?.ai_confidence_score != null ? <span className="score-chip">Conf {formatConfidence(activeGroup.ai_confidence_score)}</span> : null}
            {adjacentGap != null ? <span className="score-chip">Prev gap {adjacentGap.toFixed(1)}s</span> : null}
          </div>
          <div className="actions">
            <button className="button secondary" type="button" onClick={acceptAI} disabled={!activeGroup}>Accept AI</button>
            <button className="button secondary" type="button" onClick={setBest} disabled={!activePhoto}>Set Best</button>
            <button className="button secondary" type="button" onClick={keepAlso} disabled={!activePhoto}>Keep Also</button>
            <button className="button warning" type="button" onClick={rejectPhoto} disabled={!activePhoto}>Reject</button>
            <button className="button secondary" type="button" onClick={markReviewed} disabled={!activePhoto}>Mark Reviewed</button>
            <button className="button secondary" type="button" onClick={mergePrev} disabled={!groups[activeGroupIndex - 1]}>Merge Prev</button>
            <button className="button secondary" type="button" onClick={mergeNext} disabled={!groups[activeGroupIndex + 1]}>Merge Next</button>
            <button className="button secondary" type="button" onClick={splitHere} disabled={!activePhoto}>Split Here</button>
          </div>
        </aside>
      </div>
    </Panel>
  );
}

function BurstGroupRow({
  group,
  active,
  activePhotoId,
  onSelect,
  onPhotoSelect,
}: {
  group: GroupListItem;
  active: boolean;
  activePhotoId: string | null;
  onSelect: () => void;
  onPhotoSelect: (photoId: string) => void;
}) {
  const gap = group.previous_gap_seconds;
  return (
    <section className={`burst-row${active ? " active" : ""}`} onClick={onSelect}>
      <header>
        <div>
          <strong>{group.id}</strong>
          <div className="review-row-meta">
            <span>{group.group_size} photos</span>
            <span>Width {durationSeconds(group).toFixed(1)}s</span>
            {gap != null ? <span>Gap {gap.toFixed(1)}s</span> : null}
            {group.ai_confidence_score != null ? <span>Conf {formatConfidence(group.ai_confidence_score)}</span> : null}
            {group.review_queue ? <span>{group.review_queue}</span> : null}
            {group.merge_suggested ? <span>merge_suggested</span> : null}
          </div>
        </div>
        <span className="pill">Best {group.best_photo_id ?? "pending"}</span>
      </header>
      <div className="burst-strip">
        {(group.items ?? []).map((photo) => (
          <BurstThumb
            key={photo.photo_id}
            photo={photo}
            active={photo.photo_id === activePhotoId}
            onSelect={() => onPhotoSelect(photo.photo_id)}
          />
        ))}
      </div>
    </section>
  );
}

function BurstThumb({ photo, active, onSelect }: { photo: PhotoReviewItem; active: boolean; onSelect: () => void }) {
  return (
    <button type="button" className={`burst-thumb${active ? " active" : ""}${photo.selection_status === "rejected" ? " rejected" : ""}`} onClick={(event) => { event.stopPropagation(); onSelect(); }}>
      {photo.thumb_url ? <img src={photo.thumb_url} alt={photo.file_name} /> : <div className="review-thumb-placeholder">No preview</div>}
      <span>{formatRating(photo.rating, photo.selection_status)}</span>
      <span>AI {formatScore(photo.semantic_score)}</span>
      {photo.best_cut_flag ? <strong>Best</strong> : null}
      {photo.pick_flag ? <strong>Keep</strong> : null}
      {photo.problem_tags?.slice(0, 2).map((tag) => <span key={tag}>{tag}</span>)}
    </button>
  );
}

function queueFilter(queue: string): Record<string, unknown> {
  return queue === "all" ? {} : { review_queue: queue };
}

function durationSeconds(group: GroupListItem): number {
  const start = Date.parse(group.group_start_time ?? "");
  const end = Date.parse(group.group_end_time ?? "");
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, (end - start) / 1000) : 0;
}

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}
