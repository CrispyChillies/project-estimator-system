"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";

import { EmptyState, JobProgress, PageHeader } from "@/components/common";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { errorToast, useBacktestRun, useBacktestRuns } from "@/hooks/queries";
import { api } from "@/lib/api";
import { dateTime, hours, num, pct } from "@/lib/format";
import type { BacktestProject, BacktestSummary, Job, Metrics } from "@/lib/types";
import { cn } from "@/lib/utils";

const ESTIMATORS: { key: string; label: string; color: string }[] = [
  { key: "E0_median", label: "E0 category median", color: "var(--chart-5)" },
  { key: "E1_raw_llm", label: "E1 raw LLM", color: "var(--chart-4)" },
  { key: "E2_analogs", label: "E2 + analogs", color: "var(--chart-3)" },
  { key: "E3_calibrated_edit", label: "E3 + edit calibration", color: "var(--chart-2)" },
  { key: "E4_calibrated_full", label: "E4 full system", color: "var(--chart-1)" },
  { key: "A1_edit_only", label: "A1 ablation: edit calibration only (no analogs)", color: "var(--chart-2)" },
  { key: "A2_full_no_analogs", label: "A2 ablation: full system without analogs", color: "var(--chart-3)" },
];

type MetricKey = "MAPE" | "MdAPE" | "PRED25" | "bias" | "coverage_p80" | "interval_width";
const METRICS: { key: MetricKey; label: string; better: "low" | "high" | "zero" | "p80"; fmt: (v?: number) => string; ci?: boolean }[] = [
  { key: "MAPE", label: "MAPE", better: "low", fmt: (v) => (v === undefined ? "—" : `${v.toFixed(1)}%`), ci: true },
  { key: "MdAPE", label: "MdAPE", better: "low", fmt: (v) => (v === undefined ? "—" : `${v.toFixed(1)}%`), ci: true },
  { key: "PRED25", label: "PRED(25)", better: "high", fmt: (v) => pct(v), ci: true },
  { key: "bias", label: "Bias (mean log)", better: "zero", fmt: (v) => num(v, 3) },
  { key: "coverage_p80", label: "P80 coverage", better: "p80", fmt: (v) => pct(v), ci: true },
  { key: "interval_width", label: "Norm. width", better: "low", fmt: (v) => num(v, 2) },
];

function best(values: (number | undefined)[], better: string): number {
  const score = (v?: number) =>
    v === undefined ? Infinity : better === "low" ? v : better === "high" ? -v : better === "zero" ? Math.abs(v) : Math.abs(v - 0.8);
  let bi = -1;
  let bs = Infinity;
  values.forEach((v, i) => {
    const s = score(v);
    if (s < bs) {
      bs = s;
      bi = i;
    }
  });
  return bi;
}

function MetricsTable({ summary, level }: { summary: BacktestSummary; level: "task" | "project" }) {
  const rows = ESTIMATORS.map((e) => ({ ...e, r: summary.estimators[e.key] }));
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Estimator</TableHead>
          <TableHead className="text-right">n</TableHead>
          {METRICS.map((m) => (
            <TableHead key={m.key} className="text-right">
              {m.label}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, i) => (
          <TableRow key={row.key}>
            <TableCell className="font-medium">{row.label}</TableCell>
            <TableCell className="text-right tabular-nums">{row.r?.[level].n ?? 0}</TableCell>
            {METRICS.map((m) => {
              const vals = rows.map((x) => (x.r?.[level] as Metrics | undefined)?.[m.key]);
              const ci = row.r?.[`${level}_ci`]?.[m.key];
              const isBest = best(vals, m.better) === i;
              return (
                <TableCell key={m.key} className={cn("text-right tabular-nums", isBest && "font-semibold text-emerald-600")}>
                  {m.fmt(vals[i])}
                  {m.ci && ci && (
                    <div className="text-[10px] font-normal text-muted-foreground">
                      [{m.key === "PRED25" || m.key === "coverage_p80" ? `${pct(ci[0])}, ${pct(ci[1])}` : `${ci[0].toFixed(1)}, ${ci[1].toFixed(1)}`}]
                    </div>
                  )}
                </TableCell>
              );
            })}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

const chartConfig: ChartConfig = Object.fromEntries(ESTIMATORS.map((e) => [e.key, { label: e.label, color: e.color }]));

export default function BacktestPage() {
  const { data: runs, isLoading } = useBacktestRuns();
  const [runId, setRunId] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [protocol, setProtocol] = useState("loo");
  const [level, setLevel] = useState<"task" | "project">("project");
  const qc = useQueryClient();
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- default to latest run
    if (!runId && runs?.length) setRunId(runs[0].id);
  }, [runs, runId]);
  const { data: detail } = useBacktestRun(runId);
  const start = useMutation({
    mutationFn: () => api<Job>("/backtest", { method: "POST", json: { protocol } }),
    onSuccess: (j) => setJobId(j.id),
    onError: errorToast,
  });
  const onDone = (j: Job) => {
    setJobId(null);
    void qc.invalidateQueries({ queryKey: ["backtest-runs"] });
    if (j.result_ref) setRunId(j.result_ref);
  };
  const summary = detail?.run.summary as BacktestSummary | undefined;
  const projects = (detail?.projects ?? []) as unknown as BacktestProject[];

  const coverageData = ESTIMATORS.map((e) => ({
    name: e.label.split(" ")[0],
    key: e.key,
    coverage: Number((((summary?.estimators[e.key]?.[level].coverage_p80 ?? 0) as number) * 100).toFixed(1)),
  }));

  return (
    <div className="space-y-4">
      <PageHeader
        title="Backtest"
        description="Leave-one-project-out (or chronological) evaluation using cached raw LLM estimates — no LLM calls, no leakage."
        actions={
          <>
            <Select value={protocol} onValueChange={(v) => setProtocol(String(v))} items={[{ value: "loo", label: "Leave-one-out" }, { value: "chronological", label: "Chronological" }]}>
              <SelectTrigger size="sm" className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="loo">Leave-one-out</SelectItem>
                <SelectItem value="chronological">Chronological</SelectItem>
              </SelectContent>
            </Select>
            <Button size="sm" onClick={() => start.mutate()} disabled={!!jobId}>
              <Play /> Re-run backtest
            </Button>
          </>
        }
      />
      {jobId && <JobProgress jobId={jobId} onDone={onDone} />}
      {isLoading ? (
        <Skeleton className="h-64" />
      ) : !runs?.length ? (
        <EmptyState title="No backtest runs yet" description="A backtest re-estimates your delivered projects with history from the others and compares against actual hours. Deliver at least a few projects with actuals, then click “Re-run backtest”." />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={runId}
              onValueChange={(v) => v && setRunId(v)}
              items={runs.map((r) => ({ value: r.id, label: `${dateTime(r.created_at)} · ${String(r.config.protocol)}` }))}
            >
              <SelectTrigger size="sm" className="w-72">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {runs.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {dateTime(r.created_at)} · {String(r.config.protocol)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <ToggleGroup value={[level]} onValueChange={(v) => v.length && setLevel(v[0] as "task" | "project")} variant="outline" size="sm">
              <ToggleGroupItem value="project">Project totals</ToggleGroupItem>
              <ToggleGroupItem value="task">Tasks</ToggleGroupItem>
            </ToggleGroup>
          </div>
          {summary?.small_sample && (
            <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm text-amber-800 dark:text-amber-300">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              Small sample: {summary.n_projects} held-out projects. Brackets show 95% bootstrap CIs over projects — overlapping
              intervals mean differences may not be significant.
            </div>
          )}
          {summary && (
            <Card>
              <CardHeader>
                <CardTitle>Estimators × metrics ({level} level)</CardTitle>
                <CardDescription>Best value per metric highlighted. P80 coverage is best when closest to 80%.</CardDescription>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <MetricsTable summary={summary} level={level} />
              </CardContent>
            </Card>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Learning curve</CardTitle>
                <CardDescription>Task MdAPE vs. number of training projects (avg. over random orderings)</CardDescription>
              </CardHeader>
              <CardContent>
                <ChartContainer config={chartConfig} className="h-64 w-full">
                  <LineChart data={summary?.learning_curve ?? []}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="n_train" fontSize={10} />
                    <YAxis fontSize={10} unit="%" domain={["auto", "auto"]} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <ChartLegend content={<ChartLegendContent />} />
                    {["E1_raw_llm", "E3_calibrated_edit", "E4_calibrated_full"].map((k) => (
                      <Line key={k} dataKey={k} stroke={`var(--color-${k})`} dot={false} strokeWidth={2} />
                    ))}
                  </LineChart>
                </ChartContainer>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>P80 coverage</CardTitle>
                <CardDescription>Share of actuals at or below the predicted P80 (target line 80%)</CardDescription>
              </CardHeader>
              <CardContent>
                <ChartContainer config={{ coverage: { label: "Coverage %", color: "var(--chart-2)" } }} className="h-64 w-full">
                  <BarChart data={coverageData}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="name" fontSize={10} />
                    <YAxis domain={[0, 100]} fontSize={10} unit="%" />
                    <ReferenceLine y={80} stroke="var(--destructive)" strokeDasharray="4 4" />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="coverage" fill="var(--color-coverage)" radius={2} />
                  </BarChart>
                </ChartContainer>
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Per-project drill-down</CardTitle>
              <CardDescription>Project-total P50 per estimator vs. actual planned hours</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Project</TableHead>
                    <TableHead className="text-right">Train n</TableHead>
                    <TableHead className="text-right">Actual</TableHead>
                    {ESTIMATORS.map((e) => (
                      <TableHead key={e.key} className="text-right">
                        {e.label.split(" ")[0]}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {projects.map((p) => (
                    <TableRow key={p.project_id}>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          {p.name}
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{p.n_train}</TableCell>
                      <TableCell className="text-right tabular-nums">{hours(p.actual)}</TableCell>
                      {ESTIMATORS.map((e) => {
                        const r = p.estimators[e.key];
                        return (
                          <TableCell key={e.key} className="text-right tabular-nums">
                            {r ? (
                              <>
                                {hours(r.p50)}
                                <div className={cn("text-[10px]", r.ape <= 0.1 ? "text-emerald-600" : r.ape <= 0.25 ? "text-amber-600" : "text-rose-600")}>
                                  {pct(r.ape)} {r.covered_p80 ? "✓P80" : ""}
                                </div>
                              </>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
