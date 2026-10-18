"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common";
import { ProposalCard } from "@/components/estimate/agent-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { errorToast, useAssumptions, useInvalidateEstimate, useQuestions } from "@/hooks/queries";
import { api } from "@/lib/api";
import { pct } from "@/lib/format";
import type { Proposal, Question } from "@/lib/types";

function QuestionCard({ q, estimateId }: { q: Question; estimateId: string }) {
  const [answer, setAnswer] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const qc = useQueryClient();
  const invalidate = useInvalidateEstimate();
  const delta = (q.scenario_delta_min + q.scenario_delta_max) / 2;
  const submit = useMutation({
    mutationFn: (scenario: boolean) =>
      api<{ question: Question; proposal: Proposal | null }>(`/questions/${q.id}/answer`, {
        method: "POST",
        json: { answer: answer || (scenario ? "Yes" : "No"), scenario_applies: scenario },
      }),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["questions", estimateId] });
      invalidate(estimateId);
      setProposal(r.proposal);
      toast.success(r.proposal ? "Scenario tasks proposed — review below" : "Answer recorded");
    },
    onError: errorToast,
  });
  const dismiss = useMutation({
    mutationFn: () => api<Question>(`/questions/${q.id}/dismiss`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["questions", estimateId] }),
  });
  return (
    <Card size="sm" className={q.status !== "open" ? "opacity-70" : ""}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-sm leading-snug">{q.question}</CardTitle>
          <Badge variant="outline" className="shrink-0 border-amber-500/50 text-amber-700 dark:text-amber-400">
            could shift total ±{Math.round(delta)} h
          </Badge>
        </div>
        <CardDescription>
          {q.why_it_matters} · prior P(yes) {pct(q.prior_probability)} · impact {q.impact_score.toFixed(1)}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {q.scenario_tasks.length > 0 && (
          <div className="text-xs text-muted-foreground">
            If yes: {q.scenario_tasks.map((s) => `${String(s.title)} (${Number(s.min_hours).toFixed(0)}–${Number(s.max_hours).toFixed(0)} h)`).join(", ")}
          </div>
        )}
        {q.status === "open" ? (
          <div className="flex flex-wrap gap-2">
            <Input className="h-8 max-w-sm" placeholder="Client's answer…" value={answer} onChange={(e) => setAnswer(e.target.value)} />
            <Button size="sm" onClick={() => submit.mutate(true)} disabled={submit.isPending}>
              Yes — add scenario
            </Button>
            <Button size="sm" variant="outline" onClick={() => submit.mutate(false)} disabled={submit.isPending}>
              No
            </Button>
            <Button size="sm" variant="ghost" onClick={() => dismiss.mutate()}>
              Dismiss
            </Button>
          </div>
        ) : (
          <div className="text-xs">
            <Badge variant="secondary">{q.status}</Badge> {q.answer}
          </div>
        )}
        {proposal && <ProposalCard proposal={proposal} estimateId={estimateId} />}
      </CardContent>
    </Card>
  );
}

export function QuestionsTab({ estimateId }: { estimateId: string | null }) {
  const { data: questions, isLoading } = useQuestions(estimateId);
  const { data: assumptions } = useAssumptions(estimateId);
  if (!estimateId) return <EmptyState title="No estimate selected" />;
  if (isLoading) return <Skeleton className="h-64" />;
  const kinds: { kind: string; title: string }[] = [
    { kind: "assumption", title: "Assumptions & ambiguities" },
    { kind: "risk", title: "Risks" },
    { kind: "out_of_scope", title: "Out of scope" },
  ];
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <div className="space-y-3">
        <h2 className="text-sm font-semibold">Clarifying questions (ranked by impact = Δh · 4p(1−p))</h2>
        {questions?.length ? (
          questions.map((q) => <QuestionCard key={q.id} q={q} estimateId={estimateId} />)
        ) : (
          <EmptyState title="No open questions" description="The extraction found no effort-changing unknowns." />
        )}
      </div>
      <div className="space-y-3">
        {kinds.map(({ kind, title }) => {
          const items = assumptions?.filter((a) => a.kind === kind) ?? [];
          return (
            <Card key={kind} size="sm">
              <CardHeader>
                <CardTitle>{title}</CardTitle>
              </CardHeader>
              <CardContent>
                {items.length ? (
                  <ul className="list-disc space-y-1 pl-4 text-sm">
                    {items.map((a) => (
                      <li key={a.id}>{a.text}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-muted-foreground">None</p>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
