import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { GenerationTask } from "@/types";

export function useTasks(gameId: string | null) {
  return useQuery({
    queryKey: ["tasks", gameId],
    queryFn: async () => {
      const res = await apiClient.get<GenerationTask[]>(`/tasks/games/${gameId}`);
      return res.data;
    },
    enabled: !!gameId,
  });
}
