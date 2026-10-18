"use client";

import { Bar, BarChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { hours, money } from "@/lib/format";
import type { EstimateSummary, Role } from "@/lib/types";

const chartConfig = { count: { label: "Draws", color: "var(--chart-2)" } } satisfies ChartConfig;

export function Histogram({ summary, height = 140 }: { summary: EstimateSummary; height?: number }) {
  const sim = summary.simulation;
  const data = sim.histogram.map((b) => ({ x: Math.round((b.x0 + b.x1) / 2), count: b.count }));
  return (
    <ChartContainer config={chartConfig} className="w-full" style={{ height }}>
      <BarChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="x" tickLine={false} axisLine={false} fontSize={10} minTickGap={24} />
        <YAxis hide />
        <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => `${v} h`} />} />
        <Bar dataKey="count" fill="var(--color-count)" radius={2} />
        <ReferenceLine x={data.reduce((p, d) => (Math.abs(d.x - sim.p50) < Math.abs(p - sim.p50) ? d.x : p), 0)} stroke="var(--chart-1)" strokeDasharray="3 3" label={{ value: "P50", fontSize: 10, position: "top" }} />
        <ReferenceLine x={data.reduce((p, d) => (Math.abs(d.x - sim.p80) < Math.abs(p - sim.p80) ? d.x : p), 0)} stroke="var(--chart-4)" strokeDasharray="3 3" label={{ value: "P80", fontSize: 10, position: "top" }} />
      </BarChart>
    </ChartContainer>
  );
}

export function SummaryPanel({ summary, roles }: { summary?: EstimateSummary; roles: Role[] }) {
  if (!summary) return <Skeleton className="h-96 w-full" />;
  const sim = summary.simulation;
  const color = (name: string) => roles.find((r) => r.name === name)?.color ?? "var(--muted-foreground)";
  return (
    <div className="space-y-3">
      <Card size="sm">
        <CardHeader>
          <CardTitle>Total effort</CardTitle>
          <CardDescription>
            Monte Carlo, {sim.draws.toLocaleString()} draws · shared factor: {sim.shared}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <div className="text-xs text-muted-foreground">P50</div>
              <div className="text-2xl font-semibold tabular-nums">{hours(sim.p50)}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">P80</div>
              <div className="text-2xl font-semibold tabular-nums">{hours(sim.p80)}</div>
            </div>
          </div>
          <div className="text-xs text-muted-foreground">
            P10 {hours(sim.p10)} · P90 {hours(sim.p90)} · Σ min–max {hours(summary.total_min)}–{hours(summary.total_max)}
          </div>
          <Histogram summary={summary} />
          <div className="text-sm">
            Cost (mid): <span className="font-medium">{money(summary.total_cost_mid, summary.currency)}</span>
          </div>
        </CardContent>
      </Card>
      <Card size="sm">
        <CardHeader>
          <CardTitle>By role</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Role</TableHead>
                <TableHead className="text-right">Hours</TableHead>
                <TableHead className="text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.by_role.map((r) => (
                <TableRow key={r.name}>
                  <TableCell>
                    <span className="mr-1.5 inline-block size-2 rounded-full" style={{ background: color(r.name) }} />
                    {r.name}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{hours(r.mid)}</TableCell>
                  <TableCell className="text-right tabular-nums">{money(r.cost, summary.currency)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <Card size="sm">
        <CardHeader>
          <CardTitle>By module</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableBody>
              {summary.by_module.map((m) => (
                <TableRow key={m.name}>
                  <TableCell className="max-w-40 truncate">{m.name}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {hours(m.min)}–{hours(m.max)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
