import { useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { Game, GameAsset, GenerationTask } from "@/types";

export function useCreateGame() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { title: string; description: string; tags: string[]; prompt_text: string }) => {
      const res = await apiClient.post<Game>("/games", data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["games"] });
    },
  });
}

export function useUploadAsset() {
  return useMutation({
    mutationFn: async ({ gameId, file }: { gameId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      const res = await apiClient.post<GameAsset>(`/games/${gameId}/assets`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return res.data;
    },
  });
}

export function useGenerateGame() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ gameId, promptText }: { gameId: string; promptText: string }) => {
      const res = await apiClient.post<GenerationTask>(`/games/${gameId}/generate`, {
        prompt_text: promptText,
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["games"] });
    },
  });
}
