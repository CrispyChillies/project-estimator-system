"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import Link from "next/link";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  ErrorBar,
  Line,
  LineChart,
  ReferenceLine,
  Scatter,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { CHART_GUIDES, type ChartGuideId } from "@/lib/chart-guides";

interface Block {
  n: number;
  enough: boolean;
}
interface Analytics {
  min_projects: number;
  includes_reference_library: boolean;
  estimate_vs_actual: Block & { rows: { name: string; p50: number; min: number; max: number; actual: number }[] };
  accuracy_over_time: Block & { window: number; rows: { name: string; ape: number; rolling_median: number }[] };
  bias_by_category: Block & { rows: { label: string; n: number; ratio: number; lo: number | null; hi: number | null; enough: boolean }[] };
  coverage: {
    task_in_range: number | null;
    task_n: number;
    range_target: number;
    project_below_p80: number | null;
    project_n: number;
    p80_target: number;
    enough: boolean;
  };
  unplanned: Block & { by_reason: { reason: string; hours: number; share: number | null }[]; by_project: { name: string; share: number }[] };
  planned_vs_actual: Block & {
    by_role: { label: string; planned: number; actual: number }[];
    by_category: { label: string; planned: number; actual: number }[];
  };
  productivity: Block & {
    per_estimate: { name: string; lead_time_hours: number | null; edits: number; changed_share: number | null }[];
    median_lead_time_hours: number | null;
    median_edits: number | null;
    median_changed_share: number | null;
    agent_edit_share: number | null;
    edits_by_actor: { manual: number; agent: number };
  };
  learning_impact: Block & { rows: { name: string; raw_ape: number | null; calibrated_ape: number | null; final_ape: number | null }[] };
}

const pct0 = (x: number | null | undefined) => (x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`);
const short = (s: string) => (s.length > 18 ? `${s.slice(0, 17)}…` : s);
const REASON: Record<string, string> = {
  missed_requirement: "Missed requirement",
  clarified_scope: "Clarified scope",
  change_request: "Change request",
  other: "Other",
  unspecified: "Not specified",
};

function HowToRead({ id }: { id: ChartGuideId }) {
  const g = CHART_GUIDES[id];
  return (
    <Sheet>
      <SheetTrigger render={<Button size="xs" variant="ghost" aria-label={`How to read this: ${g.title}`} />}>
        <BookOpen /> How to read this
      </SheetTrigger>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{g.title}</SheetTitle>
          <SheetDescription>{g.shows}</SheetDescription>
        </SheetHeader>
        <div className="space-y-3 px-4 pb-6 text-sm">
          {(
            [
              ["How it is computed", g.computed],
              ["How to read it", g.read],
              ["What to do next", g.next],
              ["Pitfalls", g.pitfalls],
            ] as const
          ).map(([h, t]) => (
            <section key={h}>
              <h3 className="text-xs font-semibold text-muted-foreground uppercase">{h}</h3>
              <p>{t}</p>
            </section>
          ))}
          <Link className="text-primary underline underline-offset-4" href={`/help/analytics#${id}`}>
            Open the full guide
          </Link>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ChartCard({ id, n, enough, need, children, className }: {
  id: ChartGuideId;
  n: number;
  enough: boolean;
  need: string;
  children: React.ReactNode;
  className?: string;
}) {
  const g = CHART_GUIDES[id];
  return (
    <Card className={className} data-testid={`chart-${id}`}>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">{g.title}</CardTitle>
            <CardDescription>{g.shows}</CardDescription>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Badge variant="outline">n = {n}</Badge>
            <HowToRead id={id} />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {enough ? (
          children
        ) : (
          <div className="flex h-48 flex-col items-center justify-center gap-1 rounded-md border border-dashed text-center text-sm text-muted-foreground" data-testid="not-enough">
            <span className="font-medium">Not enough data yet</span>
            <span className="max-w-xs text-xs">{need}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const evaCfg = {
  band: { label: "Quoted min–max", color: "var(--chart-3)" },
  p50: { label: "Quote (P50)", color: "var(--chart-1)" },
  actual: { label: "Actual", color: "var(--chart-2)" },
} satisfies ChartConfig;
const accCfg = { ape: { label: "Error %", color: "var(--chart-1)" }, rolling_median: { label: "Rolling median", color: "var(--chart-2)" } } satisfies ChartConfig;
const biasCfg = { ratio: { label: "Actual ÷ quote", color: "var(--chart-1)" } } satisfies ChartConfig;
const paCfg = { planned: { label: "Planned (midpoint)", color: "var(--chart-1)" }, actual: { label: "Actual", color: "var(--chart-2)" } } satisfies ChartConfig;
const unCfg = { share: { label: "Unplanned share %", color: "var(--chart-4)" } } satisfies ChartConfig;
const liCfg = {
  raw_ape: { label: "Raw AI draft", color: "var(--chart-4)" },
  calibrated_ape: { label: "Calibrated draft", color: "var(--chart-1)" },
  final_ape: { label: "Final quote", color: "var(--chart-2)" },
} satisfies ChartConfig;
const prodCfg = { edits: { label: "Edits", color: "var(--chart-1)" } } satisfies ChartConfig;

export function ProductivityAnalytics() {
  const { data, isLoading } = useQuery({ queryKey: ["analytics"], queryFn: () => api<Analytics>("/insights/analytics") });
  if (isLoading || !data) return <Skeleton className="h-96" />;
  const projNeed = `Needs at least ${data.min_projects} delivered projects with actual hours.`;
  const eva = data.estimate_vs_actual.rows.map((r) => ({ ...r, label: short(r.name), band: [r.min, r.max] }));
  return (
    <div className="space-y-4">
      {data.includes_reference_library && (
        <div className="rounded-md border px-3 py-2 text-xs text-muted-foreground">Includes reference library data.</div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard id="estimate-vs-actual" n={data.estimate_vs_actual.n} enough={data.estimate_vs_actual.enough} need={projNeed} className="lg:col-span-2">
          <ChartContainer config={evaCfg} className="h-72 w-full">
            <ComposedChart data={eva} margin={{ bottom: 40 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" angle={-35} textAnchor="end" interval={0} fontSize={10} height={60} />
              <YAxis fontSize={10} unit=" h" />
              <ChartTooltip content={<ChartTooltipContent />} />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar dataKey="band" fill="var(--color-band)" fillOpacity={0.35} radius={2} />
              <Scatter dataKey="p50" fill="var(--color-p50)" />
              <Scatter dataKey="actual" fill="var(--color-actual)" shape="diamond" />
            </ComposedChart>
          </ChartContainer>
        </ChartCard>

        <ChartCard id="accuracy-over-time" n={data.accuracy_over_time.n} enough={data.accuracy_over_time.enough} need={projNeed}>
          <ChartContainer config={accCfg} className="h-64 w-full">
            <LineChart data={data.accuracy_over_time.rows.map((r, i) => ({ ...r, idx: i + 1 }))}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="idx" fontSize={10} />
              <YAxis fontSize={10} unit="%" />
              <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => p?.[0]?.payload?.name ?? ""} />} />
              <ChartLegend content={<ChartLegendContent />} />
              <Line dataKey="ape" stroke="var(--color-ape)" dot strokeOpacity={0.4} />
              <Line dataKey="rolling_median" stroke="var(--color-rolling_median)" dot={false} strokeWidth={2} />
            </LineChart>
          </ChartContainer>
        </ChartCard>

        <ChartCard id="bias-by-category" n={data.bias_by_category.n} enough={data.bias_by_category.enough} need="Needs at least 5 delivered tasks with actuals in a category.">
          <ChartContainer config={biasCfg} className="h-64 w-full">
            <ComposedChart
              data={data.bias_by_category.rows.filter((r) => r.enough).map((r) => ({
                ...r,
                err: r.lo !== null && r.hi !== null ? [r.ratio - r.lo, r.hi - r.ratio] : [0, 0],
              }))}
              layout="vertical"
              margin={{ left: 20 }}
            >
              <CartesianGrid horizontal={false} />
              <XAxis type="number" fontSize={10} domain={[0, "auto"]} />
              <YAxis type="category" dataKey="label" fontSize={10} width={110} />
              <ReferenceLine x={1} stroke="var(--muted-foreground)" strokeDasharray="3 3" />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="ratio" fill="var(--color-ratio)" radius={2}>
                <ErrorBar dataKey="err" width={4} stroke="var(--foreground)" direction="x" />
              </Bar>
            </ComposedChart>
          </ChartContainer>
        </ChartCard>

        <ChartCard id="range-coverage" n={data.coverage.task_n} enough={data.coverage.enough} need="Needs delivered tasks with actuals in at least 3 projects.">
          <div className="grid grid-cols-2 gap-3 text-sm">
            {(
              [
                ["Tasks inside the quoted min–max", data.coverage.task_in_range, data.coverage.range_target, data.coverage.task_n],
                ["Projects at or below P80", data.coverage.project_below_p80, data.coverage.p80_target, data.coverage.project_n],
              ] as const
            ).map(([label, v, target, n]) => (
              <div key={label} className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className="text-2xl font-semibold tabular-nums">{pct0(v)}</div>
                <div className="mt-1 h-2 w-full rounded bg-muted">
                  <div className="h-2 rounded bg-primary" style={{ width: `${Math.min(100, (v ?? 0) * 100)}%` }} />
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  target {pct0(target)} · n = {n}
                </div>
              </div>
            ))}
          </div>
        </ChartCard>

        <ChartCard id="unplanned-work" n={data.unplanned.n} enough={data.unplanned.enough} need={projNeed}>
          <div className="space-y-3">
            <ul className="space-y-1 text-sm">
              {data.unplanned.by_reason.map((r) => (
                <li key={r.reason} className="flex justify-between">
                  <span>{REASON[r.reason] ?? r.reason}</span>
                  <span className="tabular-nums">
                    {r.hours} h · {pct0(r.share)} of all hours
                  </span>
                </li>
              ))}
            </ul>
            <ChartContainer config={unCfg} className="h-40 w-full">
              <BarChart data={data.unplanned.by_project.map((r, i) => ({ ...r, idx: i + 1 }))}>
                <XAxis dataKey="idx" fontSize={10} />
                <YAxis fontSize={10} unit="%" />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => p?.[0]?.payload?.name ?? ""} />} />
                <Bar dataKey="share" fill="var(--color-share)" radius={2} />
              </BarChart>
            </ChartContainer>
          </div>
        </ChartCard>

        <ChartCard id="planned-vs-actual" n={data.planned_vs_actual.n} enough={data.planned_vs_actual.enough} need="Needs at least 10 delivered tasks with actuals.">
          <div className="grid gap-2 md:grid-cols-2">
            {(["by_role", "by_category"] as const).map((k) => (
              <ChartContainer key={k} config={paCfg} className="h-56 w-full">
                <BarChart data={data.planned_vs_actual[k].slice(0, 8)} layout="vertical" margin={{ left: 10 }}>
                  <XAxis type="number" fontSize={9} />
                  <YAxis type="category" dataKey="label" fontSize={9} width={80} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="planned" fill="var(--color-planned)" radius={2} />
                  <Bar dataKey="actual" fill="var(--color-actual)" radius={2} />
                </BarChart>
              </ChartContainer>
            ))}
          </div>
        </ChartCard>

        <ChartCard id="estimating-productivity" n={data.productivity.n} enough={data.productivity.enough} need="Needs at least 3 finalized estimates.">
          <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            {(
              [
                ["Brief → final quote (median)", data.productivity.median_lead_time_hours === null ? "—" : `${data.productivity.median_lead_time_hours.toFixed(1)} h`],
                ["Edits per estimate (median)", data.productivity.median_edits ?? "—"],
                ["AI tasks changed (median)", pct0(data.productivity.median_changed_share)],
                ["Edits made by the agent", pct0(data.productivity.agent_edit_share)],
              ] as const
            ).map(([l, v]) => (
              <div key={l} className="rounded-md border p-2">
                <div className="text-xs text-muted-foreground">{l}</div>
                <div className="text-lg font-semibold tabular-nums">{v}</div>
              </div>
            ))}
          </div>
          <ChartContainer config={prodCfg} className="mt-2 h-32 w-full">
            <BarChart data={data.productivity.per_estimate.map((r, i) => ({ ...r, idx: i + 1 }))}>
              <XAxis dataKey="idx" fontSize={9} />
              <YAxis fontSize={9} />
              <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => p?.[0]?.payload?.name ?? ""} />} />
              <Bar dataKey="edits" fill="var(--color-edits)" radius={2} />
            </BarChart>
          </ChartContainer>
        </ChartCard>

        <ChartCard id="learning-impact" n={data.learning_impact.n} enough={data.learning_impact.enough} need={projNeed} className="lg:col-span-2">
          <ChartContainer config={liCfg} className="h-64 w-full">
            <LineChart data={data.learning_impact.rows.map((r, i) => ({ ...r, idx: i + 1 }))}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="idx" fontSize={10} />
              <YAxis fontSize={10} unit="%" />
              <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => p?.[0]?.payload?.name ?? ""} />} />
              <ChartLegend content={<ChartLegendContent />} />
              <Line dataKey="raw_ape" stroke="var(--color-raw_ape)" dot={false} />
              <Line dataKey="calibrated_ape" stroke="var(--color-calibrated_ape)" dot={false} />
              <Line dataKey="final_ape" stroke="var(--color-final_ape)" dot={false} strokeWidth={2} />
            </LineChart>
          </ChartContainer>
        </ChartCard>
      </div>
    </div>
  );
}
