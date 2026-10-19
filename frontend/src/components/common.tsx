"use client";

import { AlertTriangle, Inbox } from "lucide-react";
import { useEffect, useRef } from "react";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useJob } from "@/hooks/queries";
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

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-muted text-foreground/80",
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
