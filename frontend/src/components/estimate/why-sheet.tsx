"use client";

import { Badge } from "@/components/ui/badge";
import { HelpTip } from "@/components/onboarding";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useChunkLookup, useRules } from "@/hooks/queries";
import { factor, hours, num } from "@/lib/format";
import type { Provenance, TaskOut } from "@/lib/types";

function Section({ title, children, help }: { title: string; children: React.ReactNode; help?: { href: string; text: string } }) {
  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
        {help && <HelpTip label={title} href={help.href} text={help.text} />}
      </h3>
      {children}
    </section>
  );
}

export function WhySheet({ task, onClose }: { task: TaskOut | null; onClose: () => void }) {
  const prov = (task?.baseline?.provenance ?? null) as Provenance | null;
  const chunkIds = task?.source_chunk_ids ?? [];
  const { data: chunks } = useChunkLookup(chunkIds);
  const { data: rules } = useRules();
  const b = task?.baseline;
  const cal = prov?.calibration;
  return (
    <Sheet open={!!task} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Why this number?</SheetTitle>
          <SheetDescription>{task?.title}</SheetDescription>
        </SheetHeader>
        {task && (
          <div className="space-y-5 px-4 pb-6 text-sm">
            <div className="grid grid-cols-3 gap-2 rounded-lg border p-3">
              <div>
                <div className="text-xs text-muted-foreground">Raw LLM</div>
                <div className="font-medium tabular-nums">
                  {b ? `${b.raw_min}–${b.raw_max} h` : "—"}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">AI shown</div>
                <div className="font-medium tabular-nums">{b ? `${b.shown_min}–${b.shown_max} h` : "—"}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Current</div>
                <div className="font-medium tabular-nums">
                  {task.min_hours}–{task.max_hours} h
                </div>
              </div>
            </div>
            {!b && <p className="text-muted-foreground">Added by a {task.origin}; no AI provenance.</p>}
            {b && (
              <>
                <Section title="Source in the brief">
                  {chunks?.length ? (
                    chunks.map((c) => (
                      <blockquote key={c.id} className="border-l-2 pl-3 text-xs whitespace-pre-wrap text-muted-foreground">
                        {c.text.length > 600 ? `${c.text.slice(0, 600)}…` : c.text}
                      </blockquote>
                    ))
                  ) : (
                    <p className="text-xs text-muted-foreground">Hidden/standard task — not tied to a specific passage.</p>
                  )}
                  {task.rationale && <p className="text-xs">Rationale: {task.rationale}</p>}
                </Section>
                <Separator />
                <Section title={`Raw LLM samples (median of ${prov?.raw.samples.length ?? 0})`}>
                  <div className="flex flex-wrap gap-1.5">
                    {prov?.raw.samples.map(([lo, hi], i) => (
                      <Badge key={i} variant="secondary" className="tabular-nums">
                        {lo}–{hi} h
                      </Badge>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Model {b.model} · prompt {b.prompt_version}
                  </p>
                </Section>
                <Separator />
                <Section title="Calibration" help={{ href: "/help/estimates#calibration", text: "A multiplier learned from how your team changed AI drafts and from delivered actuals, per category." }}>
                  {cal ? (
                    <div className="space-y-1">
                      <div>
                        Factor <span className="font-semibold">{factor(cal.factor)}</span> · σ {num(cal.sigma, 2)} · scope{" "}
                        <code className="text-xs break-all">{cal.scope_used}</code>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Evidence: {cal.n_edit} PM edits (μ={num(cal.mu_edit, 3)}) and {cal.n_actual} delivered tasks
                        {cal.mu_actual !== null ? ` (μ=${num(cal.mu_actual, 3)})` : ""}. With few actuals the system follows PM
                        consensus; actuals dominate as they accumulate.
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      {prov?.learning ? "Cold start: no history yet (factor ×1.00)." : "Generated without learning (pure LLM baseline)."}
                    </p>
                  )}
                </Section>
                <Separator />
                <Section title={`Analogs (blend weight ${num(prov?.blend_weight ?? 0, 2)}, analog median ${hours(prov?.analog_mid ?? null, 1)})`}>
                  {prov?.analogs.length ? (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Past task</TableHead>
                          <TableHead className="text-right">Sim.</TableHead>
                          <TableHead className="text-right">Final</TableHead>
                          <TableHead className="text-right">Actual</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {prov.analogs.map((a) => (
                          <TableRow key={a.task_id}>
                            <TableCell className="max-w-56">
                              <div className="truncate">{a.title}</div>
                              <div className="truncate text-xs text-muted-foreground">{a.project_name}</div>
                            </TableCell>
                            <TableCell className="text-right tabular-nums">{num(a.similarity, 2)}</TableCell>
                            <TableCell className="text-right tabular-nums">{hours(a.final_mid, 1)}</TableCell>
                            <TableCell className="text-right tabular-nums">{hours(a.actual_mid, 1)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <p className="text-xs text-muted-foreground">No analogs above the similarity threshold.</p>
                  )}
                </Section>
                <Separator />
                <Section title="Similar past projects used as context" help={{ href: "/help/estimates#references", text: "Up to 3 of your most similar finalized projects, given to the AI as calibration evidence." }}>
                  {prov?.reference_projects?.length ? (
                    <ul className="space-y-1.5 text-xs">
                      {prov.reference_projects.map((r) => (
                        <li key={r.project_id} className="rounded-md border px-2 py-1.5">
                          <div className="flex justify-between gap-2">
                            <span className="font-medium">{r.name}</span>
                            <span className="tabular-nums text-muted-foreground">sim {num(r.similarity, 2)}</span>
                          </div>
                          <div className="text-muted-foreground">
                            {r.status} · {r.data_source}
                            {r.why?.length ? ` · ${r.why.slice(1).join(" · ")}` : ""}
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      None — no past project above the similarity threshold, or retrieval was off.
                    </p>
                  )}
                </Section>
                <Separator />
                <Section title="Rules applied">
                  {prov?.rules_applied.length ? (
                    <ul className="list-disc space-y-1 pl-4 text-xs">
                      {prov.rules_applied.map((id) => (
                        <li key={id}>{rules?.find((r) => r.id === id)?.text ?? id}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground">No active learned rules applied.</p>
                  )}
                </Section>
              </>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
