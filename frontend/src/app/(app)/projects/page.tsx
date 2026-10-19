"use client";

import { createColumnHelper, tableFeatures, useTable } from "@tanstack/react-table";
import { ArrowUpDown, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState, ErrorState, PageHeader, StatusBadge } from "@/components/common";
import { NewProjectDialog } from "@/components/projects/new-project-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useProjects } from "@/hooks/queries";
import { date, hours } from "@/lib/format";
import type { ProjectListItem } from "@/lib/types";

type SortKey = "name" | "status" | "p50_hours" | "final_mid_hours" | "actual_hours" | "accuracy_pct" | "created_at";

const features = tableFeatures({});
const helper = createColumnHelper<typeof features, ProjectListItem>();
const columns = helper.columns([
  helper.accessor("name", {
    header: "Name",
    cell: (c) => (
      <div className="flex items-center gap-2">
        <Link href={`/projects/${c.row.original.id}`} className="font-medium hover:underline">
          {c.getValue()}
        </Link>
      </div>
    ),
  }),
  helper.accessor("client_name", { header: "Client", cell: (c) => c.getValue() || "—" }),
  helper.accessor("status", { header: "Status", cell: (c) => <StatusBadge status={c.getValue()} /> }),
  helper.accessor("p50_hours", { header: "P50", cell: (c) => hours(c.getValue()) }),
  helper.accessor("final_mid_hours", { header: "Final estimate", cell: (c) => hours(c.getValue()) }),
  helper.accessor("actual_hours", { header: "Actual", cell: (c) => hours(c.getValue()) }),
  helper.accessor("accuracy_pct", {
    header: "Accuracy",
    cell: (c) => {
      const v = c.getValue();
      if (v === null || v === undefined) return "—";
      const cls = v >= 85 ? "text-emerald-600" : v >= 70 ? "text-amber-600" : "text-rose-600";
      return <span className={cls}>{v.toFixed(0)}%</span>;
    },
  }),
  helper.accessor("created_at", { header: "Created", cell: (c) => date(c.getValue()) }),
]);

const SORTABLE: Record<string, SortKey> = {
  name: "name",
  status: "status",
  p50_hours: "p50_hours",
  final_mid_hours: "final_mid_hours",
  actual_hours: "actual_hours",
  accuracy_pct: "accuracy_pct",
  created_at: "created_at",
};

const STATUSES = ["all", "draft", "quoted", "won", "lost", "delivered"];

export default function ProjectsPage() {
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "created_at", desc: true });
  const { data, isLoading, error } = useProjects(status === "all" ? undefined : status);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = (data ?? []).filter(
      (p) => !q || p.name.toLowerCase().includes(q) || p.client_name.toLowerCase().includes(q),
    );
    return [...filtered].sort((a, b) => {
      const av = a[sort.key] ?? -Infinity;
      const bv = b[sort.key] ?? -Infinity;
      const r = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.desc ? -r : r;
    });
  }, [data, search, sort]);

  const table = useTable({ features, columns, data: rows });

  return (
    <div>
      <PageHeader
        title="Projects"
        description="Briefs, estimates and delivered history."
        actions={<NewProjectDialog autoOpen />}
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute top-2 left-2 size-4 text-muted-foreground" />
          <Input
            className="w-64 pl-8"
            placeholder="Search name or client…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          value={status}
          onValueChange={(v) => setStatus(v ?? "all")}
          items={STATUSES.map((s) => ({ value: s, label: s === "all" ? "All statuses" : s }))}
        >
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {s === "all" ? "All statuses" : s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-xs text-muted-foreground">{rows.length} projects</span>
      </div>
      {error ? (
        <ErrorState error={error} />
      ) : isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          title="No projects yet"
          description="Create a project, upload or paste the client brief, and generate a first estimate."
          action={<NewProjectDialog />}
        />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((g) => (
                <TableRow key={g.id}>
                  {g.headers.map((h) => {
                    const key = SORTABLE[h.column.id];
                    return (
                      <TableHead key={h.id}>
                        {key ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="-ml-2 h-7"
                            onClick={() => setSort((s) => ({ key, desc: s.key === key ? !s.desc : true }))}
                          >
                            <table.FlexRender header={h} />
                            <ArrowUpDown className="size-3 opacity-50" />
                          </Button>
                        ) : (
                          <table.FlexRender header={h} />
                        )}
                      </TableHead>
                    );
                  })}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getAllCells().map((cell) => (
                    <TableCell key={cell.id}>
                      <table.FlexRender cell={cell} />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
