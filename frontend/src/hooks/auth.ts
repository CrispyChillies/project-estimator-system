"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { api, ApiError } from "@/lib/api";

export interface Me {
  id: string;
  name: string;
  email: string;
  role: "admin" | "member";
  onboarding_state: Record<string, unknown>;
  last_login_at: string | null;
}

export const meKey = ["me"] as const;

export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: async () => {
      try {
        return await api<Me>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useSignOut() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/auth/logout", { method: "POST" }),
    onSettled: () => {
      qc.clear();
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload drops cached private data
      window.location.href = "/signin";
    },
  });
}

export function useOnboarding() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const state = (me?.onboarding_state ?? {}) as Record<string, unknown>;
  const update = useMutation({
    mutationFn: (patch: Record<string, unknown>) => api<Me>("/auth/me/onboarding", { method: "PUT", json: { state: patch } }),
    onSuccess: (m) => qc.setQueryData(meKey, m),
  });
  const { mutate } = update;
  const apply = useCallback((patch: Record<string, unknown>) => mutate(patch), [mutate]);
  return { state, update: apply };
}
