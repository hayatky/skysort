import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { ReanalyzeScope } from "@skysort/client";
import { api } from "@/lib/api";

export function usePhotoMutation(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { photoId: string; rating?: number | null; selection_status?: "normal" | "rejected"; pick_flag?: boolean; best_cut_flag?: boolean; reviewed_flag?: boolean }) => {
      const { photoId, ...changes } = payload;
      return api.updatePhoto(photoId, { job_id: jobId, ...changes });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["groups", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["photos", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["progress", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["group"] }),
      ]);
    },
  });
}

export function useReanalyzePhoto(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: string | { photoId: string; scope: ReanalyzeScope }) => {
      const photoId = typeof payload === "string" ? payload : payload.photoId;
      const scope = typeof payload === "string" ? "full" : payload.scope;
      return api.reanalyzePhoto(photoId, { job_id: jobId, scope });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["groups", jobId] });
      await queryClient.invalidateQueries({ queryKey: ["photos", jobId] });
    },
  });
}

export function useReanalyzeGroup(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: string | { groupId: string; scope: ReanalyzeScope }) => {
      const groupId = typeof payload === "string" ? payload : payload.groupId;
      const scope = typeof payload === "string" ? "full" : payload.scope;
      return api.reanalyzeGroup(groupId, { job_id: jobId, scope });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["groups", jobId] });
      await queryClient.invalidateQueries({ queryKey: ["photos", jobId] });
    },
  });
}

export function useRetryFailure(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (failureId: string) => api.retryFailure(jobId, failureId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["failures", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["groups", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["photos", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["progress", jobId] }),
      ]);
    },
  });
}

export function useMergeGroup(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { groupId: string; targetGroupId: string }) => api.mergeGroup(payload.groupId, { target_group_id: payload.targetGroupId }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["groups", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["photos", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["group"] }),
      ]);
    },
  });
}

export function useSplitGroup(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { groupId: string; photoIds: string[] }) => api.splitGroup(payload.groupId, { photo_ids: payload.photoIds }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["groups", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["photos", jobId] }),
        queryClient.invalidateQueries({ queryKey: ["group"] }),
      ]);
    },
  });
}
