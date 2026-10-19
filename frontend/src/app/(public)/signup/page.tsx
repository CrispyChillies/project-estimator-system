"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthCard } from "@/components/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { meKey } from "@/hooks/auth";
import { api, ApiError } from "@/lib/api";

export default function SignUpPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const { data: cfg } = useQuery({
    queryKey: ["auth-config"],
    queryFn: () => api<{ signup_mode: string; auth_mode: string }>("/auth/config"),
  });
  useEffect(() => {
    if (cfg?.auth_mode === "quick") router.replace("/signin");
  }, [cfg, router]);
  const [form, setForm] = useState({ name: "", email: "", password: "", invite_code: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const mode = cfg?.signup_mode;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password.length < 10) return setError("Password must be at least 10 characters");
    setBusy(true);
    setError(null);
    try {
      const me = await api("/auth/signup", {
        method: "POST",
        json: { ...form, invite_code: mode === "invite" ? form.invite_code : undefined },
      });
      qc.setQueryData(meKey, me);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the account. Try again.");
      setBusy(false);
    }
  };
  return (
    <AuthCard
      title="Create your account"
      description="Your workspace starts empty and private to you."
      footer={
        <>
          Already have an account? <Link className="underline underline-offset-4" href="/signin">Sign in</Link>
        </>
      }
    >
      {mode === "closed" ? (
        <p className="text-sm text-muted-foreground">Sign-up is closed. Ask an administrator for an account.</p>
      ) : (
        <form onSubmit={submit} className="space-y-3" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" autoComplete="name" required value={form.name} onChange={set("name")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={10}
              aria-describedby="pw-hint"
              value={form.password}
              onChange={set("password")}
            />
            <p id="pw-hint" className="text-xs text-muted-foreground">At least 10 characters.</p>
          </div>
          {mode === "invite" && (
            <div className="space-y-1.5">
              <Label htmlFor="invite">Invite code</Label>
              <Input id="invite" required value={form.invite_code} onChange={set("invite_code")} autoComplete="off" />
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <Button type="submit" className="w-full" disabled={busy || !form.name || !form.email || !form.password}>
            {busy ? "Creating account…" : "Create account"}
          </Button>
        </form>
      )}
    </AuthCard>
  );
}
