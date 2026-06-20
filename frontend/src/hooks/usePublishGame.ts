import { useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { Game } from "@/types";

export function usePublishGame() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (gameId: string) => {
      const res = await apiClient.put<Game>(`/games/${gameId}`, { status: "published" });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["game"] });
      queryClient.invalidateQueries({ queryKey: ["games"] });
    },
  });
}
