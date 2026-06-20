import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import apiClient from "@/lib/api-client";
import { useAuthStore } from "@/lib/auth-store";
import type { TokenResponse } from "@/types";

export function useLogin() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  return useMutation({
    mutationFn: async (data: { email: string; password: string }) => {
      const res = await apiClient.post<TokenResponse>("/auth/login", data);
      return res.data;
    },
    onSuccess: (data) => {
      login(data.access_token, data.user);
      navigate("/");
    },
  });
}

export function useRegister() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  return useMutation({
    mutationFn: async (data: { username: string; email: string; password: string }) => {
      const res = await apiClient.post<TokenResponse>("/auth/register", data);
      return res.data;
    },
    onSuccess: (data) => {
      login(data.access_token, data.user);
      navigate("/");
    },
  });
}
