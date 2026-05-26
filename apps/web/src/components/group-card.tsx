import { Link, useSearchParams } from "react-router-dom";
import type { GroupListItem } from "@skysort/client";

import { formatScore } from "@/lib/format";

export function GroupCard({ group }: { group: GroupListItem }) {
  const [searchParams] = useSearchParams();
  const job = searchParams.get("job") ?? "";
  const failedCount = group.items?.filter((photo) => photo.evaluation_status === "ai_eval_failed").length ?? 0;
  const staleCount = (group.stale_flag ? 1 : 0) + (group.items?.filter((photo) => photo.stale_flag).length ?? 0);
  return (
    <Link className="list-card" to={`/groups/${group.id}?job=${job}`}>
      {group.representative_thumb_url ? <img src={group.representative_thumb_url} alt={group.id} /> : <div className="empty">No preview</div>}
      <header>
        <div>
          <strong>{group.id}</strong>
          <div className="panel-copy">{group.group_size} photos</div>
        </div>
        <span className="pill">{group.unreviewed_count} pending</span>
      </header>
      <div className="score-row">
        <span className="score-chip">Best {group.best_photo_id ?? "pending"}</span>
        <span className="score-chip">Tech {formatScore(group.technical_score_total)}</span>
        <span className="score-chip">AI {formatScore(group.semantic_score)}</span>
        {staleCount ? <span className="score-chip">Stale {staleCount}</span> : null}
        {failedCount ? <span className="score-chip">AI Failed {failedCount}</span> : null}
      </div>
    </Link>
  );
}
