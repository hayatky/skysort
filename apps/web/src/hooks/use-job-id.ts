import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export function useJobId() {
  const [params] = useSearchParams();
  return useMemo(() => params.get("job") ?? "", [params]);
}
