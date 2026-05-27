import { useQuery } from "@tanstack/react-query";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export function useProgress(jobId: string) {
  return useQuery({
    queryKey: ["progress", jobId],
    queryFn: () => api.getProgress(jobId),
    enabled: Boolean(jobId),
    refetchInterval: 1_500,
  });
}

export function useFailures(jobId: string) {
  return useQuery({
    queryKey: ["failures", jobId],
    queryFn: () => api.getFailures(jobId),
    enabled: Boolean(jobId),
  });
}

export function useCancelJob(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.cancelJob(jobId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["progress", jobId] });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useRetryJob(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.retryJob(jobId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
