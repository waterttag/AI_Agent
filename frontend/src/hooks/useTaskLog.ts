import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";

interface TaskLog {
  task_id: string;
  status: string;
  progress: number;
  prompt_summary: string | null;
  agent_steps: string[];
  started_at: string | null;
  completed_at: string | null;
}

export function useTaskLog(gameId: string | null) {
  return useQuery({
    queryKey: ["task-log", gameId],
    queryFn: async () => {
      const res = await apiClient.get<TaskLog>(`/tasks/games/${gameId}/log`);
      return res.data;
    },
    enabled: !!gameId,
  });
}
