"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Info, RotateCcw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { errorToast, useLearningSettings } from "@/hooks/queries";
import { api } from "@/lib/api";

const isRetrievalKey = (k: string) => k.startsWith("retrieval_") || k === "analog_blend_enabled";

export function RetrievalCard() {
  const { data } = useLearningSettings();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: (values: Record<string, unknown>) => api("/admin/learning", { method: "PUT", json: values }),
    onSuccess: () => {
      setDraft({});
      void qc.invalidateQueries({ queryKey: ["learning-settings"] });
      toast.success("Retrieval settings saved");
    },
    onError: errorToast,
  });
  if (!data) return <Skeleton className="h-48" />;
  const entries = Object.entries(data.values).filter(([k]) => isRetrievalKey(k));
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Retrieval (similar past projects)</CardTitle>
            <CardDescription>
              The k most similar past projects are added as context to decomposition and estimation. Below the threshold
              fewer are used — never padded.
            </CardDescription>
          </div>
          <Button
            size="sm"
            aria-label="Save retrieval settings"
            disabled={!Object.keys(draft).length}
            onClick={() => save.mutate(Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, Number(v)])))}
          >
            Save
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-2 sm:grid-cols-2">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between gap-2 rounded-md border px-2 py-1.5">
            <div className="text-sm">
              <code className="text-xs">{k}</code>
              <div className="text-xs text-muted-foreground">{data.descriptions[k]}</div>
            </div>
            {typeof v === "boolean" ? (
              <Switch checked={v} aria-label={k} onCheckedChange={(c) => save.mutate({ [k]: c })} />
            ) : (
              <Input
                className="h-7 w-20 text-right"
                inputMode="decimal"
                aria-label={k}
                value={draft[k] ?? String(v)}
                onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
              />
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function LearningCard() {
  const { data } = useLearningSettings();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () =>
      api("/admin/learning", {
        method: "PUT",
        json: Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, Number(v)])),
      }),
    onSuccess: () => {
      setDraft({});
      void qc.invalidateQueries({ queryKey: ["learning-settings"] });
      toast.success("Hyperparameters saved");
    },
    onError: errorToast,
  });
  const reset = useMutation({
    mutationFn: () => api("/admin/learning/reset", { method: "POST" }),
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
        {Object.entries(data.values).filter(([k]) => !isRetrievalKey(k)).map(([k, v]) => (
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

