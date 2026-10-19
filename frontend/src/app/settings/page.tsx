"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Info, RotateCcw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { errorToast, useCategories, useLearningSettings, useLLMUsage, useRoles } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { Role } from "@/lib/types";

function RateRow({ role }: { role: Role }) {
  const [rate, setRate] = useState(String(role.hourly_rate));
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => api<Role>(`/roles/${role.id}`, { method: "PUT", json: { hourly_rate: Number(rate), currency: role.currency } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["roles"] });
      toast.success(`${role.name} rate saved`);
    },
    onError: errorToast,
  });
  return (
    <TableRow>
      <TableCell>
        <span className="mr-2 inline-block size-2.5 rounded-full" style={{ background: role.color }} />
        {role.name}
      </TableCell>
      <TableCell>
        <Input
          className="h-7 w-24 text-right"
          inputMode="decimal"
          value={rate}
          onChange={(e) => setRate(e.target.value)}
          onBlur={() => Number(rate) !== role.hourly_rate && save.mutate()}
        />
      </TableCell>
      <TableCell>{role.currency}</TableCell>
    </TableRow>
  );
}

function LearningCard() {
  const { data } = useLearningSettings();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () =>
      api("/settings/learning", {
        method: "PUT",
        json: Object.fromEntries(
          Object.entries(draft).map(([k, v]) => [k, v === "true" ? true : v === "false" ? false : Number(v)]),
        ),
      }),
    onSuccess: () => {
      setDraft({});
      void qc.invalidateQueries({ queryKey: ["learning-settings"] });
      toast.success("Hyperparameters saved");
    },
    onError: errorToast,
  });
  const reset = useMutation({
    mutationFn: () => api("/settings/learning/reset", { method: "POST" }),
    onSuccess: () => {
      setDraft({});
      void qc.invalidateQueries({ queryKey: ["learning-settings"] });
    },
  });
  if (!data) return <Skeleton className="h-96" />;
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Learning hyperparameters</CardTitle>
            <CardDescription>See docs/LEARNING.md for the math and rationale.</CardDescription>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => reset.mutate()}>
              <RotateCcw /> Defaults
            </Button>
            <Button size="sm" onClick={() => save.mutate()} disabled={!Object.keys(draft).length}>
              Save
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-2 sm:grid-cols-2">
        {Object.entries(data.values).map(([k, v]) => (
          <div key={k} className="flex items-center justify-between gap-2 rounded-md border px-2 py-1.5">
            <div className="flex items-center gap-1 text-sm">
              <code className="text-xs">{k}</code>
              {data.descriptions[k] && (
                <Tooltip>
                  <TooltipTrigger render={<span className="text-muted-foreground" />}>
                    <Info className="size-3.5" />
                  </TooltipTrigger>
                  <TooltipContent>{data.descriptions[k]}</TooltipContent>
                </Tooltip>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              {String(draft[k] ?? v) !== String(data.defaults[k]) && (
                <span className="text-[10px] text-muted-foreground">default {data.defaults[k]}</span>
              )}
              <Input
                className="h-7 w-24 text-right"
                inputMode="decimal"
                value={draft[k] ?? String(v)}
                onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
              />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { data: roles } = useRoles();
  const { data: categories } = useCategories();
  const { data: usage } = useLLMUsage();
  const qc = useQueryClient();
  const resetLearning = useMutation({
    mutationFn: () => api("/admin/reset-learning", { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries();
      toast.success("Learned data cleared. Edit history and actuals are kept; use Insights → recompute to rebuild.");
    },
    onError: errorToast,
  });
  return (
    <div className="space-y-4">
      <PageHeader title="Settings" />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Rate cards</CardTitle>
            <CardDescription>Used for cost (mid hours × rate)</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Role</TableHead>
                  <TableHead>Rate/h</TableHead>
                  <TableHead>Cur.</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>{roles?.map((r) => <RateRow key={r.id} role={r} />)}</TableBody>
            </Table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>LLM</CardTitle>
            <CardDescription>Every call goes through one gateway and is logged.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex flex-wrap gap-1.5">
              <Badge>mode: {usage?.mode ?? "…"}</Badge>
              <Badge variant="outline">chat: {usage?.model}</Badge>
              <Badge variant="outline">embeddings: {usage?.embedding_model}</Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 pt-2">
              <div>
                <div className="text-xs text-muted-foreground">Calls</div>
                <div className="text-lg font-semibold">{usage?.calls ?? 0}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Cache hits</div>
                <div className="text-lg font-semibold">{usage?.cache_hits ?? 0}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Tokens in / out</div>
                <div className="font-medium">
                  {(usage?.input_tokens ?? 0).toLocaleString()} / {(usage?.output_tokens ?? 0).toLocaleString()}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Est. cost (this DB)</div>
                <div className="font-medium">${(usage?.cost_usd ?? 0).toFixed(4)}</div>
              </div>
              <div className="col-span-2">
                <div className="text-xs text-muted-foreground">Live spend, all time (ledger) vs budget</div>
                <div className="font-medium">
                  ${(usage?.ledger_cost_usd ?? 0).toFixed(4)} of ${(usage?.budget_usd ?? 0).toFixed(2)}
                </div>
              </div>
            </div>
            <p className="pt-2 text-xs text-muted-foreground">
              Client documents are sent to OpenAI in live/record mode. PII redaction (LLM_REDACT_PII) is future work.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Demo data & reset</CardTitle>
            <CardDescription>Seed with `make seed`. Synthetic and dataset projects are always badged.</CardDescription>
          </CardHeader>
          <CardContent>
            <AlertDialog>
              <AlertDialogTrigger render={<Button variant="destructive" size="sm" />}>Reset learned data</AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Reset learned data?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Deletes calibration stats, calibration runs and learned rules. The append-only edit log, baselines and
                    actuals are preserved, so learning can be recomputed at any time.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={() => resetLearning.mutate()}>Reset</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </CardContent>
        </Card>
      </div>
      <LearningCard />
      <Card>
        <CardHeader>
          <CardTitle>Task categories</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
          {categories?.map((c) => (
            <div key={c.id}>
              <span className="font-medium">{c.name}</span> <code className="text-xs text-muted-foreground">{c.key}</code>
              <div className="text-xs text-muted-foreground">{c.description}</div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
