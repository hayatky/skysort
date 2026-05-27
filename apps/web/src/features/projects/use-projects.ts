import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
    refetchInterval: 5_000,
  });
}

export function useProjectJobs(projectId: string) {
  return useQuery({
    queryKey: ["project-jobs", projectId],
    queryFn: () => api.listProjectJobs(projectId),
    enabled: Boolean(projectId),
  });
}

export function useStartProjectAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => api.startProjectAnalyze(projectId, { reuse_cache: true }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
