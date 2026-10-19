"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { meKey, useMe } from "@/hooks/auth";
import { errorToast } from "@/hooks/queries";
import { api } from "@/lib/api";

interface Allowance {
  spent_today_usd: number;
  daily_cap_usd: number;
  remaining_usd: number;
}

export default function ProfilePage() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [name, setName] = useState<string | null>(null);
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const { data: allowance } = useQuery({ queryKey: ["me-usage"], queryFn: () => api<Allowance>("/me/usage") });
  const saveName = useMutation({
    mutationFn: () => api("/auth/me", { method: "PATCH", json: { name } }),
    onSuccess: (m) => {
      qc.setQueryData(meKey, m);
      setName(null);
      toast.success("Name saved");
    },
    onError: errorToast,
  });
  const changePw = useMutation({
    mutationFn: () => api("/auth/password", { method: "POST", json: pw }),
    onSuccess: () => {
      setPw({ current_password: "", new_password: "" });
      toast.success("Password changed. Other sessions were signed out.");
    },
    onError: errorToast,
  });
  if (!me) return null;
  return (
    <div className="max-w-2xl space-y-4">
      <PageHeader title="Profile" />
      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>{me.email}</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              saveName.mutate();
            }}
          >
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="name">Name</Label>
              <Input id="name" value={name ?? me.name} onChange={(e) => setName(e.target.value)} />
            </div>
            <Button type="submit" disabled={!name || name === me.name}>
              Save
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Change password</CardTitle>
          <CardDescription>At least 10 characters. Other signed-in sessions are signed out.</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              changePw.mutate();
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="cur">Current password</Label>
              <Input id="cur" type="password" autoComplete="current-password" value={pw.current_password}
                onChange={(e) => setPw((p) => ({ ...p, current_password: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="new">New password</Label>
              <Input id="new" type="password" autoComplete="new-password" value={pw.new_password}
                onChange={(e) => setPw((p) => ({ ...p, new_password: e.target.value }))} />
            </div>
            <Button type="submit" disabled={!pw.current_password || pw.new_password.length < 10}>
              Change password
            </Button>
          </form>
        </CardContent>
      </Card>
      {allowance && (
        <Card>
          <CardHeader>
            <CardTitle>AI allowance</CardTitle>
            <CardDescription>Resets every day at 00:00 UTC.</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            Used today ${allowance.spent_today_usd.toFixed(2)} of ${allowance.daily_cap_usd.toFixed(2)}.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
