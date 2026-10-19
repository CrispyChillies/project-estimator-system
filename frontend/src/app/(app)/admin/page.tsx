"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LearningCard, RetrievalCard } from "@/components/admin/learning-cards";
import { PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMe } from "@/hooks/auth";
import { errorToast } from "@/hooks/queries";
import { api } from "@/lib/api";

interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  archived: boolean;
  last_login_at: string | null;
  projects: number;
  spend_month: { calls: number; cost_usd: number; tokens: number };
  daily_usd_cap: number;
}

interface Usage {
  today: { user_id: string | null; name: string; calls: number; cost_usd: number; tokens: number }[];
  month: { user_id: string | null; name: string; calls: number; cost_usd: number; tokens: number }[];
  global: { budget_usd: number; spent_usd: number; user_daily_usd_cap: number };
  model: { mode: string; model: string; embedding_model: string };
}

interface Archive {
  description: string;
  include_archive_for_all: boolean;
  counts: Record<string, number>;
}

const usd = (n: number) => `$${n.toFixed(n < 1 ? 4 : 2)}`;

function CapInput({ user }: { user: AdminUser }) {
  const qc = useQueryClient();
  const [v, setV] = useState(String(user.daily_usd_cap));
  const save = useMutation({
    mutationFn: () => api(`/admin/users/${user.id}`, { method: "PATCH", json: { daily_usd_cap: Number(v) } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: errorToast,
  });
  return (
    <Input
      className="h-7 w-20 text-right"
      inputMode="decimal"
      aria-label={`Daily cap for ${user.name}`}
      value={v}
      onChange={(e) => setV(e.target.value)}
      onBlur={() => Number(v) !== user.daily_usd_cap && save.mutate()}
    />
  );
}

function UsersTab() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const { data: users } = useQuery({ queryKey: ["admin-users"], queryFn: () => api<AdminUser[]>("/admin/users") });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api(`/admin/users/${id}`, { method: "PATCH", json: body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: errorToast,
  });
  const [link, setLink] = useState<string | null>(null);
  const reset = useMutation({
    mutationFn: (id: string) => api<{ url: string }>(`/admin/users/${id}/reset-link`, { method: "POST" }),
    onSuccess: (r) => setLink(r.url),
    onError: errorToast,
  });
  const active = (users ?? []).filter((u) => !u.archived);
  return (
    <div className="space-y-3">
      {link && (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-2 pt-4 text-sm">
            <KeyRound className="size-4" /> One-time reset link (valid 24 h, shown once):
            <code className="max-w-full truncate rounded bg-muted px-1.5 py-0.5 text-xs">{link}</code>
            <Button
              size="xs"
              variant="outline"
              onClick={() => {
                void navigator.clipboard.writeText(link);
                toast.success("Copied");
              }}
            >
              <Copy /> Copy
            </Button>
          </CardContent>
        </Card>
      )}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last sign-in</TableHead>
              <TableHead className="text-right">Projects</TableHead>
              <TableHead className="text-right">AI spend (month)</TableHead>
              <TableHead>Daily cap $</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {active.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.name}</TableCell>
                <TableCell className="text-muted-foreground">{u.email}</TableCell>
                <TableCell>
                  <Badge variant={u.role === "admin" ? "default" : "secondary"}>{u.role}</Badge>
                </TableCell>
                <TableCell>{u.is_active ? "active" : "deactivated"}</TableCell>
                <TableCell className="text-xs">{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "—"}</TableCell>
                <TableCell className="text-right tabular-nums">{u.projects}</TableCell>
                <TableCell className="text-right tabular-nums">{usd(u.spend_month.cost_usd)}</TableCell>
                <TableCell>
                  <CapInput user={u} />
                </TableCell>
                <TableCell>
                  {u.id !== me?.id && (
                    <div className="flex justify-end gap-1">
                      <Button size="xs" variant="outline" onClick={() => patch.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                        {u.is_active ? "Deactivate" : "Activate"}
                      </Button>
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={() => patch.mutate({ id: u.id, body: { role: u.role === "admin" ? "member" : "admin" } })}
                      >
                        {u.role === "admin" ? "Demote" : "Promote"}
                      </Button>
                      <Button size="xs" variant="ghost" onClick={() => reset.mutate(u.id)}>
                        Reset link
                      </Button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs text-muted-foreground">
        {(users ?? []).length - active.length} archived author account(s) from the stored test data are kept for history and cannot sign in.
      </p>
    </div>
  );
}

function UsageTab() {
  const { data } = useQuery({ queryKey: ["admin-usage"], queryFn: () => api<Usage>("/admin/usage") });
  if (!data) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle>Global AI budget</CardTitle>
          <CardDescription>Set by the server environment; not editable here.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <div>
            Spent {usd(data.global.spent_usd)} of {usd(data.global.budget_usd)}
          </div>
          <div>Default per-user daily cap {usd(data.global.user_daily_usd_cap)}</div>
          <div className="text-xs text-muted-foreground">
            Model {data.model.model} · embeddings {data.model.embedding_model} · mode {data.model.mode}
          </div>
        </CardContent>
      </Card>
      {(["today", "month"] as const).map((k) => (
        <Card key={k}>
          <CardHeader>
            <CardTitle>{k === "today" ? "Today" : "This month"}</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead className="text-right">Calls</TableHead>
                  <TableHead className="text-right">Tokens</TableHead>
                  <TableHead className="text-right">USD</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data[k].map((r) => (
                  <TableRow key={r.user_id ?? "system"}>
                    <TableCell>{r.name}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.calls}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.tokens.toLocaleString()}</TableCell>
                    <TableCell className="text-right tabular-nums">{usd(r.cost_usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ArchiveTab() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-archive"], queryFn: () => api<Archive>("/admin/archive") });
  const set = useMutation({
    mutationFn: (v: boolean) => api("/admin/archive", { method: "PUT", json: { include_archive_for_all: v } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin-archive"] }),
    onError: errorToast,
  });
  if (!data) return null;
  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Data archive</CardTitle>
        <CardDescription>{data.description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid grid-cols-5 gap-2">
          {Object.entries(data.counts).map(([k, v]) => (
            <div key={k} className="rounded-md border p-2">
              <div className="text-xs text-muted-foreground">{k}</div>
              <div className="text-lg font-semibold tabular-nums">{v}</div>
            </div>
          ))}
        </div>
        <div className="flex items-start justify-between gap-4 rounded-md border p-3">
          <div>
            <Label htmlFor="archive-switch">Include archived reference library for all users</Label>
            <p className="text-xs text-muted-foreground">
              Off: members are never calibrated by, and never retrieve, the archived data. On: it appears in their similar-project
              references and calibration as &quot;Reference library&quot;, with a note wherever it is used.
            </p>
          </div>
          <Switch id="archive-switch" checked={data.include_archive_for_all} onCheckedChange={(v) => set.mutate(v)} />
        </div>
      </CardContent>
    </Card>
  );
}

export default function AdminPage() {
  const { data: me } = useMe();
  const router = useRouter();
  useEffect(() => {
    if (me && me.role !== "admin") router.replace("/dashboard");
  }, [me, router]);
  if (me?.role !== "admin") return null;
  return (
    <div className="space-y-4">
      <PageHeader title="Admin" description="Users, AI usage and caps, the data archive and learning settings." />
      <Tabs defaultValue="users">
        <TabsList>
          <TabsTrigger value="users">Users</TabsTrigger>
          <TabsTrigger value="usage">Usage and cost</TabsTrigger>
          <TabsTrigger value="archive">Data archive</TabsTrigger>
          <TabsTrigger value="learning">Learning</TabsTrigger>
        </TabsList>
        <TabsContent value="users" className="pt-3">
          <UsersTab />
        </TabsContent>
        <TabsContent value="usage" className="pt-3">
          <UsageTab />
        </TabsContent>
        <TabsContent value="archive" className="pt-3">
          <ArchiveTab />
        </TabsContent>
        <TabsContent value="learning" className="space-y-4 pt-3">
          <RetrievalCard />
          <LearningCard />
        </TabsContent>
      </Tabs>
    </div>
  );
}
