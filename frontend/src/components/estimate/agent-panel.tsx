"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Send, X } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { errorToast, useInvalidateEstimate, useProposals } from "@/hooks/queries";
import { api, postSSE } from "@/lib/api";
import type { BulkChange, Proposal, ProposalOp } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Msg {
  role: "user" | "assistant";
  text: string;
}

const EXAMPLES = ["increase backend hours by 20% and add an SSO task", "explain ERP integration", "remove the push notifications task"];

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

export function AgentPanel({ estimateId, readOnly }: { estimateId: string; readOnly: boolean }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState("chat");
  const sessionRef = useRef<string | null>(null);
  const { data: pending, refetch } = useProposals(estimateId);
  const invalidate = useInvalidateEstimate();

  const send = async (t: string) => {
    if (!t.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", text: t }, { role: "assistant", text: "" }]);
    setText("");
    setBusy(true);
    try {
      await postSSE(
        `/estimates/${estimateId}/agent/messages`,
        { text: t, session_id: sessionRef.current },
        {
          onEvent: (ev, data) => {
            const d = data as Record<string, string>;
            if (ev === "session") sessionRef.current = d.session_id;
            if (ev === "token")
              setMessages((m) => {
                const copy = [...m];
                copy[copy.length - 1] = { role: "assistant", text: copy[copy.length - 1].text + d.text };
                return copy;
              });
            if (ev === "proposal") void refetch();
            if (ev === "error") toast.error(d.message);
          },
        },
      );
    } catch (e) {
      errorToast(e);
    } finally {
      setBusy(false);
      invalidate(estimateId);
    }
  };

  return (
    <div className="flex h-full flex-col gap-2 p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-medium">
          <Bot className="size-4" /> AI Agent
        </div>
        <ToggleGroup value={[mode]} onValueChange={(v) => v.length && setMode(String(v[0]))} size="sm" variant="outline">
          <ToggleGroupItem value="chat">Chat</ToggleGroupItem>
          <ToggleGroupItem value="generate">Generate</ToggleGroupItem>
        </ToggleGroup>
      </div>
      <p className="text-xs text-muted-foreground">
        The agent never edits directly: every change is a reviewable proposal, logged when you accept or reject it.
      </p>
      <ScrollArea className="min-h-0 flex-1 rounded-md border">
        <div className="space-y-2 p-2">
          {messages.length === 0 && (
            <div className="space-y-1.5">
              {EXAMPLES.map((e) => (
                <button
                  key={e}
                  type="button"
                  className="block w-full rounded-md border px-2 py-1.5 text-left text-xs hover:bg-accent"
                  onClick={() => void send(e)}
                  disabled={readOnly}
                >
                  {e}
                </button>
              ))}
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "max-w-[90%] rounded-lg px-2.5 py-1.5 text-sm whitespace-pre-wrap",
                m.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "bg-muted",
              )}
            >
              {m.text || (busy && i === messages.length - 1 ? "…" : "")}
            </div>
          ))}
          {pending?.map((p) => (
            <ProposalCard key={p.id} proposal={p} estimateId={estimateId} />
          ))}
        </div>
      </ScrollArea>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(mode === "generate" ? `add ${text}` : text);
        }}
      >
        <Textarea
          rows={2}
          value={text}
          disabled={readOnly}
          placeholder={readOnly ? "Estimate is final — clone it to change" : mode === "generate" ? "Describe a task to add…" : "Ask or instruct…"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(mode === "generate" ? `add ${text}` : text);
            }
          }}
        />
        <Button type="submit" size="icon" disabled={busy || readOnly} aria-label="Send">
          <Send />
        </Button>
      </form>
    </div>
  );
}
