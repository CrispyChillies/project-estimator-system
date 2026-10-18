"use client";

import { AlertTriangle, Inbox } from "lucide-react";
import { useEffect, useRef } from "react";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useJob, useModelStatus } from "@/hooks/queries";
import type { Job } from "@/lib/types";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function DataSourceBadge({ source }: { source: string }) {
  if (source === "synthetic")
    return (
      <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400">
        Synthetic
      </Badge>
    );
  if (source === "dataset")
    return (
      <Badge variant="outline" className="border-sky-500/50 text-sky-700 dark:text-sky-400">
        Demo data
      </Badge>
    );
  return null;
}

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  quoted: "bg-blue-500/15 text-blue-700 dark:text-blue-300",
  won: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  lost: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
  delivered: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
  final: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="secondary" className={STATUS_STYLE[status] ?? ""}>
      {status}
    </Badge>
  );
}

export function ModelStatusBanner() {
  const { data } = useModelStatus();
  if (!data?.restarted) return null;
  const others = Object.entries(data.final_estimates_by_key).filter(([k]) => k !== data.active_model_key);
  return (
    <div className="flex items-start gap-2 rounded-md border border-sky-500/40 bg-sky-500/5 px-3 py-2 text-sm text-sky-800 dark:text-sky-300">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <span>
        Calibration restarted for model <code className="text-xs">{data.active_model_key}</code>: no finalized history was
        produced with this model yet. History from other models is kept separate and not used (
        {others.map(([k, n]) => `${k}: ${n}`).join(", ")}).
      </span>
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-10 text-center">
      <Inbox className="size-8 text-muted-foreground" />
      <p className="font-medium">{title}</p>
      {description && <p className="max-w-md text-sm text-muted-foreground">{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
      <AlertTriangle className="size-4" />
      {error instanceof Error ? error.message : "Failed to load"}
    </div>
  );
}

export function JobProgress({ jobId, onDone }: { jobId: string; onDone?: (job: Job) => void }) {
  const { data } = useJob(jobId);
  const fired = useRef(false);
  const done = data?.status === "done" || data?.status === "failed";
  useEffect(() => {
    if (done && data && onDone && !fired.current) {
      fired.current = true;
      onDone(data);
    }
  }, [done, data, onDone]);
  return (
    <div className="space-y-1.5">
      <Progress value={Math.round((data?.progress ?? 0) * 100)} />
      <p className="text-xs text-muted-foreground">
        {data?.status === "failed" ? <span className="text-destructive">Failed: {data.error}</span> : data?.message || data?.status || "queued"}
      </p>
    </div>
  );
}
