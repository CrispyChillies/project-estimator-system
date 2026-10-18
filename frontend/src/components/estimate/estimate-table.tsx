"use client";

import {
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, GripVertical, HelpCircle, MessageCircle, RotateCcw, Trash2 } from "lucide-react";
import { Fragment, useRef, useState } from "react";

import { ReasonChips } from "@/components/estimate/reason-chips";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { errorToast, useInvalidateEstimate, usePatchTask } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { Category, EstimateTree, ModuleOut, Role, TaskOut } from "@/lib/types";
import { cn } from "@/lib/utils";

export type Highlight = Record<string, "update" | "remove">;

const CONF: Record<string, string> = {
  low: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
  medium: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  high: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
};

function HoursInput({ value, disabled, onCommit, label }: { value: number; disabled: boolean; onCommit: (v: number) => void; label: string }) {
  const [draft, setDraft] = useState<string | null>(null);
  const committed = useRef(false);
  const commit = () => {
    if (draft === null || committed.current) return;
    committed.current = true; // Enter then blur must not send the same PATCH twice
    const v = Number(draft);
    setDraft(null);
    if (!Number.isNaN(v) && v >= 0 && v !== value) onCommit(v);
  };
  return (
    <Input
      aria-label={label}
      inputMode="decimal"
      className="h-7 w-16 text-right tabular-nums"
      disabled={disabled}
      value={draft ?? String(value)}
      onChange={(e) => {
        committed.current = false;
        setDraft(e.target.value);
      }}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          commit();
          (e.target as HTMLInputElement).blur();
        }
        if (e.key === "Escape") setDraft(null);
      }}
    />
  );
}

function TaskRow({
  task,
  estimateId,
  readOnly,
  roles,
  categories,
  highlight,
  onWhy,
}: {
  task: TaskOut;
  estimateId: string;
  readOnly: boolean;
  roles: Role[];
  categories: Category[];
  highlight?: "update" | "remove";
  onWhy: (t: TaskOut) => void;
}) {
  const patch = usePatchTask(estimateId);
  const invalidate = useInvalidateEstimate();
  const [reason, setReason] = useState<number | null>(null);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: task.id, disabled: readOnly });
  const del = useMutation({
    mutationFn: () => api<TaskOut>(`/tasks/${task.id}${task.removed ? "/restore" : ""}`, { method: task.removed ? "POST" : "DELETE" }),
    onSuccess: () => invalidate(estimateId),
    onError: errorToast,
  });

  const setHours = (min: number, max: number) => {
    if (max < min) {
      errorToast(new Error("Max must be ≥ min"));
      return;
    }
    const oldMid = (task.min_hours + task.max_hours) / 2;
    const newMid = (min + max) / 2;
    patch.mutate(
      { id: task.id, patch: { min_hours: min, max_hours: max } },
      {
        onSuccess: () => {
          const d = oldMid > 0 ? (newMid / oldMid - 1) * 100 : 0;
          if (Math.abs(d) > 20) setReason(d);
        },
      },
    );
  };

  return (
    <>
      <TableRow
        ref={setNodeRef}
        style={{ transform: CSS.Transform.toString(transform), transition }}
        className={cn(
          "group transition-colors",
          (!task.enabled || task.removed) && "opacity-50",
          task.removed && "line-through",
          highlight === "update" && "bg-emerald-500/10",
          highlight === "remove" && "bg-rose-500/10",
          isDragging && "relative z-10 bg-background shadow",
        )}
      >
        <TableCell className="w-6 pl-2">
          {!readOnly && (
            <button type="button" aria-label="Drag" className="cursor-grab text-muted-foreground" {...attributes} {...listeners}>
              <GripVertical className="size-4" />
            </button>
          )}
        </TableCell>
        <TableCell className="min-w-56 pl-6">
          <div className="flex items-center gap-1.5">
            <span className="truncate" title={task.description}>
              {task.title}
            </span>
            {task.origin !== "ai" && (
              <Badge variant="outline" className="text-[10px]">
                {task.origin}
              </Badge>
            )}
          </div>
        </TableCell>
        <TableCell>
          <Select
            value={task.category_id}
            disabled={readOnly}
            onValueChange={(v) => v && patch.mutate({ id: task.id, patch: { category_id: v } })}
            items={categories.map((c) => ({ value: c.id, label: c.name }))}
          >
            <SelectTrigger size="sm" className="h-7 w-40">
              <SelectValue placeholder="—" />
            </SelectTrigger>
            <SelectContent>
              {categories.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </TableCell>
        <TableCell>
          <Select
            value={task.delivery_role_id}
            disabled={readOnly}
            onValueChange={(v) => v && patch.mutate({ id: task.id, patch: { delivery_role_id: v } })}
            items={roles.map((r) => ({ value: r.id, label: r.name }))}
          >
            <SelectTrigger size="sm" className="h-7 w-32">
              <SelectValue placeholder="—" />
            </SelectTrigger>
            <SelectContent>
              {roles.map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  {r.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </TableCell>
        <TableCell>
          <HoursInput label="Min hours" value={task.min_hours} disabled={readOnly} onCommit={(v) => setHours(v, Math.max(v, task.max_hours))} />
        </TableCell>
        <TableCell>
          <HoursInput label="Max hours" value={task.max_hours} disabled={readOnly} onCommit={(v) => setHours(Math.min(task.min_hours, v), v)} />
        </TableCell>
        <TableCell>
          <Badge variant="secondary" className={CONF[task.confidence]}>
            {task.confidence}
          </Badge>
        </TableCell>
        <TableCell>
          {task.delta_pct !== null && task.delta_pct !== undefined ? (
            <Badge variant="outline" className={task.delta_pct > 0 ? "text-amber-600" : "text-sky-600"}>
              {task.delta_pct > 0 ? "+" : ""}
              {task.delta_pct.toFixed(0)}%
            </Badge>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </TableCell>
        <TableCell>
          <Switch
            size="sm"
            checked={task.enabled}
            disabled={readOnly || task.removed}
            onCheckedChange={(c) => patch.mutate({ id: task.id, patch: { enabled: c } })}
            aria-label="Enabled"
          />
        </TableCell>
        <TableCell className="text-right">
          <div className="flex items-center justify-end gap-0.5">
            {task.comment_count > 0 && (
              <Tooltip>
                <TooltipTrigger render={<span className="flex items-center gap-0.5 px-1 text-xs text-muted-foreground" />}>
                  <MessageCircle className="size-3.5" />
                  {task.comment_count}
                </TooltipTrigger>
                <TooltipContent>{task.comment_count} edit events</TooltipContent>
              </Tooltip>
            )}
            <Tooltip>
              <TooltipTrigger render={<Button variant="ghost" size="icon-xs" aria-label="Why this number?" onClick={() => onWhy(task)} />}>
                <HelpCircle />
              </TooltipTrigger>
              <TooltipContent>Why this number?</TooltipContent>
            </Tooltip>
            {!readOnly && (
              <Button variant="ghost" size="icon-xs" aria-label={task.removed ? "Restore" : "Remove"} onClick={() => del.mutate()}>
                {task.removed ? <RotateCcw /> : <Trash2 />}
              </Button>
            )}
          </div>
        </TableCell>
      </TableRow>
      {reason !== null && (
        <TableRow>
          <TableCell />
          <TableCell colSpan={9}>
            <ReasonChips taskId={task.id} estimateId={estimateId} deltaPct={reason} onClose={() => setReason(null)} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

function ModuleRows({
  module,
  order,
  ...rest
}: {
  module: ModuleOut;
  order: string[] | undefined;
  estimateId: string;
  readOnly: boolean;
  roles: Role[];
  categories: Category[];
  highlight: Highlight;
  showRemoved: boolean;
  onWhy: (t: TaskOut) => void;
}) {
  const [open, setOpen] = useState(true);
  const tasks = visibleTasks(module, rest.showRemoved);
  const ordered = order ? order.map((id) => tasks.find((t) => t.id === id)).filter((t): t is TaskOut => !!t) : tasks;
  const live = (module.tasks ?? []).filter((t) => t.enabled && !t.removed);
  const min = live.reduce((s, t) => s + t.min_hours, 0);
  const max = live.reduce((s, t) => s + t.max_hours, 0);
  if (module.removed && !rest.showRemoved) return null;
  return (
    <SortableContext items={ordered.map((t) => t.id)} strategy={verticalListSortingStrategy}>
        <TableRow className="bg-muted/40 hover:bg-muted/60">
          <TableCell className="pl-2">
            <Button variant="ghost" size="icon-xs" onClick={() => setOpen((o) => !o)} aria-label={open ? "Collapse" : "Expand"}>
              {open ? <ChevronDown /> : <ChevronRight />}
            </Button>
          </TableCell>
          <TableCell colSpan={3} className="font-medium">
            {module.name}
            <span className="ml-2 text-xs font-normal text-muted-foreground">{live.length} tasks</span>
          </TableCell>
          <TableCell className="text-right text-xs tabular-nums">{min.toFixed(1)}</TableCell>
          <TableCell className="text-right text-xs tabular-nums">{max.toFixed(1)}</TableCell>
          <TableCell colSpan={4} />
        </TableRow>
        {open &&
          ordered.map((t) => (
            <Fragment key={t.id}>
              <TaskRow task={t} {...rest} highlight={rest.highlight[t.id]} />
            </Fragment>
          ))}
      </SortableContext>
  );
}

function visibleTasks(module: ModuleOut, showRemoved: boolean): TaskOut[] {
  return (module.tasks ?? []).filter((t) => showRemoved || !t.removed).sort((a, b) => a.position - b.position);
}

export function EstimateTable({
  tree,
  roles,
  categories,
  highlight,
  showRemoved,
  onWhy,
}: {
  tree: EstimateTree;
  roles: Role[];
  categories: Category[];
  highlight: Highlight;
  showRemoved: boolean;
  onWhy: (t: TaskOut) => void;
}) {
  const readOnly = tree.estimate.status === "final";
  const estimateId = tree.estimate.id;
  const invalidate = useInvalidateEstimate();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const [orders, setOrders] = useState<Record<string, string[]>>({});
  const reorder = useMutation({
    mutationFn: ({ moduleId, ids }: { moduleId: string; ids: string[] }) =>
      api<void>(`/estimates/${estimateId}/tasks/reorder`, { method: "POST", json: { module_id: moduleId, task_ids: ids } }),
    onSettled: () => {
      setOrders({});
      invalidate(estimateId);
    },
    onError: errorToast,
  });
  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    const mod = tree.modules.find((m) => (m.tasks ?? []).some((t) => t.id === e.active.id));
    if (!mod || !(mod.tasks ?? []).some((t) => t.id === e.over?.id)) return; // reorder within a module only
    const ids = orders[mod.id] ?? visibleTasks(mod, showRemoved).map((t) => t.id);
    const next = arrayMove(ids, ids.indexOf(String(e.active.id)), ids.indexOf(String(e.over.id)));
    setOrders((o) => ({ ...o, [mod.id]: next }));
    reorder.mutate({ moduleId: mod.id, ids: next });
  };
  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-6" />
            <TableHead>Title</TableHead>
            <TableHead>Category</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Min</TableHead>
            <TableHead>Max</TableHead>
            <TableHead>Conf.</TableHead>
            <TableHead>Δ vs AI</TableHead>
            <TableHead>On</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {tree.modules
            .slice()
            .sort((a, b) => a.position - b.position)
            .map((m) => (
              <ModuleRows
                key={m.id}
                module={m}
                order={orders[m.id]}
                estimateId={tree.estimate.id}
                readOnly={readOnly}
                roles={roles}
                categories={categories}
                highlight={highlight}
                showRemoved={showRemoved}
                onWhy={onWhy}
              />
            ))}
        </TableBody>
      </Table>
    </div>
    </DndContext>
  );
}
