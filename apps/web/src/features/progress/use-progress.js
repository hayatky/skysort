import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
export function useProgress(jobId) {
    return useQuery({
        queryKey: ["progress", jobId],
        queryFn: () => api.getProgress(jobId),
        enabled: Boolean(jobId),
        refetchInterval: 1_500,
    });
}
export function useFailures(jobId) {
    return useQuery({
        queryKey: ["failures", jobId],
        queryFn: () => api.getFailures(jobId),
        enabled: Boolean(jobId),
    });
}
