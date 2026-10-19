"use client";

import { useMutation } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useEstimateJobs } from "@/hooks/estimate-jobs";
import { errorToast, useInvalidateEstimate } from "@/hooks/queries";
import { api } from "@/lib/api";
import { CategoryTag, RoleTag } from "@/components/tags";
import type { Category, ModuleOut, Role, TaskOut } from "@/lib/types";

const NEW_MODULE = "__new__";
const AUTO = "__auto__";

export function AddTaskDialog({
  estimateId,
  modules,
  roles,
  categories,
}: {
  estimateId: string;
  modules: ModuleOut[];
  roles: Role[];
  categories: Category[];
}) {
  const live = modules.filter((m) => !m.removed);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [moduleId, setModuleId] = useState<string>(live[0]?.id ?? NEW_MODULE);
  const [newModule, setNewModule] = useState("");
  const [categoryId, setCategoryId] = useState(AUTO);
  const [roleId, setRoleId] = useState(AUTO);
  const [estimate, setEstimate] = useState(true);
  const invalidate = useInvalidateEstimate();
  const { start } = useEstimateJobs();

  const create = useMutation({
    mutationFn: async () => {
      let mid = moduleId;
      if (mid === NEW_MODULE || !live.some((m) => m.id === mid)) {
        const m = await api<{ id: string }>(`/estimates/${estimateId}/modules`, {
          method: "POST",
          json: { name: newModule.trim() || "Additional scope" },
        });
        mid = m.id;
      }
      return api<TaskOut>(`/estimates/${estimateId}/tasks`, {
        method: "POST",
        json: {
          module_id: mid,
          title: title.trim(),
          description,
          category_id: categoryId === AUTO ? null : categoryId,
          delivery_role_id: roleId === AUTO ? null : roleId,
          min_hours: 0,
          max_hours: 0,
          reason_tag: "scope_added",
        },
      });
    },
    onSuccess: (t) => {
      invalidate(estimateId);
      setOpen(false);
      setTitle("");
      setDescription("");
      if (estimate) void start(estimateId, [t.id]);
      else toast.success("Task added — set hours or use “AI estimate”");
    },
    onError: errorToast,
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        <Plus /> Add task
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add task</DialogTitle>
          <DialogDescription>
            Add scope the AI missed. Leave category and role on “Auto” and let the AI pick, or choose them yourself.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="at-title">Title</Label>
            <Input id="at-title" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="at-desc">Description (helps the estimate)</Label>
            <Textarea id="at-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>Module</Label>
              <Select
                value={moduleId}
                onValueChange={(v) => v && setModuleId(v)}
                items={[...live.map((m) => ({ value: m.id, label: m.name })), { value: NEW_MODULE, label: "New module…" }]}
              >
                <SelectTrigger aria-label="Module">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {live.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.name}
                    </SelectItem>
                  ))}
                  <SelectItem value={NEW_MODULE}>New module…</SelectItem>
                </SelectContent>
              </Select>
              {moduleId === NEW_MODULE && (
                <Input placeholder="New module name" value={newModule} onChange={(e) => setNewModule(e.target.value)} />
              )}
            </div>
            <div className="grid gap-1.5">
              <Label>Role</Label>
              <Select
                value={roleId}
                onValueChange={(v) => v && setRoleId(v)}
                items={[{ value: AUTO, label: "Auto" }, ...roles.map((r) => ({ value: r.id, label: r.name }))]}
              >
                <SelectTrigger aria-label="Role">
                  <SelectValue>{(v: string | null) => (v && v !== AUTO ? <RoleTag id={v} /> : "Auto")}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={AUTO}>Auto</SelectItem>
                  {roles.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      <RoleTag id={r.id} />
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label>Category</Label>
            <Select
              value={categoryId}
              onValueChange={(v) => v && setCategoryId(v)}
              items={[{ value: AUTO, label: "Auto" }, ...categories.map((c) => ({ value: c.id, label: c.name }))]}
            >
              <SelectTrigger aria-label="Category">
                <SelectValue>{(v: string | null) => (v && v !== AUTO ? <CategoryTag id={v} /> : "Auto")}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={AUTO}>Auto</SelectItem>
                {categories.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    <CategoryTag id={c.id} />
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={estimate} onCheckedChange={(c) => setEstimate(!!c)} />
            Estimate with AI in the background after adding
          </label>
        </div>
        <DialogFooter>
          <Button onClick={() => create.mutate()} disabled={!title.trim() || create.isPending}>
            Add task
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
