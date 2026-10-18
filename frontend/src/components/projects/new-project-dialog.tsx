"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";
import { errorToast } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";

const schema = z.object({
  name: z.string().min(1, "Required").max(200),
  client_name: z.string().max(200),
  domain: z.string().max(100),
  description: z.string().max(5000),
});
type FormValues = z.infer<typeof schema>;

export function NewProjectDialog() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const qc = useQueryClient();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", client_name: "", domain: "", description: "" },
  });
  const create = useMutation({
    mutationFn: (v: FormValues) => api<Project>("/projects", { method: "POST", json: v }),
    onSuccess: (p) => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      setOpen(false);
      form.reset();
      router.push(`/projects/${p.id}`);
    },
    onError: errorToast,
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        <Plus /> New project
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={form.handleSubmit((v) => create.mutate(v))} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New project</DialogTitle>
            <DialogDescription>Create a project, then upload or paste the client brief.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="name">Name</Label>
              <Input id="name" autoFocus {...form.register("name")} />
              {form.formState.errors.name && (
                <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor="client">Client</Label>
                <Input id="client" {...form.register("client_name")} />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="domain">Domain</Label>
                <Input id="domain" placeholder="e.g. Logistics" {...form.register("domain")} />
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="desc">Description</Label>
              <Textarea id="desc" rows={3} {...form.register("description")} />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
