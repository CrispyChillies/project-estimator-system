"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthCard } from "@/components/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { meKey } from "@/hooks/auth";
import { api, ApiError } from "@/lib/api";

function safeNext(n: string | null) {
  return n && n.startsWith("/") && !n.startsWith("//") ? n : "/dashboard";
}

function SignInForm() {
  const params = useSearchParams();
  const qc = useQueryClient();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api("/auth/login", { method: "POST", json: { email, password } });
      qc.setQueryData(meKey, me);
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in. Try again.");
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={busy || !email || !password}>
        {busy ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

function QuickForm({ onPassword }: { onPassword: () => void }) {
  const params = useSearchParams();
  const qc = useQueryClient();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api("/auth/quick", { method: "POST", json: { name, email: email || null } });
      qc.setQueryData(meKey, me);
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in. Try again.");
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="name">Your name</Label>
        <Input id="name" autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="email">Email (optional)</Label>
        <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <p className="text-xs text-muted-foreground">Use the same email next time to get back to your projects.</p>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={busy || !name.trim()}>
        {busy ? "Opening…" : "Continue"}
      </Button>
      <button type="button" className="w-full text-center text-xs text-muted-foreground underline-offset-4 hover:underline" onClick={onPassword}>
        Administrator? Sign in with a password
      </button>
    </form>
  );
}

function SignIn() {
  const { data: cfg, isError } = useQuery({
    queryKey: ["auth-config"],
    queryFn: () => api<{ signup_mode: string; auth_mode: string }>("/auth/config"),
    staleTime: 300_000,
    retry: 1,
  });
  const [password, setPassword] = useState(false);
  const quick = (cfg?.auth_mode ?? "quick") === "quick" && !password;
  return (
    <>
      {isError && (
        <p role="alert" className="mb-3 text-sm text-destructive">
          Can&apos;t reach the server right now. It may be starting up — try again in a minute.
        </p>
      )}
      {quick ? <QuickForm onPassword={() => setPassword(true)} /> : <SignInForm />}
    </>
  );
}

export default function SignInPage() {
  return (
    <AuthCard
      title="Sign in"
      description="Welcome back."
      footer={
        <>
          No account? <Link className="underline underline-offset-4" href="/signup">Create one</Link>
        </>
      }
    >
      <Suspense>
        <SignIn />
      </Suspense>
    </AuthCard>
  );
}
