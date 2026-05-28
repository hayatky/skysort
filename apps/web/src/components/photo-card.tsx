import type { PhotoReviewItem } from "@skysort/client";

import { formatRating, formatScore } from "@/lib/format";

export function PhotoCard({
  photo,
  active,
  onSelect,
}: {
  photo: PhotoReviewItem;
  active?: boolean;
  onSelect?: () => void;
}) {
  return (
    <button
      type="button"
      className="photo-card"
      style={{ textAlign: "left", outline: active ? "2px solid var(--accent)" : "none" }}
      onClick={onSelect}
    >
      {photo.thumb_url ? <img src={photo.thumb_url} alt={photo.file_name} /> : <div className="empty">No preview</div>}
      <header>
        <div>
          <strong>{photo.file_name}</strong>
          <div className="panel-copy">{formatRating(photo.rating, photo.selection_status)}</div>
        </div>
        <span className="pill">{photo.evaluation_status}</span>
      </header>
      <div className="score-row">
        <span className="score-chip">Tech {formatScore(photo.technical_score_total)}</span>
        <span className="score-chip">AI {formatScore(photo.semantic_score)}</span>
        {photo.ai_confidence_score != null ? <span className="score-chip">Conf {formatConfidence(photo.ai_confidence_score)}</span> : null}
        {photo.is_missing ? <span className="score-chip">Missing</span> : null}
        {photo.stale_flag ? <span className="score-chip">Stale</span> : null}
        {photo.evaluation_status === "ai_eval_failed" ? <span className="score-chip">AI Failed</span> : null}
        {photo.review_queue === "low_confidence" ? <span className="score-chip">Low Confidence</span> : null}
        {photo.provisional_rating ? <span className="score-chip">Provisional {photo.provisional_rating}</span> : null}
        {photo.best_cut_flag ? <span className="score-chip">Best Cut</span> : null}
        {photo.pick_flag ? <span className="score-chip">Pick</span> : null}
        {photo.reviewed_flag ? <span className="score-chip">Reviewed</span> : null}
        {photo.problem_tags?.map((tag) => <span key={tag} className="score-chip">{tag}</span>)}
      </div>
    </button>
  );
}

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}
