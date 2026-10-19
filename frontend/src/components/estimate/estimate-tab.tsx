"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Copy, Download, GitCompare, Loader2, Lock, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, StatusBadge } from "@/components/common";
import { AddTaskDialog } from "@/components/estimate/add-task-dialog";
import { AgentPanel } from "@/components/estimate/agent-panel";
import { EstimateTable, type Highlight } from "@/components/estimate/estimate-table";
import { SummaryPanel } from "@/components/estimate/summary-panel";
import { WhySheet } from "@/components/estimate/why-sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  errorToast,
  qk,
  useCategories,
  useCompare,
  useEstimate,
  useProposals,
  useRoles,
  useSummary,
} from "@/hooks/queries";
import { useEstimateJobs } from "@/hooks/estimate-jobs";
import { api, downloadUrl } from "@/lib/api";
import { factor } from "@/lib/format";
import type { Estimate, ProposalOp, TaskOut } from "@/lib/types";

function label(e: Estimate) {
  return `v${e.version} · ${e.status} · ${e.learning_enabled ? "learned" : "raw LLM"}`;
}

function CompareView({ estimateId, other, estimates }: { estimateId: string; other: string; estimates: Estimate[] }) {
  const { data, isLoading } = useCompare(estimateId, other);
  if (isLoading || !data) return <Skeleton className="h-64" />;
  const a = estimates.find((e) => e.id === other);
  const b = estimates.find((e) => e.id === estimateId);
  const tot = (lo: (number | null)[], hi: (number | null)[]) =>
    (lo.reduce<number>((s, v) => s + (v ?? 0), 0) + hi.reduce<number>((s, v) => s + (v ?? 0), 0)) / 2;
  const totA = tot(data.rows.map((r) => r.a_min), data.rows.map((r) => r.a_max));
  const totB = tot(data.rows.map((r) => r.b_min), data.rows.map((r) => r.b_max));
  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Task</TableHead>
            <TableHead>Category</TableHead>
            <TableHead className="text-right">{a ? label(a) : "A"}</TableHead>
            <TableHead className="text-right">{b ? label(b) : "B"}</TableHead>
            <TableHead className="text-right">Applied factor</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.rows.map((r) => {
            const ma = r.a_min !== null && r.a_max !== null ? (r.a_min + r.a_max) / 2 : null;
            const mb = r.b_min !== null && r.b_max !== null ? (r.b_min + r.b_max) / 2 : null;
            const up = ma !== null && mb !== null && mb > ma * 1.05;
            const down = ma !== null && mb !== null && mb < ma * 0.95;
            return (
              <TableRow key={r.ai_key ?? r.title}>
                <TableCell>{r.title}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{r.category}</TableCell>
                <TableCell className="text-right tabular-nums">{ma !== null ? `${r.a_min}–${r.a_max}` : "—"}</TableCell>
                <TableCell className={`text-right tabular-nums ${up ? "text-amber-600" : down ? "text-sky-600" : ""}`}>
                  {mb !== null ? `${r.b_min}–${r.b_max}` : "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">{factor(r.factor)}</TableCell>
              </TableRow>
            );
          })}
          <TableRow className="font-medium">
            <TableCell colSpan={2}>Total (mid)</TableCell>
            <TableCell className="text-right tabular-nums">{totA.toFixed(0)} h</TableCell>
            <TableCell className="text-right tabular-nums">{totB.toFixed(0)} h</TableCell>
            <TableCell className="text-right tabular-nums">{totA ? factor(totB / totA) : "—"}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  );
}

export function EstimateTab({
  projectId,
  estimates,
  estimateId,
  onSelect,
  agentRequest = 0,
}: {
  projectId: string;
  estimates: Estimate[];
  estimateId: string | null;
  onSelect: (id: string) => void;
  agentRequest?: number;
}) {
  const { data: tree, isLoading, error } = useEstimate(estimateId);
  const { data: summary } = useSummary(estimateId);
  const { data: roles } = useRoles();
  const { data: categories } = useCategories();
  const { data: proposals } = useProposals(estimateId);
  const [why, setWhy] = useState<TaskOut | null>(null);
  const [agent, setAgentState] = useState(
    () => typeof window !== "undefined" && window.localStorage.getItem("calibr.agentOpen") === "1",
  );
  const setAgent = useCallback((v: boolean | ((a: boolean) => boolean)) => {
    setAgentState((prev) => {
      const next = typeof v === "function" ? v(prev) : v;
      window.localStorage.setItem("calibr.agentOpen", next ? "1" : "0");
      return next;
    });
  }, []);
  const [agentHl, setAgentHl] = useState<Highlight>({});
  const hlTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flash = useCallback((ids: string[]) => {
    if (!ids.length) return;
    setAgentHl(Object.fromEntries(ids.map((id) => [id, "agent" as const])));
    if (hlTimer.current) clearTimeout(hlTimer.current);
    hlTimer.current = setTimeout(() => setAgentHl({}), 4000);
  }, []);
  const showTasks = useCallback(
    (ids: string[]) => {
      flash(ids);
      document.querySelector(`[data-task-id="${ids[0]}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    },
    [flash],
  );
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- open on explicit request (after generation)
    if (agentRequest) setAgent(true);
  }, [agentRequest, setAgent]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setAgent((a) => !a);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setAgent]);
  const [compareWith, setCompareWith] = useState<string | null>(null);
  const [showRemoved, setShowRemoved] = useState(false);
  const qc = useQueryClient();
  const { start: startEstimate, isEstimating } = useEstimateJobs();
  const pendingIds = useMemo(
    () =>
      (tree?.modules ?? [])
        .filter((m) => !m.removed)
        .flatMap((m) => m.tasks ?? [])
        .filter((t) => !t.baseline && t.origin !== "ai" && t.enabled && !t.removed && t.min_hours === 0 && t.max_hours === 0)
        .map((t) => t.id),
    [tree],
  );
  const estimatingBatch = !!estimateId && pendingIds.some((id) => isEstimating(estimateId, id));

  const highlight = useMemo(() => {
    const h: Highlight = {};
    for (const p of proposals ?? []) {
      for (const op of p.ops as unknown as ProposalOp[]) {
        if (op.status !== "pending") continue;
        if (op.type === "remove_task" && op.payload.task_id) h[op.payload.task_id] = "remove";
        if (op.type === "update_task" && op.payload.task_id) h[op.payload.task_id] = "update";
        if (op.type === "bulk_adjust" && Array.isArray(op.payload.changes))
          for (const c of op.payload.changes as { task_id: string }[]) h[c.task_id] = "update";
      }
    }
    return { ...h, ...agentHl };
  }, [proposals, agentHl]);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: qk.estimates(projectId) });
    void qc.invalidateQueries({ queryKey: qk.project(projectId) });
    void qc.invalidateQueries({ queryKey: ["projects"] });
  };
  const finalize = useMutation({
    mutationFn: () => api<Estimate>(`/estimates/${estimateId}/finalize`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Finalized — edit-layer calibration updated (see Insights)");
      refresh();
      void qc.invalidateQueries({ queryKey: qk.estimate(estimateId ?? "") });
      void qc.invalidateQueries({ queryKey: ["calibration"] });
      void qc.invalidateQueries({ queryKey: ["timeline"] });
      void qc.invalidateQueries({ queryKey: ["rules"] });
    },
    onError: errorToast,
  });
  const clone = useMutation({
    mutationFn: () => api<Estimate>(`/estimates/${estimateId}/clone`, { method: "POST" }),
    onSuccess: (e) => {
      refresh();
      onSelect(e.id);
      toast.success(`Created draft v${e.version}`);
    },
    onError: errorToast,
  });

  if (!estimates.length)
    return <EmptyState title="No estimate yet" description="Upload a brief in Overview and click “Generate estimate”." />;
  if (error) return <ErrorState error={error} />;

  const est = tree?.estimate;
  const readOnly = est?.status === "final";
  const others = estimates.filter((e) => e.id !== estimateId);

  const toolbar = (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        value={estimateId}
        onValueChange={(v) => v && onSelect(v)}
        items={estimates.map((e) => ({ value: e.id, label: label(e) }))}
      >
        <SelectTrigger size="sm" className="w-60">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {estimates.map((e) => (
            <SelectItem key={e.id} value={e.id}>
              {label(e)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {est && <StatusBadge status={est.status} />}
      {est && (
        <Badge variant="outline">{est.learning_enabled ? "with learning" : "raw LLM (no learning)"}</Badge>
      )}
      <Select
        value={compareWith ?? "none"}
        onValueChange={(v) => setCompareWith(v && v !== "none" ? v : null)}
        items={[{ value: "none", label: "No comparison" }, ...others.map((e) => ({ value: e.id, label: `Compare with ${label(e)}` }))]}
      >
        <SelectTrigger size="sm" className="w-64">
          <GitCompare className="size-4" />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none">No comparison</SelectItem>
          {others.map((e) => (
            <SelectItem key={e.id} value={e.id}>
              Compare with {label(e)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="flex items-center gap-1.5">
        <Switch id="removed" size="sm" checked={showRemoved} onCheckedChange={setShowRemoved} />
        <Label htmlFor="removed" className="text-xs">
          Show removed
        </Label>
      </div>
      <div className="ml-auto flex items-center gap-2">
        {!readOnly && tree && roles && categories && (
          <AddTaskDialog estimateId={tree.estimate.id} modules={tree.modules} roles={roles} categories={categories} />
        )}
        {!readOnly && estimateId && pendingIds.length > 0 && (
          <Button size="sm" onClick={() => void startEstimate(estimateId, pendingIds)} disabled={estimatingBatch}>
            {estimatingBatch ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {estimatingBatch ? "Estimating…" : `AI estimate ${pendingIds.length} added task${pendingIds.length > 1 ? "s" : ""}`}
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button size="sm" variant="outline" />}>
            <Download /> Export
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onClick={() => window.open(downloadUrl(`/estimates/${estimateId}/export?format=xlsx`))}>
              Excel (.xlsx)
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => window.open(downloadUrl(`/estimates/${estimateId}/export?format=csv`))}>
              CSV (flat)
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button size="sm" variant="outline" onClick={() => clone.mutate()} disabled={!estimateId}>
          <Copy /> Clone
        </Button>
        <Button
          size="sm"
          variant={agent ? "secondary" : "outline"}
          onClick={() => setAgent((a) => !a)}
          title="Toggle agent (Ctrl/⌘+J)"
          aria-keyshortcuts="Control+J Meta+J"
        >
          <Bot /> Agent
        </Button>
        {!readOnly && (
          <AlertDialog>
            <AlertDialogTrigger render={<Button size="sm" />}>
              <Lock /> Finalize
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Finalize this estimate?</AlertDialogTitle>
                <AlertDialogDescription>
                  The estimate becomes read-only and the quoted version. Every difference between the AI baseline and your
                  final numbers updates the edit-layer calibration (always measured against the raw LLM output), and the
                  system may propose new lessons for review.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => finalize.mutate()}>Finalize & learn</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>
    </div>
  );

  const main = (
    <div className={agent ? "grid gap-4" : "grid gap-4 xl:grid-cols-[1fr_320px]"}>
      <div className="min-w-0 overflow-x-auto">
        {isLoading || !tree || !roles || !categories ? (
          <Skeleton className="h-96" />
        ) : compareWith && estimateId ? (
          <CompareView estimateId={estimateId} other={compareWith} estimates={estimates} />
        ) : (
          <EstimateTable
            tree={tree}
            roles={roles}
            categories={categories}
            highlight={highlight}
            showRemoved={showRemoved}
            onWhy={setWhy}
          />
        )}
      </div>
      <SummaryPanel summary={summary} roles={roles ?? []} />
    </div>
  );

  return (
    <div className="space-y-3">
      {toolbar}
      {agent && estimateId ? (
        <ResizablePanelGroup orientation="horizontal" className="h-[calc(100vh-11rem)] min-h-[560px] rounded-lg border">
          <ResizablePanel defaultSize="68%" minSize="40%">
            <div className="h-full overflow-auto p-3">{main}</div>
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize="32%" minSize="22%">
            <AgentPanel
              estimateId={estimateId}
              projectId={projectId}
              readOnly={!!readOnly}
              onClose={() => setAgent(false)}
              onPatch={flash}
              onShowTasks={showTasks}
            />
          </ResizablePanel>
        </ResizablePanelGroup>
      ) : (
        main
      )}
      <WhySheet task={why} onClose={() => setWhy(null)} />
    </div>
  );
}
