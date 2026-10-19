"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Share2, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { errorToast, qk } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";

interface Member {
  user_id: string;
  name: string;
  email: string;
  role: "owner" | "viewer" | "editor";
}

export function ShareDialog({ project }: { project: Project }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"viewer" | "editor">("viewer");
  const key = ["members", project.id];
  const { data: members } = useQuery({ queryKey: key, queryFn: () => api<Member[]>(`/projects/${project.id}/members`) });
  const refresh = () => void qc.invalidateQueries({ queryKey: key });
  const add = useMutation({
    mutationFn: () => api(`/projects/${project.id}/members`, { method: "POST", json: { email, role } }),
    onSuccess: () => {
      setEmail("");
      refresh();
      toast.success("Shared");
    },
    onError: errorToast,
  });
  const remove = useMutation({
    mutationFn: (uid: string) => api(`/projects/${project.id}/members/${uid}`, { method: "DELETE" }),
    onSuccess: refresh,
    onError: errorToast,
  });
  const workspace = useMutation({
    mutationFn: (v: boolean) => api(`/projects/${project.id}`, { method: "PATCH", json: { shared_to_workspace: v } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.project(project.id) }),
    onError: errorToast,
  });
  return (
    <Dialog>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        <Share2 /> Share
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Share “{project.name}”</DialogTitle>
          <DialogDescription>People you add must already have an account. Viewers can read; editors can change the estimate.</DialogDescription>
        </DialogHeader>
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="share-email">Email</Label>
            <Input id="share-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <Select
            value={role}
            onValueChange={(v) => v && setRole(v as "viewer" | "editor")}
            items={[{ value: "viewer", label: "Viewer" }, { value: "editor", label: "Editor" }]}
          >
            <SelectTrigger className="w-28" aria-label="Access level">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="viewer">Viewer</SelectItem>
              <SelectItem value="editor">Editor</SelectItem>
            </SelectContent>
          </Select>
          <Button type="submit" disabled={!email}>
            Add
          </Button>
        </form>
        <ul className="space-y-1 text-sm">
          {members?.map((m) => (
            <li key={m.user_id} className="flex items-center justify-between rounded-md border px-2 py-1.5">
              <span>
                {m.name} <span className="text-muted-foreground">· {m.email}</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="text-xs text-muted-foreground">{m.role}</span>
                {m.role !== "owner" && (
                  <Button size="icon-xs" variant="ghost" aria-label={`Remove ${m.name}`} onClick={() => remove.mutate(m.user_id)}>
                    <Trash2 />
                  </Button>
                )}
              </span>
            </li>
          ))}
        </ul>
        <div className="flex items-start justify-between gap-3 rounded-md border p-3">
          <div>
            <Label htmlFor="ws-share">Share history with the workspace</Label>
            <p className="text-xs text-muted-foreground">
              When this project is finalized or delivered, its numbers may calibrate other people&apos;s estimates and appear in their
              similar-project references. Its documents stay private.
            </p>
          </div>
          <Switch id="ws-share" checked={!!project.shared_to_workspace} onCheckedChange={(v) => workspace.mutate(v)} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
