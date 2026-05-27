import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export function useJobId() {
  const [params] = useSearchParams();
  return useMemo(() => params.get("job") ?? "", [params]);
}

export function storeJobId(jobId: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem("skysort:lastJobId", jobId);
}

export function getStoredJobId() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("skysort:lastJobId") ?? "";
}
