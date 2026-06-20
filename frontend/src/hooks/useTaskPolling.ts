import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { GenerationTask } from "@/types";

export function useTaskPolling(taskId: string | null) {
  return useQuery({
    queryKey: ["task", taskId],
    queryFn: async () => {
      const res = await apiClient.get<GenerationTask>(`/tasks/${taskId}`);
      return res.data;
    },
    enabled: !!taskId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 2000;
      if (data.status === "completed" || data.status === "failed") return false;
      return 2000;
    },
  });
}
