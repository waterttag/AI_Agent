import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { GameListResponse, Game, GameAsset } from "@/types";

export function useGames(tag?: string) {
  return useQuery({
    queryKey: ["games", tag],
    queryFn: async () => {
      const params: Record<string, string> = { status: "published", size: "50" };
      if (tag) params.tag = tag;
      const res = await apiClient.get<GameListResponse>("/games", { params });
      return res.data;
    },
  });
}

export function useGame(gameId: string) {
  return useQuery({
    queryKey: ["game", gameId],
    queryFn: async () => {
      const res = await apiClient.get<Game>(`/games/${gameId}`);
      return res.data;
    },
    enabled: !!gameId,
  });
}

export function useGameAssets(gameId: string) {
  return useQuery({
    queryKey: ["game-assets", gameId],
    queryFn: async () => {
      const res = await apiClient.get<GameAsset[]>(`/games/${gameId}/assets`);
      return res.data;
    },
    enabled: !!gameId,
  });
}
