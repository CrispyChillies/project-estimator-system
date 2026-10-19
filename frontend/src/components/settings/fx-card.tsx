"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { FxNote } from "@/components/currency-toggle";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCurrency, type Fx } from "@/hooks/currency";
import { errorToast } from "@/hooks/queries";
import { api } from "@/lib/api";
import { parseAmount } from "@/lib/money";

/** Admin: USD/VND workspace rate (manual, or fetched from the public provider). */
export function FxCard() {
  const { fx, rate } = useCurrency();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const done = (m: string) => (d: Fx) => {
    qc.setQueryData(["fx"], d);
    void qc.invalidateQueries({ queryKey: ["summary"] });
    setText("");
    toast.success(m);
  };
  const save = useMutation({
    mutationFn: (r: number) => api<Fx>("/admin/fx", { method: "PUT", json: { rate: r } }),
    onSuccess: done("Exchange rate saved"),
    onError: errorToast,
  });
  const refresh = useMutation({
    mutationFn: () => api<Fx>("/admin/fx/refresh", { method: "POST" }),
    onSuccess: done("Exchange rate updated from the provider"),
    onError: errorToast,
  });
  const n = parseAmount(text);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Exchange rate</CardTitle>
        <CardDescription>
          VND is the canonical currency; USD is a conversion at this rate. Source: {fx?.rate_source ?? "default"}
          {fx?.auto_update ? " (auto-update on, manual rates are never overwritten)" : ""}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <FxNote />
        <div className="flex flex-wrap items-center gap-2">
          <Input
            className="h-8 w-36 text-right tabular-nums"
            inputMode="decimal"
            aria-label="VND per 1 USD"
            placeholder={String(Math.round(rate))}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <span className="text-xs text-muted-foreground">₫ per USD</span>
          <Button size="sm" disabled={n === null || n <= 0 || save.isPending} onClick={() => n && save.mutate(n)}>
            Save rate
          </Button>
          <Button size="sm" variant="outline" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            Fetch current rate
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">AI usage and spending caps stay in USD (the provider&apos;s billing currency).</p>
      </CardContent>
    </Card>
  );
}
