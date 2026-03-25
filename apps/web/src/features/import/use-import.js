import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
export function useAIHealth() {
    return useQuery({
        queryKey: ["ai-health"],
        queryFn: () => api.getAIHealth(),
        refetchInterval: 20_000,
    });
}
export function useImportJob() {
    return useMutation({
        mutationFn: async (payload) => {
            const imported = await api.importFolder({
                root_path: payload.rootPath,
                recursive: payload.recursive,
                reuse_cache: payload.reuseCache,
                file_types: payload.fileTypes,
            });
            await api.startAnalyze(imported.job_id, { reuse_cache: payload.reuseCache });
            return imported;
        },
    });
}
