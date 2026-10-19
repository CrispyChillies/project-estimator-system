"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import type {
  Accuracy,
  AccuracyPoint,
  ActualRow,
  Assumption,
  BacktestDetail,
  BacktestRun,
  CalibrationRow,
  Category,
  Chunk,
  CompareOut,
  DocumentOut,
  EditEvent,
  Estimate,
  EstimateSummary,
  EstimateTree,
  Job,
  LearningSettings,
  Project,
  ProjectListItem,
  Proposal,
  Question,
  Role,
  Rule,
  StructuralSignals,
  TaskOut,
  TaskPatch,
  TimelinePoint,
  Unplanned,
} from "@/lib/types";

export function errorToast(e: unknown) {
  toast.error(e instanceof ApiError ? e.message : "Something went wrong");
}

export const qk = {
  projects: (s?: string, q?: string) => ["projects", s ?? "", q ?? ""] as const,
  project: (id: string) => ["project", id] as const,
  documents: (id: string) => ["documents", id] as const,
  estimates: (pid: string) => ["estimates", pid] as const,
  estimate: (id: string) => ["estimate", id] as const,
  summary: (id: string) => ["summary", id] as const,
};

export const useRoles = () => useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles"), staleTime: 60_000 });
export const useCategories = () =>
  useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/categories"), staleTime: 60_000 });

export const useProjects = (status?: string, search?: string) =>
  useQuery({
    queryKey: qk.projects(status, search),
    queryFn: () => {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      if (search) p.set("search", search);
      return api<ProjectListItem[]>(`/projects?${p}`);
    },
  });

export const useProject = (id: string) =>
  useQuery({ queryKey: qk.project(id), queryFn: () => api<Project>(`/projects/${id}`) });

export const useDocuments = (id: string) =>
  useQuery({ queryKey: qk.documents(id), queryFn: () => api<DocumentOut[]>(`/projects/${id}/documents`) });

export const useChunks = (docId: string | null) =>
  useQuery({
    queryKey: ["chunks", docId],
    queryFn: () => api<Chunk[]>(`/documents/${docId}/chunks`),
    enabled: !!docId,
  });

export const useChunkLookup = (ids: string[]) =>
  useQuery({
    queryKey: ["chunk-lookup", ...ids],
    queryFn: () => api<Chunk[]>("/chunks/lookup", { method: "POST", json: ids }),
    enabled: ids.length > 0,
  });

export const useEstimates = (pid: string) =>
  useQuery({ queryKey: qk.estimates(pid), queryFn: () => api<Estimate[]>(`/projects/${pid}/estimates`) });

export const useEstimate = (id: string | null) =>
  useQuery({ queryKey: qk.estimate(id ?? ""), queryFn: () => api<EstimateTree>(`/estimates/${id}`), enabled: !!id });

export const useSummary = (id: string | null) =>
  useQuery({
    queryKey: qk.summary(id ?? ""),
    queryFn: () => api<EstimateSummary>(`/estimates/${id}/summary`),
    enabled: !!id,
  });

export const useCompare = (id: string | null, other: string | null) =>
  useQuery({
    queryKey: ["compare", id, other],
    queryFn: () => api<CompareOut>(`/estimates/${id}/compare?with=${other}`),
    enabled: !!id && !!other,
  });

export const useActivity = (id: string | null, actor?: string) =>
  useQuery({
    queryKey: ["activity", id, actor ?? ""],
    queryFn: () => api<EditEvent[]>(`/estimates/${id}/activity${actor ? `?actor=${actor}` : ""}`),
    enabled: !!id,
  });

export const useQuestions = (id: string | null) =>
  useQuery({ queryKey: ["questions", id], queryFn: () => api<Question[]>(`/estimates/${id}/questions`), enabled: !!id });

export const useAssumptions = (id: string | null) =>
  useQuery({
    queryKey: ["assumptions", id],
    queryFn: () => api<Assumption[]>(`/estimates/${id}/assumptions`),
    enabled: !!id,
  });

export const useProposals = (id: string | null) =>
  useQuery({
    queryKey: ["proposals", id],
    queryFn: () => api<Proposal[]>(`/estimates/${id}/proposals?status=pending`),
    enabled: !!id,
  });

export const useActuals = (pid: string, enabled: boolean) =>
  useQuery({ queryKey: ["actuals", pid], queryFn: () => api<ActualRow[]>(`/projects/${pid}/actuals`), enabled });

export const useUnplanned = (pid: string) =>
  useQuery({ queryKey: ["unplanned", pid], queryFn: () => api<Unplanned[]>(`/projects/${pid}/unplanned`) });

export const useAccuracy = (pid: string, enabled: boolean) =>
  useQuery({ queryKey: ["accuracy", pid], queryFn: () => api<Accuracy>(`/projects/${pid}/accuracy`), enabled });

export const useCalibration = () =>
  useQuery({ queryKey: ["calibration"], queryFn: () => api<CalibrationRow[]>("/insights/calibration") });
export const useTimeline = () =>
  useQuery({ queryKey: ["timeline"], queryFn: () => api<TimelinePoint[]>("/insights/timeline") });
export const useAccuracyOverTime = () =>
  useQuery({ queryKey: ["accuracy-time"], queryFn: () => api<AccuracyPoint[]>("/insights/accuracy") });
export const useStructural = () =>
  useQuery({ queryKey: ["structural"], queryFn: () => api<StructuralSignals>("/insights/structural") });
export const useRules = () => useQuery({ queryKey: ["rules"], queryFn: () => api<Rule[]>("/rules") });

export const useBacktestRuns = () =>
  useQuery({ queryKey: ["backtest-runs"], queryFn: () => api<BacktestRun[]>("/backtest/runs") });
export const useBacktestRun = (id: string | null) =>
  useQuery({ queryKey: ["backtest-run", id], queryFn: () => api<BacktestDetail>(`/backtest/runs/${id}`), enabled: !!id });

export const useLearningSettings = () =>
  useQuery({ queryKey: ["learning-settings"], queryFn: () => api<LearningSettings>("/admin/learning") });


export interface AdminUsage {
  total_cost_usd: number;
  budget_usd: number;
  by_section: { key: string | null; calls: number; cost_usd: number; cache_hits: number }[];
}
export const useAdminUsage = () =>
  useQuery({ queryKey: ["admin-usage"], queryFn: () => api<AdminUsage>("/admin/llm-usage") });

export function useJob(id: string | null) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => api<Job>(`/jobs/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && ["done", "failed"].includes(q.state.data.status) ? false : 800),
  });
}

/** Invalidate everything that depends on an estimate's tasks. */
export function useInvalidateEstimate() {
  const qc = useQueryClient();
  return (estimateId: string) => {
    void qc.invalidateQueries({ queryKey: qk.estimate(estimateId) });
    void qc.invalidateQueries({ queryKey: qk.summary(estimateId) });
    void qc.invalidateQueries({ queryKey: ["activity", estimateId] });
    void qc.invalidateQueries({ queryKey: ["proposals", estimateId] });
    void qc.invalidateQueries({ queryKey: ["compare"] });
  };
}

export function usePatchTask(estimateId: string) {
  const invalidate = useInvalidateEstimate();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: TaskPatch }) =>
      api<TaskOut>(`/tasks/${id}`, { method: "PATCH", json: patch }),
    onSuccess: () => invalidate(estimateId),
    onError: errorToast,
  });
}
