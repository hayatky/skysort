import { Link } from "react-router-dom";

import { Hero } from "@/components/hero";
import { Panel } from "@/components/panel";
import { PhotoCard } from "@/components/photo-card";
import { usePhotos } from "@/features/groups/use-groups";
import { usePhotoMutation } from "@/features/review/use-review-actions";
import { useJobId } from "@/hooks/use-job-id";

export function DeleteCandidatesRoute() {
  const jobId = useJobId();
  const photos = usePhotos(jobId, { filter: { delete_candidate: true }, page: 1, pageSize: 200 });
  const mutate = usePhotoMutation(jobId);
  const items = photos.data?.items ?? [];

  return (
    <>
      <Hero
        title="Delete candidate review."
        copy="reject と低評価を分けて確認し、削除候補から戻す操作を短い導線にします。"
        badge="Delete Candidates"
        right={<div className="pill">{photos.data?.total ?? items.length} candidates</div>}
      />
      <Panel title="Candidates" copy={`${items.length} loaded`}>
        <div className="photo-grid">
          {items.map((photo) => {
            const reason = photo.selection_status === "rejected" ? "Rejected" : "★1";
            return (
              <div key={photo.photo_id} className="candidate-review-item">
                <div className="meta-row">
                  <span className="score-chip">{reason}</span>
                  <span className="score-chip">Reviewed {photo.reviewed_flag ? "yes" : "no"}</span>
                  {photo.group_id ? (
                    <Link className="button secondary" to={`/groups/${photo.group_id}?job=${jobId}`}>
                      Group
                    </Link>
                  ) : null}
                </div>
                <PhotoCard photo={photo} />
                <div className="actions">
                  <button className="button secondary" type="button" onClick={() => mutate.mutate({ photoId: photo.photo_id, selection_status: "normal", rating: null })}>
                    Remove Candidate
                  </button>
                  <button className="button warning" type="button" onClick={() => mutate.mutate({ photoId: photo.photo_id, selection_status: "rejected", rating: null, reviewed_flag: true })}>
                    Confirm Reject
                  </button>
                  <button className="button secondary" type="button" onClick={() => mutate.mutate({ photoId: photo.photo_id, reviewed_flag: !photo.reviewed_flag })}>
                    Toggle Reviewed
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        {!items.length ? <div className="empty">No delete candidates.</div> : null}
      </Panel>
    </>
  );
}
