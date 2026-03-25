import { useMutation } from "@tanstack/react-query";

import { api } from "@/lib/api";

export function useXmpExport() {
  return useMutation({
    mutationFn: (payload: { jobId: string; dryRun: boolean }) =>
      api.exportXmp({ job_id: payload.jobId, dry_run: payload.dryRun, conflict_policy: "skip" }),
  });
}

export function useResultsExport() {
  return useMutation({
    mutationFn: (payload: { jobId: string; format: "csv" | "json" }) => api.exportResults({ job_id: payload.jobId, format: payload.format }),
  });
}
