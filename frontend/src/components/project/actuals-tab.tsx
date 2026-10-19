"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, PackageCheck, Plus, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common";
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
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorToast, qk, useAccuracy, useActuals, useUnplanned } from "@/hooks/queries";
import { HelpTip } from "@/components/onboarding";
import { api, ApiError, downloadUrl } from "@/lib/api";
import { hours, pct } from "@/lib/format";
import type { Estimate, Project } from "@/lib/types";

function variance(min: number, max: number, actual: number | null) {
  if (actual === null) return "";
  if (actual > max) return "text-rose-700 dark:text-rose-400";
  if (actual < min) return "text-sky-700 dark:text-sky-400";
  return "text-emerald-700 dark:text-emerald-400";
}

const REASON_LABEL: Record<string, string> = {
  missed_requirement: "missed requirement",
  clarified_scope: "clarified scope",
  change_request: "change request",
  other: "other",
  unspecified: "no reason",
};

export function ActualsTab({ project, estimates }: { project: Project; estimates: Estimate[] }) {
  const hasFinal = estimates.some((e) => e.status === "final");
  const delivered = project.status === "delivered";
  const { data: rows, isLoading } = useActuals(project.id, hasFinal);
  const { data: unplanned } = useUnplanned(project.id);
  const { data: acc } = useAccuracy(project.id, hasFinal);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("missed_requirement");
  const [uh, setUh] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const refresh = () => {
    for (const k of [["actuals", project.id], ["accuracy", project.id], ["unplanned", project.id], ["projects"]])
      void qc.invalidateQueries({ queryKey: k });
  };
  const save = useMutation({
    mutationFn: () =>
      api<void>(`/projects/${project.id}/actuals`, {
        method: "PUT",
        json: Object.entries(draft)
          .filter(([, v]) => v !== "")
          .map(([task_id, v]) => ({ task_id, actual_hours: Number(v) })),
      }),
    onSuccess: () => {
      setDraft({});
      refresh();
      toast.success("Actuals saved");
    },
    onError: errorToast,
  });
  const importCsv = useMutation({
    mutationFn: (f: File) => {
      const fd = new FormData();
      fd.append("file", f);
      return api<{ imported: number }>(`/projects/${project.id}/actuals/import`, { method: "POST", body: fd });
    },
    onSuccess: (r) => {
      refresh();
      toast.success(`Imported ${r.imported} rows`);
    },
    onError: (e) => {
      if (e instanceof ApiError && Array.isArray(e.details))
        toast.error(`${e.message}: ${(e.details as { line: number; error: string }[]).slice(0, 3).map((d) => `line ${d.line} ${d.error}`).join("; ")}`);
      else errorToast(e);
    },
  });
  const addUnplanned = useMutation({
    mutationFn: () => api(`/projects/${project.id}/unplanned`, { method: "POST", json: { title, hours: Number(uh), reason } }),
    onSuccess: () => {
      setTitle("");
      setUh("");
      refresh();
    },
    onError: errorToast,
  });
  const delUnplanned = useMutation({
    mutationFn: (id: string) => api(`/unplanned/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  const deliver = useMutation({
    mutationFn: () => api<Project>(`/projects/${project.id}/deliver`, { method: "POST" }),
    onSuccess: () => {
      refresh();
      void qc.invalidateQueries({ queryKey: qk.project(project.id) });
      void qc.invalidateQueries({ queryKey: ["calibration"] });
      void qc.invalidateQueries({ queryKey: ["timeline"] });
      void qc.invalidateQueries({ queryKey: ["rules"] });
      toast.success("Delivered — actual-layer calibration updated and lessons proposed");
    },
    onError: errorToast,
  });

  if (!hasFinal)
    return <EmptyState title="Finalize an estimate first" description="Actuals are recorded against the final (quoted) estimate." />;
  if (isLoading) return <Skeleton className="h-64" />;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => save.mutate()} disabled={!Object.keys(draft).length || save.isPending}>
            Save actuals
          </Button>
          <Button size="sm" variant="outline" onClick={() => window.open(downloadUrl(`/projects/${project.id}/actuals/template.csv`))}>
            <Download /> CSV template
          </Button>
          <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()}>
            <Upload /> Import CSV
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) importCsv.mutate(f);
              e.target.value = "";
            }}
          />
          <AlertDialog>
            <AlertDialogTrigger render={<Button size="sm" className="ml-auto" variant={delivered ? "outline" : "default"} />}>
              <PackageCheck /> {delivered ? "Re-run delivery learning" : "Mark delivered"}
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Mark project delivered?</AlertDialogTitle>
                <AlertDialogDescription>
                  Actual hours are compared with the raw AI baseline to update the actual-layer calibration (ground truth).
                  Unplanned work is reported separately as scope creep and is not mixed into estimation error.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => deliver.mutate()}>Deliver & learn</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Module</TableHead>
                <TableHead>Task</TableHead>
                <TableHead className="text-right">Estimate</TableHead>
                <TableHead className="w-28 text-right">Actual h</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows?.map((r) => {
                const v = draft[r.task_id] ?? (r.actual_hours !== null && r.actual_hours !== undefined ? String(r.actual_hours) : "");
                const actual = v === "" ? null : Number(v);
                return (
                  <TableRow key={r.task_id}>
                    <TableCell className="text-xs text-muted-foreground">{r.module}</TableCell>
                    <TableCell>{r.title}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {r.min_hours}–{r.max_hours}
                    </TableCell>
                    <TableCell className="text-right">
                      <Input
                        inputMode="decimal"
                        aria-label={`Actual hours for ${r.title}`}
                        className={`h-7 text-right tabular-nums ${variance(r.min_hours, r.max_hours, actual)}`}
                        value={v}
                        onChange={(e) => setDraft((d) => ({ ...d, [r.task_id]: e.target.value }))}
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>
      <div className="space-y-3">
        <Card size="sm">
          <CardHeader>
            <CardTitle>Accuracy</CardTitle>
            <CardDescription>Final estimate vs. actuals (planned tasks only)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div>
              Tasks with actuals: {acc?.tasks_with_actuals ?? 0} / {acc?.tasks_total ?? 0}
            </div>
            <div>
              Estimate (mid): {hours(acc?.estimate_mid_for_tasks_with_actuals)} · Actual: {hours(acc?.planned_actual_hours)}
            </div>
            <div>
              P50 {hours(acc?.p50)} · P80 {hours(acc?.p80)} ·{" "}
              {acc?.within_p80 === null || acc?.within_p80 === undefined ? "—" : acc.within_p80 ? "within P80 ✓" : "above P80 ✗"}
            </div>
            <div>Project error: {pct(acc?.project_ape)} · task MdAPE: {pct(acc?.task_mdape)}</div>
            <div>Tasks inside min–max: {pct(acc?.task_in_range_share)}</div>
            <div>
              Unplanned work: {hours(acc?.unplanned_hours)} ({pct(acc?.unplanned_share)} of total)
            </div>
          </CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-1">
              Unplanned work
              <HelpTip label="unplanned work" href="/help/closing-the-loop#unplanned" text="Work that was not in the quote. Recorded separately with a reason so it does not distort estimation error." />
            </CardTitle>
            <CardDescription>Scope creep never in the estimate — tracked separately.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {unplanned?.map((u) => (
              <div key={u.id} className="flex items-center justify-between text-sm">
                <span>
                  {u.title} <span className="text-xs text-muted-foreground">· {REASON_LABEL[u.reason ?? "unspecified"]}</span>
                </span>
                <span className="flex items-center gap-1 tabular-nums">
                  {hours(u.hours)}
                  <Button variant="ghost" size="icon-xs" aria-label="Delete" onClick={() => delUnplanned.mutate(u.id)}>
                    <Trash2 />
                  </Button>
                </span>
              </div>
            ))}
            <div className="flex gap-1.5">
              <Input className="h-8" placeholder="What was done" aria-label="Unplanned work description" value={title} onChange={(e) => setTitle(e.target.value)} />
              <select
                className="h-8 rounded-md border bg-background px-1.5 text-xs"
                aria-label="Reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              >
                <option value="missed_requirement">Missed requirement</option>
                <option value="clarified_scope">Clarified scope</option>
                <option value="change_request">Change request</option>
                <option value="other">Other</option>
              </select>
              <Input className="h-8 w-20" placeholder="h" inputMode="decimal" value={uh} onChange={(e) => setUh(e.target.value)} />
              <Button size="icon-sm" aria-label="Add" onClick={() => addUnplanned.mutate()} disabled={!title || !Number(uh)}>
                <Plus />
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
