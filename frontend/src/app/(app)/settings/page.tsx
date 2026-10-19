"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTheme } from "next-themes";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useMe } from "@/hooks/auth";
import { errorToast, useCategories, useRoles } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { Role } from "@/lib/types";

function RateRow({ role, editable }: { role: Role; editable: boolean }) {
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
        {editable ? (
          <Input
            className="h-7 w-24 text-right"
            inputMode="decimal"
            aria-label={`Hourly rate for ${role.name}`}
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            onBlur={() => Number(rate) !== role.hourly_rate && save.mutate()}
          />
        ) : (
          <span className="tabular-nums">{role.hourly_rate}</span>
        )}
      </TableCell>
      <TableCell>{role.currency}</TableCell>
    </TableRow>
  );
}

function Appearance() {
  const { theme, setTheme } = useTheme();
  const [density, setDensity] = useState(() =>
    typeof window === "undefined" ? "comfortable" : (window.localStorage.getItem("calibr.density") ?? "comfortable"),
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
        <CardDescription>Stored in this browser.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center justify-between gap-2">
          <span>Theme</span>
          <ToggleGroup value={[theme ?? "system"]} onValueChange={(v) => v.length && setTheme(String(v[0]))} size="sm" variant="outline" aria-label="Theme">
            <ToggleGroupItem value="light">Light</ToggleGroupItem>
            <ToggleGroupItem value="dark">Dark</ToggleGroupItem>
            <ToggleGroupItem value="system">System</ToggleGroupItem>
          </ToggleGroup>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span>Table density</span>
          <ToggleGroup
            value={[density]}
            onValueChange={(v) => {
              if (!v.length) return;
              const d = String(v[0]);
              setDensity(d);
              window.localStorage.setItem("calibr.density", d);
              document.documentElement.dataset.density = d;
            }}
            size="sm"
            variant="outline"
            aria-label="Table density"
          >
            <ToggleGroupItem value="comfortable">Comfortable</ToggleGroupItem>
            <ToggleGroupItem value="compact">Compact</ToggleGroupItem>
          </ToggleGroup>
        </div>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { data: me } = useMe();
  const { data: roles } = useRoles();
  const { data: categories } = useCategories();
  const admin = me?.role === "admin";
  const currency = roles?.[0]?.currency ?? "EUR";
  return (
    <div className="space-y-4">
      <PageHeader title="Settings" description="Your preferences and the workspace reference data used for cost." />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
            <CardDescription>{me?.email}</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            <Link href="/profile" className="underline underline-offset-4">
              Edit name and password
            </Link>
          </CardContent>
        </Card>
        <Appearance />
        <Card>
          <CardHeader>
            <CardTitle>Units and currency</CardTitle>
            <CardDescription>How numbers are shown.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div>Effort: hours for one mid-level engineer of the task&apos;s role.</div>
            <div>Ranges: min–max hours; totals show P50 and P80.</div>
            <div>Currency: {currency} (from the rate card).</div>
          </CardContent>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Roles and rates</CardTitle>
            <CardDescription>
              Cost = midpoint hours × rate. {admin ? "You can edit rates for the workspace." : "Rates are set by your administrator."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Role</TableHead>
                  <TableHead>Rate/h</TableHead>
                  <TableHead>Currency</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>{roles?.map((r) => <RateRow key={r.id} role={r} editable={admin} />)}</TableBody>
            </Table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Task categories</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-1 text-sm sm:grid-cols-2">
            {categories?.map((c) => (
              <div key={c.id}>
                <span className="font-medium">{c.name}</span>
                <div className="text-xs text-muted-foreground">{c.description}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
