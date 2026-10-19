"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthCard } from "@/components/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const router = useRouter();
  const [pw, setPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api("/auth/reset", { method: "POST", json: { token, new_password: pw } });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reset the password.");
    }
  };
  if (!token) return <p className="text-sm text-muted-foreground">This link is incomplete. Ask your administrator for a new one.</p>;
  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="pw">New password</Label>
        <Input id="pw" type="password" autoComplete="new-password" minLength={10} value={pw} onChange={(e) => setPw(e.target.value)} />
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={pw.length < 10}>
        Set password and sign in
      </Button>
    </form>
  );
}

export default function ResetPage() {
  return (
    <AuthCard title="Choose a new password" description="Reset links work once and expire after 24 hours.">
      <Suspense>
        <ResetForm />
      </Suspense>
    </AuthCard>
  );
}
