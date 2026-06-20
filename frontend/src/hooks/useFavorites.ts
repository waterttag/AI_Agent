import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";

export function useFavoriteGameIds() {
  return useQuery({
    queryKey: ["favorites"],
    queryFn: async () => {
      const res = await apiClient.get<string[]>("/auth/me/favorites");
      return res.data;
    },
  });
}

export function useFavoriteStatus(gameId: string) {
  return useQuery({
    queryKey: ["favorite", gameId],
    queryFn: async () => {
      const res = await apiClient.get<{ favorited: boolean; count: number }>(`/games/${gameId}/favorite`);
      return res.data;
    },
  });
}

export function useToggleFavorite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (gameId: string) => {
      const res = await apiClient.post<{ favorited: boolean }>(`/games/${gameId}/favorite`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      queryClient.invalidateQueries({ queryKey: ["favorite"] });
    },
  });
}
