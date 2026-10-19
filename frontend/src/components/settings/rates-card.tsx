"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CurrencyToggle, FxNote } from "@/components/currency-toggle";
import { ColorPicker } from "@/components/settings/color-picker";
import { RoleTag } from "@/components/tags";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { meKey } from "@/hooks/auth";
import { useCurrency } from "@/hooks/currency";
import { errorToast, useCategories, useRoles } from "@/hooks/queries";
import { api } from "@/lib/api";
import { fromVnd, parseAmount } from "@/lib/money";
import type { Role } from "@/lib/types";

/** Amount field in the user's display currency; sends the typed amount + currency, the server stores canonical VND. */
function AmountInput({ vnd, label, disabled, onSave }: { vnd: number; label: string; disabled?: boolean; onSave: (amount: number) => void }) {
  const { currency, rate } = useCurrency();
  const shown = currency === "USD" ? fromVnd(vnd, currency, rate).toFixed(2) : String(Math.round(vnd));
  // remount when the stored value or display currency changes so the field always starts from the saved figure
  return <AmountField key={`${shown}-${currency}`} initial={shown} currency={currency} label={label} disabled={disabled} onSave={onSave} />;
}

function AmountField({ initial, currency, label, disabled, onSave }: { initial: string; currency: string; label: string; disabled?: boolean; onSave: (amount: number) => void }) {
  const [text, setText] = useState(initial);
  const commit = () => {
    const n = parseAmount(text);
    if (n === null || n <= 0) return setText(initial);
    if (text !== initial) onSave(n);
  };
  return (
    <div className="flex items-center justify-end gap-1">
      <Input
        className="h-7 w-28 text-right tabular-nums"
        inputMode="decimal"
        aria-label={label}
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && (e.currentTarget as HTMLInputElement).blur()}
      />
      <span className="w-4 text-xs text-muted-foreground">{currency === "USD" ? "$" : "₫"}</span>
    </div>
  );
}

function RateRow({ role, admin }: { role: Role; admin: boolean }) {
  const qc = useQueryClient();
  const { currency, money } = useCurrency();
  const done = (msg: string) => () => {
    void qc.invalidateQueries({ queryKey: ["roles"] });
    void qc.invalidateQueries({ queryKey: ["summary"] });
    toast.success(msg);
  };
  const mine = useMutation({
    mutationFn: (amount: number) => api<Role>(`/me/rates/${role.id}`, { method: "PUT", json: { amount, currency } }),
    onSuccess: done(`${role.name}: your rate saved`),
    onError: errorToast,
  });
  const reset = useMutation({
    mutationFn: () => api<Role>(`/me/rates/${role.id}`, { method: "DELETE" }),
    onSuccess: done(`${role.name}: back to the workspace rate`),
    onError: errorToast,
  });
  const def = useMutation({
    mutationFn: (amount: number) => api<Role>(`/roles/${role.id}`, { method: "PUT", json: { amount, currency } }),
    onSuccess: done(`${role.name}: workspace default saved`),
    onError: errorToast,
  });
  const color = useMutation({
    mutationFn: (c: string) => api("/me/colors", { method: "PUT", json: { kind: "role", ref: role.id, color: c } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["roles"] });
      void qc.invalidateQueries({ queryKey: meKey });
    },
    onError: errorToast,
  });
  return (
    <TableRow data-testid={`rate-row-${role.name}`}>
      <TableCell>
        <RoleTag id={role.id} />
      </TableCell>
      <TableCell className="text-right">
        {admin ? (
          <AmountInput vnd={role.hourly_rate_vnd} label={`Workspace default hourly rate for ${role.name}`} onSave={(a) => def.mutate(a)} />
        ) : (
          <span className="tabular-nums">{money(role.hourly_rate_vnd)}</span>
        )}
      </TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-1">
          <AmountInput vnd={role.rate_vnd} label={`Your hourly rate for ${role.name}`} onSave={(a) => mine.mutate(a)} />
          {role.my_rate_vnd ? (
            <Button size="icon-xs" variant="ghost" aria-label={`Reset your rate for ${role.name}`} onClick={() => reset.mutate()}>
              <RotateCcw />
            </Button>
          ) : (
            <span className="size-6" />
          )}
        </div>
      </TableCell>
      <TableCell className="text-right">
        <ColorPicker value={role.color} label={role.name} onPick={(c) => color.mutate(c)} />
      </TableCell>
    </TableRow>
  );
}

export function RatesCard({ admin }: { admin: boolean }) {
  const { data: roles } = useRoles();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Roles and rates</CardTitle>
        <CardDescription>
          Hourly billing rates. Cost = hours × rate. Type amounts in your display currency; they are stored in VND (rounded to 1.000 ₫).
          Your own rate only affects your figures.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <CurrencyToggle />
          <FxNote />
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Role</TableHead>
              <TableHead className="text-right">Workspace default / h</TableHead>
              <TableHead className="text-right">Your rate / h</TableHead>
              <TableHead className="text-right">Colour</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>{roles?.map((r) => <RateRow key={r.id} role={r} admin={admin} />)}</TableBody>
        </Table>
        {admin && <p className="text-xs text-muted-foreground">As admin you edit the workspace defaults; every member can override them for themselves.</p>}
      </CardContent>
    </Card>
  );
}

export function CategoriesCard() {
  const { data: categories } = useCategories();
  const qc = useQueryClient();
  const color = useMutation({
    mutationFn: ({ id, c }: { id: string; c: string }) => api("/me/colors", { method: "PUT", json: { kind: "category", ref: id, color: c } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["categories"] });
      void qc.invalidateQueries({ queryKey: meKey });
    },
    onError: errorToast,
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Task categories</CardTitle>
        <CardDescription>Related categories share a colour family. Pick your own colours; the label is always shown.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
        {categories?.map((c) => (
          <div key={c.id} className="flex items-start gap-2" data-testid={`category-row-${c.key}`}>
            <div className="min-w-0 flex-1">
              <TagTag id={c.id} />
              <div className="mt-0.5 text-xs text-muted-foreground">{c.description}</div>
            </div>
            <ColorPicker value={c.color} label={c.name} onPick={(t) => color.mutate({ id: c.id, c: t })} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

import { CategoryTag as TagTag } from "@/components/tags";
