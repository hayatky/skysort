import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
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
  const parentRef = useRef<HTMLDivElement | null>(null);
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

  const counts = useMemo(
    () => ({
      picks: rawItems.filter((item) => item.pick_flag).length,
      rejected: rawItems.filter((item) => item.selection_status === "rejected").length,
      pending: rawItems.filter((item) => item.evaluation_status !== "final").length,
    }),
    [rawItems],
  );

  return (
    <>
      <Hero
        title="Global review for star tiers and reject lanes."
        copy="大量件数向けに仮想スクロールを前提にした全体レビューです。未確認、reject、pick を横断で拾います。"
        badge="Global Review"
        right={
          <>
            <div className="pill">Picks {counts.picks}</div>
            <div className="pill">Reject {counts.rejected}</div>
            <div className="pill">Pending {counts.pending}</div>
          </>
        }
      />
      <Panel title="All Photos" copy={`${items.length} frames`}>
        <div className="actions" style={{ marginBottom: 16 }}>
          <button className="button secondary" type="button" onClick={() => setFilter("all")}>All</button>
          <button className="button secondary" type="button" onClick={() => setFilter("pending")}>Unreviewed</button>
          <button className="button secondary" type="button" onClick={() => setFilter("reject")}>Reject</button>
          <button className="button secondary" type="button" onClick={() => setFilter("drop")}>Delete Candidates</button>
          <button className="button secondary" type="button" onClick={() => setFilter("pick")}>Pick</button>
          <button className="button secondary" type="button" onClick={() => setFilter("best")}>Best Cut</button>
          <button className="button secondary" type="button" onClick={() => setFilter("star:5")}>★5</button>
          <button className="button secondary" type="button" onClick={() => setFilter("star:4")}>★4</button>
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
            <button className="button secondary" type="button" onClick={() => reanalyzePhoto.mutate(selected.photo_id)}>Reanalyze Photo</button>
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
      </Panel>
    </>
  );
}
