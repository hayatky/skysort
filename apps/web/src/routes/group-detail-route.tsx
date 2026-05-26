import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import type { ReanalyzeScope } from "@skysort/client";

import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { PhotoCard } from "@/components/photo-card";
import { useGroup } from "@/features/groups/use-groups";
import { usePhotoMutation, useReanalyzeGroup, useReanalyzePhoto, useSplitGroup } from "@/features/review/use-review-actions";
import { useJobId } from "@/hooks/use-job-id";
import { useReviewShortcuts } from "@/hooks/use-review-shortcuts";

export function GroupDetailRoute() {
  const { groupId = "" } = useParams();
  const jobId = useJobId();
  const group = useGroup(groupId);
  const mutate = usePhotoMutation(jobId);
  const reanalyzeGroup = useReanalyzeGroup(jobId);
  const reanalyzePhoto = useReanalyzePhoto(jobId);
  const splitGroup = useSplitGroup(jobId);
  const [index, setIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [reanalyzeScope, setReanalyzeScope] = useState<ReanalyzeScope>("full");
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

  const actionButtons = useMemo(
    () => (
      <div className="toolbar">
        <button type="button" onClick={() => selected && mutate.mutate({ photoId: selected.photo_id, rating: 5 })}>★5</button>
        <button type="button" onClick={() => selected && mutate.mutate({ photoId: selected.photo_id, rating: 4 })}>★4</button>
        <button type="button" onClick={() => selected && mutate.mutate({ photoId: selected.photo_id, selection_status: "rejected", rating: null })}>Reject</button>
        <button type="button" onClick={() => selected && mutate.mutate({ photoId: selected.photo_id, pick_flag: !selected.pick_flag })}>Pick</button>
        <button type="button" onClick={() => selected && mutate.mutate({ photoId: selected.photo_id, best_cut_flag: !selected.best_cut_flag })}>Best Cut</button>
        <button type="button" onClick={() => selected && mutate.mutate({ photoId: selected.photo_id, reviewed_flag: !selected.reviewed_flag })}>Reviewed</button>
        <select value={reanalyzeScope} onChange={(event) => setReanalyzeScope(event.target.value as ReanalyzeScope)}>
          <option value="full">full</option>
          <option value="technical_only">technical_only</option>
          <option value="ai_only">ai_only</option>
        </select>
        <button type="button" onClick={() => selected && reanalyzePhoto.mutate({ photoId: selected.photo_id, scope: reanalyzeScope })}>Reanalyze Photo</button>
        <button type="button" onClick={() => groupId && reanalyzeGroup.mutate({ groupId, scope: reanalyzeScope })}>Reanalyze Group</button>
        <button type="button" onClick={() => selected && groupId && splitGroup.mutate({ groupId, photoIds: [selected.photo_id] })}>Split Selected</button>
      </div>
    ),
    [groupId, mutate, reanalyzeGroup, reanalyzePhoto, reanalyzeScope, selected, splitGroup],
  );

  return (
    <>
      <Hero
        title="Frame-by-frame burst review."
        copy="グループ詳細ではショートカットを優先し、AI 未完了でも暫定評価を維持します。"
        badge="Group Detail"
        right={<div className="pill">1-5 / X / P / arrows / Space</div>}
      />
      <div className="review-layout">
        <Panel title={group.data?.id ?? "Group"} copy={`${group.data?.photos.length ?? 0} photos`} actions={actionButtons}>
          <div className="photo-grid">
            {group.data?.photos.map((photo, photoIndex) => (
              <PhotoCard key={photo.photo_id} photo={photo} active={selected?.photo_id === photo.photo_id} onSelect={() => setIndex(photoIndex)} />
            ))}
          </div>
        </Panel>
        <div className="preview-panel">
          <Panel title={selected?.file_name ?? "Preview"} copy={selected?.ai_reason ?? "Select a frame"}>
            {selected?.preview_url ? <img src={selected.preview_url} alt={selected.file_name} style={expanded ? { aspectRatio: "16 / 10" } : undefined} /> : <div className="empty">No preview</div>}
            {selected ? (
              <div className="meta-row">
                <span className="score-chip">Status {selected.evaluation_status}</span>
                <span className="score-chip">Rating {selected.rating ?? "n/a"}</span>
                <span className="score-chip">Provisional {selected.provisional_rating ?? "n/a"}</span>
                <span className="score-chip">Tech {selected.technical_score_total ?? "n/a"}</span>
                <span className="score-chip">AI {selected.semantic_score ?? "n/a"}</span>
                <span className="score-chip">Reviewed {selected.reviewed_flag ? "yes" : "no"}</span>
                {selected.is_missing ? <span className="score-chip">Missing</span> : null}
                {selected.stale_flag ? <span className="score-chip">Stale {selected.stale_reason ?? "review required"}</span> : null}
                {selected.evaluation_status === "ai_eval_failed" ? <span className="score-chip">AI Failed</span> : null}
              </div>
            ) : null}
          </Panel>
        </div>
      </div>
    </>
  );
}
