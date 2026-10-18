"use client";

import { useMutation } from "@tanstack/react-query";
import { MessageSquareText, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorToast, useInvalidateEstimate } from "@/hooks/queries";
import { api } from "@/lib/api";
import { REASON_TAGS, type ReasonTag } from "@/lib/types";

/** Non-blocking "Why?" chips shown after a large hours change. Skipping never blocks editing. */
export function ReasonChips({
  taskId,
  estimateId,
  deltaPct,
  onClose,
}: {
  taskId: string;
  estimateId: string;
  deltaPct: number;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const invalidate = useInvalidateEstimate();
  const save = useMutation({
    mutationFn: (tag: ReasonTag) =>
      api<void>(`/tasks/${taskId}/reason`, { method: "POST", json: { reason_tag: tag, reason_text: text || null } }),
    onSuccess: () => {
      toast.success("Reason saved — it will inform lessons");
      invalidate(estimateId);
      onClose();
    },
    onError: errorToast,
  });
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-md bg-muted/60 px-2 py-1.5 text-xs">
      <MessageSquareText className="size-3.5 text-muted-foreground" />
      <span className="text-muted-foreground">
        Changed {deltaPct > 0 ? "+" : ""}
        {deltaPct.toFixed(0)}% — why? (optional)
      </span>
      {REASON_TAGS.map((r) => (
        <Badge
          key={r.value}
          variant="outline"
          className="cursor-pointer hover:bg-accent"
          render={<button type="button" onClick={() => save.mutate(r.value)} />}
        >
          {r.label}
        </Badge>
      ))}
      <Input
        className="h-6 w-48 text-xs"
        placeholder="note (optional)"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <Button variant="ghost" size="icon-xs" aria-label="Skip" onClick={onClose}>
        <X />
      </Button>
    </div>
  );
}
