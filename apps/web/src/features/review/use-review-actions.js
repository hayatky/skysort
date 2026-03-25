import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
export function usePhotoMutation(jobId) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload) => api.updatePhoto(payload.photoId, { job_id: jobId, ...payload }),
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
export function useReanalyzePhoto(jobId) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (photoId) => api.reanalyzePhoto(photoId, { job_id: jobId, scope: "full" }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["groups", jobId] });
            await queryClient.invalidateQueries({ queryKey: ["photos", jobId] });
        },
    });
}
export function useReanalyzeGroup(jobId) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (groupId) => api.reanalyzeGroup(groupId, { job_id: jobId, scope: "full" }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["groups", jobId] });
            await queryClient.invalidateQueries({ queryKey: ["photos", jobId] });
        },
    });
}
