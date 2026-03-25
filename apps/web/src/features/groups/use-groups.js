import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
export function useGroups(jobId) {
    return useQuery({
        queryKey: ["groups", jobId],
        queryFn: () => api.listGroups(jobId),
        enabled: Boolean(jobId),
    });
}
export function useGroup(groupId) {
    return useQuery({
        queryKey: ["group", groupId],
        queryFn: () => api.getGroup(groupId),
        enabled: Boolean(groupId),
    });
}
export function usePhotos(jobId) {
    return useQuery({
        queryKey: ["photos", jobId],
        queryFn: () => api.listPhotos(jobId),
        enabled: Boolean(jobId),
    });
}
