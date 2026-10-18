"use client";

import { Bot, User } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useActivity } from "@/hooks/queries";
import { dateTime } from "@/lib/format";
import { REASON_TAGS, type EditEvent } from "@/lib/types";

function describe(e: EditEvent): string {
  const o = e.old_value as Record<string, unknown> | null;
  const n = e.new_value as Record<string, unknown> | null;
  switch (e.event_type) {
    case "hours_changed":
      if (e.field === "reason") return "added a reason";
      return `hours ${o?.min}–${o?.max} → ${n?.min}–${n?.max}`;
    case "task_added":
      return `added task (${n?.min_hours}–${n?.max_hours} h)`;
    case "task_removed":
      return "removed task";
    case "task_restored":
      return "restored task";
    case "task_toggled":
      return n ? "enabled task" : "disabled task";
    case "title_changed":
      return `changed ${e.field}`;
    case "task_moved":
      return "moved task";
    case "proposal_op_rejected":
      return `rejected agent proposal (${e.field})`;
    default:
      return e.event_type.replaceAll("_", " ");
  }
}

export function ActivityTab({ estimateId }: { estimateId: string | null }) {
  const [actor, setActor] = useState("all");
  const { data, isLoading } = useActivity(estimateId, actor === "all" ? undefined : actor);
  if (!estimateId) return <EmptyState title="No estimate selected" />;
  return (
    <div className="space-y-3">
      <ToggleGroup value={[actor]} onValueChange={(v) => v.length && setActor(String(v[0]))} variant="outline" size="sm">
        <ToggleGroupItem value="all">All</ToggleGroupItem>
        <ToggleGroupItem value="user">User</ToggleGroupItem>
        <ToggleGroupItem value="agent">Agent</ToggleGroupItem>
        <ToggleGroupItem value="system">System</ToggleGroupItem>
      </ToggleGroup>
      {isLoading ? (
        <Skeleton className="h-64" />
      ) : !data?.length ? (
        <EmptyState title="No edits yet" description="Every change to tasks is logged here (append-only)." />
      ) : (
        <ol className="relative space-y-3 border-l pl-5">
          {data.map((e) => (
            <li key={e.id} className="text-sm">
              <span className="absolute -left-2.5 flex size-5 items-center justify-center rounded-full border bg-background">
                {e.actor === "agent" ? <Bot className="size-3" /> : <User className="size-3" />}
              </span>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium">{e.user_name ?? e.actor}</span>
                {e.actor === "agent" && <Badge variant="secondary">via agent</Badge>}
                <span>{describe(e)}</span>
                {e.task_title && <span className="text-muted-foreground">· {e.task_title}</span>}
                {e.reason_tag && (
                  <Badge variant="outline">{REASON_TAGS.find((r) => r.value === e.reason_tag)?.label ?? e.reason_tag}</Badge>
                )}
              </div>
              {e.reason_text && <div className="text-xs text-muted-foreground">“{e.reason_text}”</div>}
              <div className="text-xs text-muted-foreground">{dateTime(e.created_at)}</div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
