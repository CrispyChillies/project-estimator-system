"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, RefreshCw } from "lucide-react";
import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { EmptyState, ModelStatusBanner, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  errorToast,
  useAccuracyOverTime,
  useCalibration,
  useCategories,
  useRules,
  useStructural,
  useTimeline,
} from "@/hooks/queries";
import { api } from "@/lib/api";
import { date, factor, pct } from "@/lib/format";
import type { Rule } from "@/lib/types";

const layerConfig = {
  edit: { label: "Edit layer (PM belief)", color: "var(--chart-1)" },
  actual: { label: "Actual layer (delivered)", color: "var(--chart-2)" },
} satisfies ChartConfig;

const LINE_COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];

function RulesCard() {
  const { data: rules } = useRules();
  const qc = useQueryClient();
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api<Rule>(`/rules/${id}/status`, { method: "POST", json: { status } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["rules"] }),
    onError: errorToast,
  });
  const propose = useMutation({
    mutationFn: () => api<Rule[]>("/rules/propose", { method: "POST" }),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["rules"] });
      toast.success(`${r.length} new proposal(s)`);
    },
    onError: errorToast,
  });
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Learned rules</CardTitle>
            <CardDescription>
              Proposed by the lessons chain; never auto-activated. Active rules are injected into prompts (max 10).
            </CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={() => propose.mutate()}>
            <RefreshCw /> Propose
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {!rules?.length && <p className="text-sm text-muted-foreground">No rules yet.</p>}
        {rules?.map((r) => (
          <div key={r.id} className="flex items-start gap-3 rounded-md border p-2.5">
            <div className="min-w-0 flex-1">
              <p className="text-sm">{r.text}</p>
              <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                <Badge variant="outline">{r.layer} layer</Badge>
                {typeof r.scope.category_key === "string" && <Badge variant="outline">{r.scope.category_key}</Badge>}
                <span>
                  evidence: {r.evidence_count} tasks · {r.evidence_event_ids.length} linked edit events
                </span>
              </div>
            </div>
            {r.status === "proposed" ? (
              <div className="flex shrink-0 gap-1">
                <Button size="xs" variant="outline" onClick={() => setStatus.mutate({ id: r.id, status: "disabled" })}>
                  Dismiss
                </Button>
                <Button size="xs" onClick={() => setStatus.mutate({ id: r.id, status: "active" })}>
                  <Check /> Approve
                </Button>
              </div>
            ) : (
              <div className="flex shrink-0 items-center gap-1.5 text-xs">
                {r.status}
                <Switch
                  size="sm"
                  checked={r.status === "active"}
                  onCheckedChange={(c) => setStatus.mutate({ id: r.id, status: c ? "active" : "disabled" })}
                  aria-label="Active"
                />
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function InsightsPage() {
  const { data: cal, isLoading } = useCalibration();
  const { data: timeline } = useTimeline();
  const { data: accuracy } = useAccuracyOverTime();
  const { data: structural } = useStructural();
  const { data: categories } = useCategories();
  const catName = (k: string) => categories?.find((c) => c.key === k)?.name ?? k;

  const factors = useMemo(() => {
    const rows: Record<string, { category: string; edit?: number; actual?: number; n_edit?: number; n_actual?: number }> = {};
    for (const r of cal ?? []) {
      if (r.scope_type !== "category") continue;
      rows[r.scope_key] ??= { category: r.scope_key };
      rows[r.scope_key][r.layer] = Number(r.factor.toFixed(3));
      rows[r.scope_key][r.layer === "edit" ? "n_edit" : "n_actual"] = r.n;
    }
    return Object.values(rows).sort((a, b) => (b.actual ?? b.edit ?? 1) - (a.actual ?? a.edit ?? 1));
  }, [cal]);

  const topCats = useMemo(
    () =>
      factors
        .slice()
        .sort((a, b) => Math.abs(Math.log(b.actual ?? b.edit ?? 1)) - Math.abs(Math.log(a.actual ?? a.edit ?? 1)))
        .slice(0, 5)
        .map((f) => f.category),
    [factors],
  );

  const timelineData = useMemo(
    () =>
      (timeline ?? [])
        .filter((p) => p.layer === "actual")
        .map((p, i) => ({ idx: i + 1, date: date(String(p.created_at)), ...Object.fromEntries(topCats.map((c) => [c, p[c]])) })),
    [timeline, topCats],
  );
  const editTimeline = useMemo(
    () =>
      (timeline ?? [])
        .filter((p) => p.layer === "edit")
        .map((p, i) => ({ idx: i + 1, date: date(String(p.created_at)), ...Object.fromEntries(topCats.map((c) => [c, p[c]])) })),
    [timeline, topCats],
  );
  const tlConfig: ChartConfig = Object.fromEntries(topCats.map((c, i) => [c, { label: catName(c), color: LINE_COLORS[i] }]));

  const accData = (accuracy ?? []).filter((a) => a.ape !== null).map((a, i) => ({ idx: i + 1, name: a.name, ape: Number(((a.ape ?? 0) * 100).toFixed(1)) }));
  const covered = (accuracy ?? []).filter((a) => a.within_p80 !== null);
  const coverage = covered.length ? covered.filter((a) => a.within_p80).length / covered.length : null;
  const anyDemo = (accuracy ?? []).some((a) => a.data_source !== "user");

  if (isLoading) return <Skeleton className="h-96" />;
  if (!cal?.length)
    return (
      <div>
        <PageHeader title="Insights" />
        <ModelStatusBanner />
        <EmptyState title="Nothing learned yet" description="Finalize an estimate or run `make seed` to load history." />
      </div>
    );

  return (
    <div className="space-y-4">
      <PageHeader
        title="What the system has learned"
        description="Calibration factors are exp(μ̃) of log(reference / raw LLM), with hierarchical shrinkage."
      />
      <ModelStatusBanner />
      {anyDemo && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-800 dark:text-amber-300">
          Includes demo/synthetic history. Synthetic results demonstrate the mechanism, not real-world accuracy.
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Calibration factor by category</CardTitle>
            <CardDescription>&gt;1 means the raw AI underestimates. Edit layer = PM consensus, actual layer = delivered hours.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={layerConfig} className="h-72 w-full">
              <BarChart data={factors.map((f) => ({ ...f, label: catName(f.category) }))} margin={{ bottom: 40 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="label" angle={-35} textAnchor="end" interval={0} fontSize={10} height={60} />
                <YAxis domain={[0.6, "auto"]} fontSize={10} />
                <ReferenceLine y={1} stroke="var(--muted-foreground)" strokeDasharray="3 3" />
                <ChartTooltip content={<ChartTooltipContent />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar dataKey="edit" fill="var(--color-edit)" radius={2} />
                <Bar dataKey="actual" fill="var(--color-actual)" radius={2} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>P80 coverage</CardTitle>
            <CardDescription>Delivered projects whose actual total was ≤ the quoted P80 (target 80%).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="text-4xl font-semibold tabular-nums">{pct(coverage)}</div>
            <Progress value={Math.round((coverage ?? 0) * 100)} />
            <p className="text-xs text-muted-foreground">
              n = {covered.length} projects
              {structural?.unplanned_share_mean !== null && structural?.unplanned_share_mean !== undefined &&
                ` · unplanned work ≈ ${pct(structural.unplanned_share_mean)} of delivered hours (reported separately)`}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Timeline of beliefs — actual layer</CardTitle>
            <CardDescription>Category factors after each delivery (top 5 by magnitude)</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={tlConfig} className="h-64 w-full">
              <LineChart data={timelineData}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="idx" fontSize={10} />
                <YAxis domain={["auto", "auto"]} fontSize={10} />
                <ReferenceLine y={1} stroke="var(--muted-foreground)" strokeDasharray="3 3" />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => String(p?.[0]?.payload?.date ?? "")} />} />
                <ChartLegend content={<ChartLegendContent />} />
                {topCats.map((c) => (
                  <Line key={c} dataKey={c} stroke={`var(--color-${c})`} dot={false} strokeWidth={2} connectNulls />
                ))}
              </LineChart>
            </ChartContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Timeline of beliefs — edit layer</CardTitle>
            <CardDescription>Category factors after each finalized estimate</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={tlConfig} className="h-64 w-full">
              <LineChart data={editTimeline}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="idx" fontSize={10} />
                <YAxis domain={["auto", "auto"]} fontSize={10} />
                <ReferenceLine y={1} stroke="var(--muted-foreground)" strokeDasharray="3 3" />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => String(p?.[0]?.payload?.date ?? "")} />} />
                {topCats.map((c) => (
                  <Line key={c} dataKey={c} stroke={`var(--color-${c})`} dot={false} strokeWidth={2} connectNulls />
                ))}
              </LineChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Accuracy over time</CardTitle>
            <CardDescription>Project-level absolute % error of the final estimate, by delivery order</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={{ ape: { label: "APE %", color: "var(--chart-3)" } }} className="h-56 w-full">
              <LineChart data={accData}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="idx" fontSize={10} />
                <YAxis fontSize={10} unit="%" />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => String(p?.[0]?.payload?.name ?? "")} />} />
                <Line dataKey="ape" stroke="var(--color-ape)" strokeWidth={2} />
              </LineChart>
            </ChartContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Calibration details</CardTitle>
            <CardDescription>Shrunk factor with approx. 95% interval and sample size</CardDescription>
          </CardHeader>
          <CardContent className="max-h-64 overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scope</TableHead>
                  <TableHead>Layer</TableHead>
                  <TableHead className="text-right">n</TableHead>
                  <TableHead className="text-right">Factor</TableHead>
                  <TableHead className="text-right">95% CI</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cal
                  .filter((r) => r.scope_type !== "category_author")
                  .map((r) => (
                    <TableRow key={`${r.layer}-${r.scope_type}-${r.scope_key}`}>
                      <TableCell>{r.scope_type === "category" ? catName(r.scope_key) : `${r.scope_type}`}</TableCell>
                      <TableCell>{r.layer}</TableCell>
                      <TableCell className="text-right tabular-nums">{r.n}</TableCell>
                      <TableCell className="text-right tabular-nums">{factor(r.factor)}</TableCell>
                      <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                        {r.factor_lo.toFixed(2)}–{r.factor_hi.toFixed(2)}
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Structural signals</CardTitle>
            <CardDescription>Tasks PMs add (AI missed) and remove (false positives)</CardDescription>
          </CardHeader>
          <CardContent className="max-h-80 overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Category</TableHead>
                  <TableHead className="text-right">Missing-task rate</TableHead>
                  <TableHead className="text-right">Removed rate</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {structural?.categories.map((c) => (
                  <TableRow key={c.category}>
                    <TableCell>{catName(c.category)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {pct(c.missing_task_rate)} <span className="text-xs text-muted-foreground">({c.added})</span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {pct(c.false_positive_rate)} <span className="text-xs text-muted-foreground">({c.removed})</span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {!!structural?.frequently_added.length && (
              <div className="mt-3 text-xs">
                <div className="mb-1 font-medium">Frequently added by PMs</div>
                {structural.frequently_added.map((f) => (
                  <div key={f.title}>
                    {f.title} <span className="text-muted-foreground">×{f.count}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <RulesCard />
      </div>
    </div>
  );
}
