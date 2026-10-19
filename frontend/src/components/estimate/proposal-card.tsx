"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { errorToast, useInvalidateEstimate } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { BulkChange, Proposal, ProposalOp } from "@/lib/types";
import { cn } from "@/lib/utils";

function OpDiff({ op }: { op: ProposalOp }) {
  const p = op.payload;
  if (op.type === "bulk_adjust" && Array.isArray(p.changes)) {
    return (
      <ul className="mt-1 space-y-0.5 text-xs">
        {(p.changes as BulkChange[]).slice(0, 8).map((c) => (
          <li key={c.task_id} className="flex justify-between gap-2">
            <span className="truncate">{c.title}</span>
            <span className="shrink-0 tabular-nums">
              <span className="text-rose-600 line-through">
                {c.old_min}–{c.old_max}
              </span>{" "}
              <span className="text-emerald-600">
                {c.new_min}–{c.new_max}
              </span>
            </span>
          </li>
        ))}
        {(p.changes as BulkChange[]).length > 8 && <li className="text-muted-foreground">…and more</li>}
      </ul>
    );
  }
  if (op.type === "add_task")
    return (
      <div className="mt-1 text-xs text-emerald-600">
        + {p.title} ({p.min_hours}–{p.max_hours} h)
      </div>
    );
  if (op.type === "remove_task") return <div className="mt-1 text-xs text-rose-600 line-through">− {p.title}</div>;
  if (op.type === "update_task" && p.before)
    return (
      <div className="mt-1 text-xs">
        <span className="text-rose-600 line-through">
          {p.before.min_hours}–{p.before.max_hours} h
        </span>{" "}
        <span className="text-emerald-600">{JSON.stringify(p.changes)}</span>
      </div>
    );
  return null;
}

export function ProposalCard({ proposal, estimateId }: { proposal: Proposal; estimateId: string }) {
  const invalidate = useInvalidateEstimate();
  const qc = useQueryClient();
  const act = useMutation({
    mutationFn: (path: string) => api<Proposal>(`/proposals/${proposal.id}/${path}`, { method: "POST" }),
    onSuccess: (p) => {
      qc.setQueryData(["proposal", p.id], p);
      invalidate(estimateId);
      toast.success("Applied and logged");
    },
    onError: errorToast,
  });
  const ops = proposal.ops as unknown as ProposalOp[];
  const pending = ops.filter((o) => o.status === "pending").length;
  return (
    <div className="rounded-lg border bg-card p-2.5 text-sm">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Proposed changes</span>
        {pending > 1 && (
          <div className="flex gap-1">
            <Button size="xs" variant="outline" onClick={() => act.mutate("reject_all")}>
              Reject all
            </Button>
            <Button size="xs" onClick={() => act.mutate("accept_all")}>
              Accept all
            </Button>
          </div>
        )}
      </div>
      <div className="space-y-1.5">
        {ops.map((op) => (
          <div
            key={op.id}
            className={cn(
              "rounded-md border-l-2 bg-muted/40 p-2",
              op.status === "accepted" && "border-emerald-500",
              op.status === "rejected" && "border-rose-500 opacity-60",
              op.status === "pending" && "border-amber-500",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium">{op.summary}</div>
                {op.rationale && <div className="text-xs text-muted-foreground">{op.rationale}</div>}
                <OpDiff op={op} />
              </div>
              {op.status === "pending" ? (
                <div className="flex shrink-0 gap-1">
                  <Button size="icon-xs" variant="outline" aria-label="Reject" onClick={() => act.mutate(`ops/${op.id}/reject`)}>
                    <X />
                  </Button>
                  <Button size="icon-xs" aria-label="Accept" onClick={() => act.mutate(`ops/${op.id}/accept`)}>
                    <Check />
                  </Button>
                </div>
              ) : (
                <Badge variant="secondary">{op.status}</Badge>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
