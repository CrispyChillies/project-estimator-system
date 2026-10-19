"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { errorToast } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { AgentMsg, AgentOperationOut, AgentSessionOut, ApplyMode, ProjectMemoryOut } from "@/lib/types";

export const ak = {
  sessions: (estimateId: string) => ["agent-sessions", estimateId] as const,
  messages: (sid: string) => ["agent-messages", sid] as const,
  ops: (sid: string) => ["agent-ops", sid] as const,
  memories: (estimateId: string) => ["agent-memories", estimateId] as const,
};

export const useAgentSessions = (estimateId: string) =>
  useQuery({
    queryKey: ak.sessions(estimateId),
    queryFn: () => api<AgentSessionOut[]>(`/estimates/${estimateId}/agent/sessions`),
    refetchInterval: (q) => (q.state.data?.some((s) => s.run_state === "running") ? 1500 : false),
  });

export const useAgentMessages = (sid: string | null, polling = false) =>
  useQuery({
    queryKey: ak.messages(sid ?? ""),
    queryFn: () => api<AgentMsg[]>(`/agent/sessions/${sid}/messages`),
    enabled: !!sid,
    refetchInterval: polling ? 1500 : false,
  });

export const useAgentOps = (sid: string | null) =>
  useQuery({
    queryKey: ak.ops(sid ?? ""),
    queryFn: () => api<AgentOperationOut[]>(`/agent/sessions/${sid}/operations`),
    enabled: !!sid,
  });

export const useMemories = (estimateId: string) =>
  useQuery({
    queryKey: ak.memories(estimateId),
    queryFn: () => api<ProjectMemoryOut[]>(`/estimates/${estimateId}/memories`),
  });

export function useCreateSession(estimateId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { title?: string; apply_mode?: ApplyMode }) =>
      api<AgentSessionOut>(`/estimates/${estimateId}/agent/sessions`, { method: "POST", json: body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ak.sessions(estimateId) }),
    onError: errorToast,
  });
}

export function usePatchSession(estimateId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<AgentSessionOut> }) =>
      api<AgentSessionOut>(`/agent/sessions/${id}`, { method: "PATCH", json: patch }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ak.sessions(estimateId) }),
    onError: errorToast,
  });
}

export function useDeleteSession(estimateId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/agent/sessions/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ak.sessions(estimateId) }),
    onError: errorToast,
  });
}
