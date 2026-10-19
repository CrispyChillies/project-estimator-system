"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { ak, useMemories } from "@/hooks/agent";
import { errorToast } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { AgentSessionOut } from "@/lib/types";

export function MemoryDrawer({
  open,
  onOpenChange,
  estimateId,
  session,
  onPatch,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  estimateId: string;
  session: AgentSessionOut;
  onPatch: (p: Partial<AgentSessionOut>) => void;
}) {
  const qc = useQueryClient();
  const { data: memories } = useMemories(estimateId);
  const [text, setText] = useState("");
  const [budget, setBudget] = useState("");
  const refresh = () => void qc.invalidateQueries({ queryKey: ak.memories(estimateId) });
  const add = useMutation({
    mutationFn: () => api(`/estimates/${estimateId}/memories`, { method: "POST", json: { text, kind: "fact" } }),
    onSuccess: () => {
      setText("");
      refresh();
    },
    onError: errorToast,
  });
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api(`/memories/${id}`, { method: "PATCH", json: { enabled } }),
    onSuccess: refresh,
    onError: errorToast,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/memories/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
    onError: errorToast,
  });
  const state = Object.entries(session.state ?? {});

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Agent memory</SheetTitle>
          <SheetDescription>What the agent carries between turns. Session settings are binding inputs to tools.</SheetDescription>
        </SheetHeader>
        <div className="space-y-4 px-4 pb-6 text-sm">
          <div className="flex items-center justify-between">
            <Label htmlFor="use-memory">Use memory in this session</Label>
            <Switch id="use-memory" checked={session.use_memory} onCheckedChange={(c) => onPatch({ use_memory: c })} />
          </div>
          <Separator />
          <section className="space-y-2">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase">Session settings</h3>
            {state.length ? (
              <ul className="space-y-1">
                {state.map(([k, v]) => (
                  <li key={k} className="flex items-center justify-between rounded-md border px-2 py-1">
                    <code className="text-xs">{k}</code>
                    <span className="flex items-center gap-1">
                      {String(v)}
                      <Button
                        size="icon-xs"
                        variant="ghost"
                        aria-label={`Clear ${k}`}
                        onClick={() => {
                          const next = { ...session.state };
                          delete next[k];
                          onPatch({ state: next });
                        }}
                      >
                        <Trash2 />
                      </Button>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">None yet. Try “set a budget of 400”.</p>
            )}
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const n = Number(budget);
                if (n > 0) onPatch({ state: { ...session.state, budget_hours: n } });
                setBudget("");
              }}
            >
              <Input
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                placeholder="Budget (hours)"
                inputMode="decimal"
                aria-label="Budget hours"
              />
              <Button type="submit" size="sm" variant="outline">
                Set
              </Button>
            </form>
          </section>
          <Separator />
          <section className="space-y-2">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase">Conversation summary</h3>
            <p className="text-xs whitespace-pre-wrap text-muted-foreground">
              {session.summary || "Short conversation — nothing summarised yet."}
            </p>
          </section>
          <Separator />
          <section className="space-y-2">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase">Project memories</h3>
            {(memories ?? []).map((m) => (
              <div key={m.id} className="flex items-start gap-2 rounded-md border px-2 py-1.5">
                <Switch
                  size="sm"
                  checked={m.enabled}
                  aria-label={`Use memory: ${m.text}`}
                  onCheckedChange={(c) => toggle.mutate({ id: m.id, enabled: c })}
                />
                <div className="min-w-0 flex-1">
                  <div className={m.enabled ? "" : "text-muted-foreground line-through"}>{m.text}</div>
                  <div className="mt-0.5 flex gap-1">
                    <Badge variant="outline" className="h-4 px-1 text-[10px]">
                      {m.kind}
                    </Badge>
                    <Badge variant="outline" className="h-4 px-1 text-[10px]">
                      from {m.origin}
                    </Badge>
                  </div>
                </div>
                <Button size="icon-xs" variant="ghost" aria-label="Delete memory" onClick={() => remove.mutate(m.id)}>
                  <Trash2 />
                </Button>
              </div>
            ))}
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (text.trim()) add.mutate();
              }}
            >
              <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a fact…" aria-label="New memory" />
              <Button type="submit" size="sm" variant="outline">
                Add
              </Button>
            </form>
          </section>
        </div>
      </SheetContent>
    </Sheet>
  );
}
