import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export function useGroups(jobId: string, options: { filter?: Record<string, unknown>; page?: number; pageSize?: number } = {}) {
  return useQuery({
    queryKey: ["groups", jobId, options.filter ?? {}, options.page ?? 1, options.pageSize ?? 100],
    queryFn: () => api.listGroups(jobId, { ...options, pageSize: options.pageSize ?? 100 }),
    enabled: Boolean(jobId),
  });
}

export function useGroup(groupId: string) {
  return useQuery({
    queryKey: ["group", groupId],
    queryFn: () => api.getGroup(groupId),
    enabled: Boolean(groupId),
  });
}

export function usePhotos(jobId: string, options: { filter?: Record<string, unknown>; page?: number; pageSize?: number } = {}) {
  return useQuery({
    queryKey: ["photos", jobId, options.filter ?? {}, options.page ?? 1, options.pageSize ?? 100],
    queryFn: () => api.listPhotos(jobId, { includeMissing: true, ...options, pageSize: options.pageSize ?? 100 }),
    enabled: Boolean(jobId),
  });
}
