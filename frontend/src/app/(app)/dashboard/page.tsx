"use client";

import { useQuery } from "@tanstack/react-query";
import { FolderPlus } from "lucide-react";
import Link from "next/link";

import { PageHeader, StatusBadge } from "@/components/common";
import { GettingStarted, Onboarding } from "@/components/onboarding";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useMe } from "@/hooks/auth";
import { useProjects } from "@/hooks/queries";
import { api } from "@/lib/api";

interface Summary {
  estimate_vs_actual: { n: number };
  accuracy_over_time: { rows: { rolling_median: number }[]; enough: boolean };
  productivity: { n: number };
}

export default function Dashboard() {
  const { data: me } = useMe();
  const { data: projects } = useProjects();
  const { data: a } = useQuery({ queryKey: ["analytics"], queryFn: () => api<Summary>("/insights/analytics") });
  const recent = (projects ?? []).slice(0, 6);
  const lastMedian = a?.accuracy_over_time.enough ? a.accuracy_over_time.rows.at(-1)?.rolling_median : undefined;
  const stats = [
    ["Projects", projects?.length ?? "—"],
    ["Finalized quotes", a?.productivity.n ?? "—"],
    ["Delivered with actuals", a?.estimate_vs_actual.n ?? "—"],
    ["Recent quote error (median)", lastMedian !== undefined ? `${lastMedian}%` : "not enough data"],
  ] as const;
  return (
    <div className="space-y-4">
      <Onboarding />
      <PageHeader
        title={me ? `Hello, ${me.name.split(" ")[0]}` : "Dashboard"}
        description="Your estimates, what is waiting for you, and how accurate your quotes have been."
        actions={
          <Button render={<Link href="/projects?new=1" />} data-tour="new-project">
            <FolderPlus /> New project
          </Button>
        }
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map(([l, v]) => (
          <Card key={l}>
            <CardContent className="pt-4">
              <div className="text-xs text-muted-foreground">{l}</div>
              <div className="text-2xl font-semibold tabular-nums">{v}</div>
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <Card>
          <CardHeader>
            <CardTitle>Recent projects</CardTitle>
            <CardDescription>Newest first.</CardDescription>
          </CardHeader>
          <CardContent>
            {recent.length === 0 ? (
              <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                No projects yet. Start with <Link className="text-primary underline underline-offset-4" href="/projects?new=1">New project</Link> and
                paste the client brief.
              </div>
            ) : (
              <ul className="divide-y">
                {recent.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                    <Link href={`/projects/${p.id}`} className="font-medium hover:underline">
                      {p.name}
                    </Link>
                    <StatusBadge status={p.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <GettingStarted />
      </div>
    </div>
  );
}
