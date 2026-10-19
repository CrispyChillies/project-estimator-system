"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Bot,
  Brain,
  Check,
  ChevronDown,
  Crosshair,
  Loader2,
  MessageCircleQuestion,
  Pin,
  Plus,
  Send,
  Sparkles,
  Square,
  Trash2,
  Undo2,
  Wrench,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { MemoryDrawer } from "@/components/estimate/memory-drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  ak,
  useAgentMessages,
  useAgentOps,
  useAgentSessions,
  useCreateSession,
  useDeleteSession,
  usePatchSession,
} from "@/hooks/agent";
import { errorToast, useDocuments, useInvalidateEstimate } from "@/hooks/queries";
import { api, ApiError, postSSE } from "@/lib/api";
import type { AgentMsg, AgentOperationOut, ReferenceProject, ToolLogEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface PatchHandlers {
  onPatch: (taskIds: string[]) => void;
  onShowTasks: (taskIds: string[]) => void;
}

const SLASH = [
  { cmd: "/fit ", hint: "/fit 400 — fit total max hours to a budget" },
  { cmd: "/adjust ", hint: "/adjust +10% backend — scale hours" },
  { cmd: "/round", hint: "/round — round all hours to 0.5 h" },
  { cmd: "/similar", hint: "/similar — 3 most similar past projects" },
  { cmd: "/remember ", hint: "/remember <fact> — save to project memory" },
  { cmd: "/budget ", hint: "/budget 400 — set the session budget" },
  { cmd: "/new", hint: "/new — start a new session" },
];

const STARTERS = [
  { label: "Analyze & draft estimate", text: "Analyze the draft estimate" },
  { label: "Find ambiguities first", text: "Find ambiguities first" },
  { label: "Show similar past projects (k=3)", text: "/similar 3" },
  { label: "Set a budget", text: "/budget ", prefill: true },
];

const TOOL_LABEL: Record<string, string> = {
  fit_to_budget: "Fit to budget",
  rebalance_roles: "Rebalance roles",
  bulk_adjust: "Bulk adjust",
  set_hours: "Set hours",
  create_task: "Create task",
  create_group: "Create group",
  update_task: "Update task",
  split_task: "Split task",
  merge_tasks: "Merge tasks",
  move_tasks: "Move tasks",
  toggle_visibility: "Show / hide",
  delete_tasks: "Delete",
  remember: "Remember",
  ask_user: "Question",
  retrieve_similar_projects: "Similar projects",
  run_analysis: "Analysis",
  get_estimate_summary: "Estimate summary",
  list_tasks: "List tasks",
  explain_task: "Explain task",
};

type Live =
  | { kind: "user"; text: string }
  | { kind: "tool"; id: string; name: string; args?: Record<string, unknown>; result?: LiveResult }
  | { kind: "ask"; question: string; options: string[] }
  | { kind: "refs"; items: ReferenceProject[] }
  | { kind: "text"; text: string };

interface LiveResult {
  ok: boolean;
  status?: string;
  summary?: string;
  message?: string;
  operation_id?: string;
  before?: [number, number];
  after?: [number, number];
  reasons?: string[];
  duration_ms?: number;
}

function argsSummary(args?: Record<string, unknown>): string {
  if (!args) return "";
  return Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0))
    .map(([k, v]) => `${k.replaceAll("_", " ")}: ${Array.isArray(v) ? `${v.length} item(s)` : typeof v === "object" ? "…" : String(v)}`)
    .join(" · ");
}

const POLL_ONLY = process.env.NEXT_PUBLIC_CHAT_TRANSPORT === "poll";

const range = (r?: [number, number]) => (r ? `${r[0]}–${r[1]} h` : "");

function sessionKey(estimateId: string) {
  return `calibr.agentSession.${estimateId}`;
}

function ToolCard({
  name,
  entry,
  args,
  op,
  busy,
  onAct,
  onShow,
}: {
  name: string;
  args?: Record<string, unknown>;
  entry?: LiveResult | ToolLogEntry;
  op?: AgentOperationOut;
  busy: boolean;
  onAct: (path: string, op: AgentOperationOut | string) => void;
  onShow: (ids: string[]) => void;
}) {
  const live = entry as LiveResult | undefined;
  const status = op?.status ?? live?.status ?? (entry ? (entry.ok ? "done" : "error") : "running");
  const before = op?.result.before ?? live?.before;
  const after = op?.result.after ?? live?.after;
  const reasons = (op?.result as { reasons?: string[] } | undefined)?.reasons ?? live?.reasons;
  const ids = [...(op?.result.touched_task_ids ?? []), ...(op?.result.created_ids ?? [])];
  const text = entry?.summary ?? live?.message;
  const opId = op?.id ?? live?.operation_id;
  const undo = op?.result.undo;
  const [raw, setRaw] = useState(false);
  const callArgs = args ?? (entry as ToolLogEntry | undefined)?.args;
  const ms = (entry as LiveResult | undefined)?.duration_ms;
  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-2 text-xs",
        status === "awaiting_confirmation" && "border-amber-500/60",
        (status === "error" || status === "failed") && "border-rose-500/50",
      )}
      data-testid="tool-card"
    >
      <div className="flex items-center gap-1.5">
        {!entry ? <Loader2 className="size-3.5 animate-spin" /> : <Wrench className="size-3.5 text-muted-foreground" />}
        <span className="font-medium">{TOOL_LABEL[name] ?? name}</span>
        {ms !== undefined && <span className="ml-auto text-[10px] text-muted-foreground tabular-nums">{ms} ms</span>}
        <Badge variant="outline" className={cn("h-4 px-1.5 text-[10px]", ms === undefined && "ml-auto")}>
          {status.replaceAll("_", " ")}
        </Badge>
      </div>
      {callArgs && Object.keys(callArgs).length > 0 && (
        <div className="mt-0.5 text-muted-foreground">
          {argsSummary(callArgs)}{" "}
          <button type="button" className="underline underline-offset-2" onClick={() => setRaw((r) => !r)} aria-expanded={raw}>
            {raw ? "hide JSON" : "JSON"}
          </button>
          {raw && <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted p-1.5 text-[10px]">{JSON.stringify(callArgs, null, 2)}</pre>}
        </div>
      )}
      {text && <div className={cn("mt-1", entry && !entry.ok && "text-rose-600")}>{text}</div>}
      {before && after && (
        <div className="mt-1 tabular-nums text-muted-foreground">
          Total {range(before)} → <span className="font-medium text-foreground">{range(after)}</span>
        </div>
      )}
      {status === "awaiting_confirmation" && reasons?.length ? (
        <ul className="mt-1 list-disc pl-4 text-amber-700 dark:text-amber-400">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}
      {undo && undo.skipped.length > 0 && (
        <div className="mt-1 text-amber-700 dark:text-amber-400">
          Partial undo: kept {undo.skipped.map((s) => s.title).join(", ")} (edited after the agent change).
        </div>
      )}
      {opId && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {ids.length > 0 && (
            <Button size="xs" variant="ghost" onClick={() => onShow(ids)}>
              <Crosshair /> Show in table
            </Button>
          )}
          {status === "applied" && (
            <Button size="xs" variant="outline" disabled={busy} onClick={() => onAct("undo", op ?? opId)}>
              <Undo2 /> Undo
            </Button>
          )}
          {status === "awaiting_confirmation" && (
            <>
              <Button size="xs" disabled={busy} onClick={() => onAct("confirm", op ?? opId)}>
                <Check /> Confirm
              </Button>
              <Button size="xs" variant="outline" disabled={busy} onClick={() => onAct("reject", op ?? opId)}>
                <X /> Reject
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function AskCard({ question, options, onPick, disabled }: { question: string; options: string[]; onPick: (o: string) => void; disabled: boolean }) {
  return (
    <div className="rounded-lg border border-sky-500/50 bg-sky-500/5 p-2 text-xs">
      <div className="flex items-center gap-1.5 font-medium">
        <MessageCircleQuestion className="size-3.5" /> {question}
      </div>
      {options.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {options.map((o) => (
            <Button key={o} size="xs" variant="outline" disabled={disabled} onClick={() => onPick(o)}>
              {o}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

function RefsCard({ items }: { items: ReferenceProject[] }) {
  return (
    <div className="rounded-lg border p-2 text-xs" data-testid="references-card">
      <div className="mb-1 font-medium">References · similar past projects</div>
      {items.length === 0 ? (
        <div className="text-muted-foreground">None above the similarity threshold (fewer is better than weak matches).</div>
      ) : (
        <ul className="space-y-1">
          {items.map((r) => (
            <li key={r.project_id} className="rounded-md bg-muted/40 px-2 py-1">
              <div className="flex justify-between gap-2">
                <span className="font-medium">{r.name}</span>
                <span className="tabular-nums text-muted-foreground">sim {r.similarity.toFixed(2)}</span>
              </div>
              <div className="text-muted-foreground">
                {r.status}
                {r.total_min !== undefined && ` · ${r.total_min}–${r.total_max} h`}
                {r.actual_total ? ` · actual ${r.actual_total} h` : ""}
              </div>
              {r.notes?.[0] && <div className="text-muted-foreground">{r.notes[0]}</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Bubble({ role, children }: { role: "user" | "assistant" | "event"; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "max-w-[92%] rounded-lg px-2.5 py-1.5 text-sm whitespace-pre-wrap",
        role === "user" && "ml-auto bg-primary text-primary-foreground",
        role === "assistant" && "bg-muted",
        role === "event" && "mx-auto bg-transparent text-center text-xs text-muted-foreground",
      )}
    >
      {children}
    </div>
  );
}

export function AgentPanel({
  estimateId,
  projectId,
  readOnly,
  onClose,
  onPatch,
  onShowTasks,
  selectedIds = [],
  onClearSelection,
}: {
  estimateId: string;
  projectId: string;
  readOnly: boolean;
  onClose: () => void;
  selectedIds?: string[];
  onClearSelection?: () => void;
} & PatchHandlers) {
  const qc = useQueryClient();
  const invalidate = useInvalidateEstimate();
  const { data: sessions } = useAgentSessions(estimateId);
  const { data: docs } = useDocuments(projectId);
  const [picked, setPicked] = useState<string | null>(() =>
    typeof window === "undefined" ? null : window.localStorage.getItem(sessionKey(estimateId)),
  );
  const sessionId = sessions?.find((s) => s.id === picked)?.id ?? sessions?.[0]?.id ?? null;
  const session = sessions?.find((s) => s.id === sessionId);
  const [live, setLive] = useState<Live[]>([]);
  const [busy, setBusy] = useState(false);
  const [acting, setActing] = useState(false);
  const [text, setText] = useState("");
  const [memOpen, setMemOpen] = useState(false);
  const [failure, setFailure] = useState<{ text: string; message: string } | null>(null);
  const remoteRunning = session?.run_state === "running" && !busy;
  const { data: messages } = useAgentMessages(sessionId, remoteRunning);
  const { data: ops } = useAgentOps(sessionId);
  const create = useCreateSession(estimateId);
  const patch = usePatchSession(estimateId);
  const del = useDeleteSession(estimateId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const creating = useRef(false);
  const opById = useMemo(() => new Map((ops ?? []).map((o) => [o.id, o])), [ops]);

  const defaultTitle = docs?.length ? docs.map((d) => d.filename).join(", ").slice(0, 80) : "New session";

  useEffect(() => {
    if (sessionId) window.localStorage.setItem(sessionKey(estimateId), sessionId);
  }, [sessionId, estimateId]);

  useEffect(() => {
    // One session per estimate exists from the start, titled after the uploaded files.
    if (sessions && sessions.length === 0 && !readOnly && !creating.current && docs) {
      creating.current = true;
      create.mutate({ title: defaultTitle });
    }
  }, [sessions, readOnly, docs, create, defaultTitle]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, live, ops]);

  const refreshAgent = async () => {
    if (!sessionId) return;
    await Promise.all([
      qc.refetchQueries({ queryKey: ak.messages(sessionId) }),
      qc.refetchQueries({ queryKey: ak.ops(sessionId) }),
      qc.invalidateQueries({ queryKey: ak.sessions(estimateId) }),
      qc.invalidateQueries({ queryKey: ak.memories(estimateId) }),
    ]);
  };

  const newSession = async () => {
    const s = await create.mutateAsync({ title: defaultTitle });
    setPicked(s.id);
    setLive([]);
  };

  const waitUntilIdle = async (sid: string) => {
    // Polling transport and stream recovery: the run continues on the server, the state is persisted.
    for (let i = 0; i < 400; i++) {
      const s = await api<{ run_state: string }>(`/agent/sessions/${sid}`).catch(() => null);
      await qc.refetchQueries({ queryKey: ak.messages(sid) });
      await qc.refetchQueries({ queryKey: ak.ops(sid) });
      invalidate(estimateId);
      if (s && s.run_state !== "running" && s.run_state !== "cancelling") return;
      await new Promise((r) => setTimeout(r, 1500));
    }
  };

  const send = async (raw: string) => {
    const t = raw.trim();
    if (!t || busy || readOnly) return;
    if (t === "/new") {
      setText("");
      await newSession();
      return;
    }
    if (!sessionId) return;
    setText("");
    setBusy(true);
    setFailure(null);
    setLive([{ kind: "user", text: t }]);
    const push = (item: Live) => setLive((l) => [...l, item]);
    const body = { text: t, idempotency_key: crypto.randomUUID(), selected_task_ids: selectedIds };
    let gotEvent = false;
    let failed: string | null = null;
    const onEvent = (ev: string, data: unknown) => {
      gotEvent = true;
      const d = data as Record<string, unknown>;
      if (ev === "tool_call_started") push({ kind: "tool", id: String(d.id), name: String(d.name), args: d.args as Record<string, unknown> });
      if (ev === "tool_call_result")
        setLive((l) => l.map((x) => (x.kind === "tool" && x.id === d.id ? { ...x, result: d as unknown as LiveResult } : x)));
      if (ev === "confirmation_required") {
        const opId = String(d.operation_id);
        setLive((l) =>
          l.map((x) =>
            x.kind === "tool" && x.result?.operation_id === opId ? { ...x, result: { ...x.result, reasons: d.reasons as string[] } } : x,
          ),
        );
      }
      if (ev === "table_patch") {
        onPatch([...((d.task_ids as string[]) ?? []), ...((d.created_ids as string[]) ?? [])]);
        invalidate(estimateId);
        void qc.invalidateQueries({ queryKey: ak.ops(sessionId) });
      }
      if (ev === "ask_user") push({ kind: "ask", question: String(d.question), options: (d.options as string[]) ?? [] });
      if (ev === "references") push({ kind: "refs", items: (d.items as ReferenceProject[]) ?? [] });
      if (ev === "memory_updated") void qc.invalidateQueries({ queryKey: ak.memories(estimateId) });
      if (ev === "message_delta")
        setLive((l) => {
          const last = l[l.length - 1];
          if (last?.kind === "text") return [...l.slice(0, -1), { kind: "text", text: last.text + String(d.text) }];
          return [...l, { kind: "text", text: String(d.text) }];
        });
      if (ev === "error") failed = String(d.message);
    };
    try {
      if (POLL_ONLY) throw new Error("poll");
      const ctrl = new AbortController();
      // A proxy that buffers the stream shows nothing; after 20 s without any event, switch to polling.
      const watchdog = setTimeout(() => !gotEvent && ctrl.abort(), 20_000);
      try {
        await postSSE(`/agent/sessions/${sessionId}/runs`, body, { onEvent, signal: ctrl.signal });
      } finally {
        clearTimeout(watchdog);
      }
    } catch (e) {
      if (e instanceof ApiError && e.status !== 0 && e.code !== "stream_error") {
        failed = e.message; // a real refusal (allowance, rate limit, run in progress, ...): show it, never retry silently
      } else if (!gotEvent) {
        try {
          await api(`/agent/sessions/${sessionId}/runs/async`, { method: "POST", json: body });
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 409)) failed = err instanceof Error ? err.message : "The agent could not start.";
        }
      }
      if (!failed) await waitUntilIdle(sessionId);
    } finally {
      await refreshAgent();
      setLive([]);
      setBusy(false);
      invalidate(estimateId);
      if (failed) setFailure({ text: t, message: failed });
    }
  };

  const act = async (path: string, op: AgentOperationOut | string) => {
    const id = typeof op === "string" ? op : op.id;
    setActing(true);
    try {
      const res = await api<AgentOperationOut & { undo?: { partial: boolean } }>(`/agent/operations/${id}/${path}`, {
        method: "POST",
      });
      onPatch([...(res.result.touched_task_ids ?? []), ...(res.result.created_ids ?? [])]);
      if (path === "undo" && res.undo?.partial) toast.warning("Partially undone: rows you edited afterwards were kept");
      else toast.success(path === "confirm" ? "Applied" : path === "undo" ? "Undone" : "Rejected");
    } catch (e) {
      errorToast(e);
    } finally {
      setActing(false);
      invalidate(estimateId);
      await refreshAgent();
    }
  };

  const undoAll = async (batchId: string) => {
    setActing(true);
    try {
      await api(`/agent/batches/${batchId}/undo`, { method: "POST" });
      toast.success("Undid all changes from that turn");
    } catch (e) {
      errorToast(e);
    } finally {
      setActing(false);
      invalidate(estimateId);
      await refreshAgent();
    }
  };

  const cancel = async () => {
    if (sessionId) await api(`/agent/sessions/${sessionId}/cancel`, { method: "POST" }).catch(errorToast);
  };

  const budget = session?.state?.budget_hours as number | undefined;
  const slashOpen = text.startsWith("/") && !text.includes(" ") && !busy;
  const shown = messages ?? [];

  const renderPersisted = (m: AgentMsg) => {
    if (m.role === "user") return <Bubble key={m.id} role="user">{m.content}</Bubble>;
    if (m.role === "system_event") return <Bubble key={m.id} role="event">{m.content}</Bubble>;
    const applied = (ops ?? []).filter((o) => o.batch_id === m.batch_id && o.status === "applied");
    const ask = m.payload.ask as { question: string; options: string[] } | null | undefined;
    const refs = m.payload.references as ReferenceProject[] | null | undefined;
    const waiting = m.payload.status === "awaiting_user" && m.id === shown[shown.length - 1]?.id;
    return (
      <div key={m.id} className="space-y-1.5">
        {m.tool_calls
          .filter((c) => c.name !== "ask_user" && c.name !== "retrieve_similar_projects")
          .map((c) => (
            <ToolCard
              key={c.id}
              name={c.name}
              entry={c}
              op={c.operation_id ? opById.get(c.operation_id) : undefined}
              busy={acting || busy}
              onAct={(p, o) => void act(p, o)}
              onShow={onShowTasks}
            />
          ))}
        {refs && <RefsCard items={refs} />}
        {m.content && <Bubble role="assistant">{m.content}</Bubble>}
        {ask && waiting && <AskCard {...ask} disabled={busy || readOnly} onPick={(o) => void send(o)} />}
        {applied.length > 1 && m.batch_id && (
          <Button size="xs" variant="ghost" disabled={acting || busy} onClick={() => void undoAll(m.batch_id!)}>
            <Undo2 /> Undo all {applied.length} changes
          </Button>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col gap-2 p-3" aria-label="Agent panel">
      <div className="flex items-center gap-1.5">
        <Bot className="size-4" />
        <span className="font-medium">Agent</span>
        <div className="ml-auto flex items-center gap-1">
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button size="xs" variant="outline" className="max-w-44" />}>
              <span className="truncate">{session?.title ?? "Session"}</span>
              <ChevronDown />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              {(sessions ?? []).map((s) => (
                <DropdownMenuItem key={s.id} onClick={() => setPicked(s.id)}>
                  {s.pinned && <Pin className="size-3" />}
                  <span className={cn("truncate", s.id === sessionId && "font-medium")}>{s.title}</span>
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => void newSession()} disabled={readOnly}>
                <Plus /> New session
              </DropdownMenuItem>
              {session && (
                <>
                  <DropdownMenuItem onClick={() => patch.mutate({ id: session.id, patch: { pinned: !session.pinned } })}>
                    <Pin /> {session.pinned ? "Unpin" : "Pin"}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => {
                      const title = window.prompt("Rename session", session.title);
                      if (title) patch.mutate({ id: session.id, patch: { title } });
                    }}
                  >
                    Rename…
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => {
                      patch.mutate({ id: session.id, patch: { status: "archived" } });
                      setPicked(null);
                    }}
                  >
                    <Archive /> Archive
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={() => {
                      del.mutate(session.id);
                      setPicked(null);
                    }}
                  >
                    <Trash2 /> Delete session
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button size="icon-xs" variant="ghost" aria-label="Memory" onClick={() => setMemOpen(true)}>
            <Brain />
          </Button>
          <Button size="icon-xs" variant="ghost" aria-label="Close agent panel" onClick={onClose}>
            <X />
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <ToggleGroup
          value={[session?.apply_mode ?? "auto"]}
          onValueChange={(v) =>
            session && v.length && patch.mutate({ id: session.id, patch: { apply_mode: v[0] as "auto" | "review" } })
          }
          size="sm"
          variant="outline"
          aria-label="Apply mode"
        >
          <ToggleGroupItem value="auto">Auto</ToggleGroupItem>
          <ToggleGroupItem value="review">Review</ToggleGroupItem>
        </ToggleGroup>
        {budget !== undefined && <Badge variant="secondary">Budget {budget} h</Badge>}
        <Badge variant="secondary">{session?.use_memory === false ? "Memory off" : "Memory on"}</Badge>
        <Badge variant="secondary">k=3 refs</Badge>
        {selectedIds.length > 0 && (
          <Badge variant="default" className="gap-1" data-testid="selection-chip">
            Selection ({selectedIds.length})
            <button type="button" aria-label="Clear selection" onClick={onClearSelection} className="ml-0.5">
              <X className="size-3" />
            </button>
          </Badge>
        )}
      </div>

      <ScrollArea className="min-h-0 flex-1 rounded-md border">
        <div className="space-y-2 p-2" aria-live="polite">
          {shown.length === 0 && live.length === 0 && (
            <div className="space-y-2">
              <Bubble role="assistant">
                {docs?.length
                  ? `I've read ${docs.map((d) => d.filename).join(", ")}. `
                  : ""}
                I work directly on this estimate: changes show up in the table, and every change can be undone. Deletes
                and big swings ask you first.
              </Bubble>
              <div className="flex flex-wrap gap-1.5">
                {STARTERS.map((s) => (
                  <Button
                    key={s.label}
                    size="xs"
                    variant="outline"
                    disabled={readOnly || !sessionId}
                    onClick={() => {
                      if (s.prefill) {
                        setText(s.text);
                        inputRef.current?.focus();
                      } else void send(s.text);
                    }}
                  >
                    <Sparkles /> {s.label}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {shown.map(renderPersisted)}
          {live.map((item, i) => {
            if (item.kind === "user") return <Bubble key={i} role="user">{item.text}</Bubble>;
            if (item.kind === "text") return <Bubble key={i} role="assistant">{item.text}</Bubble>;
            if (item.kind === "ask")
              return <AskCard key={i} question={item.question} options={item.options} disabled onPick={() => undefined} />;
            if (item.kind === "refs") return <RefsCard key={i} items={item.items} />;
            if (item.name === "ask_user" || item.name === "retrieve_similar_projects") return null;
            return (
              <ToolCard
                key={i}
                name={item.name}
                args={item.args}
                entry={item.result}
                op={item.result?.operation_id ? opById.get(item.result.operation_id) : undefined}
                busy
                onAct={() => undefined}
                onShow={onShowTasks}
              />
            );
          })}
          {failure && !busy && (
            <div role="alert" className="rounded-lg border border-rose-500/50 bg-rose-500/5 p-2 text-xs">
              <div className="font-medium text-rose-700 dark:text-rose-400">That did not work</div>
              <div className="mt-0.5">{failure.message}</div>
              <div className="mt-1.5 flex gap-1">
                <Button size="xs" variant="outline" onClick={() => void send(failure.text)}>
                  Retry
                </Button>
                <Button size="xs" variant="ghost" onClick={() => setFailure(null)}>
                  Dismiss
                </Button>
              </div>
            </div>
          )}
          {(busy || remoteRunning) && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" /> {remoteRunning ? "Agent is still working…" : "Working…"}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="relative">
        {slashOpen && (
          <div className="absolute bottom-full mb-1 w-full rounded-md border bg-popover p-1 text-xs shadow-md" role="listbox">
            {SLASH.filter((s) => s.cmd.startsWith(text)).map((s) => (
              <button
                key={s.cmd}
                type="button"
                role="option"
                aria-selected={false}
                className="block w-full rounded px-2 py-1 text-left hover:bg-accent"
                onClick={() => {
                  setText(s.cmd);
                  inputRef.current?.focus();
                }}
              >
                {s.hint}
              </button>
            ))}
          </div>
        )}
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send(text);
          }}
        >
          <Textarea
            ref={inputRef}
            rows={2}
            value={text}
            disabled={readOnly}
            aria-label="Message the agent"
            placeholder={readOnly ? "Estimate is final — clone it to change" : "Ask or instruct… (/ for commands)"}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(text);
              }
            }}
          />
          {busy ? (
            <Button type="button" size="icon" variant="outline" aria-label="Stop" onClick={() => void cancel()}>
              <Square />
            </Button>
          ) : (
            <Button type="submit" size="icon" disabled={readOnly || !sessionId} aria-label="Send">
              <Send />
            </Button>
          )}
        </form>
      </div>
      <div className="flex justify-between text-[11px] text-muted-foreground">
        <span>{session?.apply_mode === "review" ? "Review mode: every change waits for you" : "Auto mode: safe changes apply"}</span>
        <span className="tabular-nums" data-testid="agent-cost">
          AI use this session ${(session?.cost_usd ?? 0).toFixed(3)}
        </span>
      </div>
      {session && (
        <MemoryDrawer
          open={memOpen}
          onOpenChange={setMemOpen}
          estimateId={estimateId}
          session={session}
          onPatch={(p) => patch.mutate({ id: session.id, patch: p })}
        />
      )}
    </div>
  );
}
