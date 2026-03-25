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
        {photo.provisional_rating ? <span className="score-chip">Provisional {photo.provisional_rating}</span> : null}
        {photo.best_cut_flag ? <span className="score-chip">Best Cut</span> : null}
        {photo.pick_flag ? <span className="score-chip">Pick</span> : null}
        {photo.reviewed_flag ? <span className="score-chip">Reviewed</span> : null}
      </div>
    </button>
  );
}
