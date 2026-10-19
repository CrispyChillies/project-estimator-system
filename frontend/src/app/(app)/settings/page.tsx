"use client";

import Link from "next/link";
import { useTheme } from "next-themes";
import { useState } from "react";

import { PageHeader } from "@/components/common";
import { CurrencyToggle, FxNote } from "@/components/currency-toggle";
import { FxCard } from "@/components/settings/fx-card";
import { CategoriesCard, RatesCard } from "@/components/settings/rates-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useMe } from "@/hooks/auth";

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
  const admin = me?.role === "admin";
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
          <CardContent className="space-y-2 text-sm">
            <div>Effort: hours for one mid-level engineer of the task&apos;s role.</div>
            <div>Ranges: min–max hours; totals show P50 and P80.</div>
            <div className="flex items-center justify-between gap-2">
              <span>Money</span>
              <CurrencyToggle />
            </div>
            <FxNote />
          </CardContent>
        </Card>
      </div>
      {admin && <FxCard />}
      <div className="grid gap-4 xl:grid-cols-2">
        <RatesCard admin={admin} />
        <CategoriesCard />
      </div>
    </div>
  );
}
