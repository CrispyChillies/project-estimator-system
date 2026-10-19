"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle, HelpCircle, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useMe, useOnboarding } from "@/hooks/auth";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// ---------------- contextual help ----------------
export function HelpTip({ text, href, label }: { text: string; href: string; label: string }) {
  return (
    <Tooltip>
      <TooltipTrigger render={<Link href={href} aria-label={`Help: ${label}`} className="inline-flex text-muted-foreground hover:text-foreground" />}>
        <HelpCircle className="size-3.5" />
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{text}</TooltipContent>
    </Tooltip>
  );
}

// ---------------- getting started checklist ----------------
interface Progress {
  created_project: boolean;
  uploaded_brief: boolean;
  generated_estimate: boolean;
  used_agent: boolean;
  finalized: boolean;
  entered_actuals: boolean;
  viewed_insights: boolean;
}

const STEPS: { key: keyof Progress; label: string; hint: string; href: string }[] = [
  { key: "created_project", label: "Create a project", hint: "One project per client opportunity.", href: "/projects" },
  { key: "uploaded_brief", label: "Upload or paste the client brief", hint: "PDF, DOCX, Markdown or text.", href: "/projects" },
  { key: "generated_estimate", label: "Generate an estimate", hint: "Ranges per task with P50/P80 totals.", href: "/projects" },
  { key: "used_agent", label: "Edit the estimate with the chat agent", hint: "Open it with Ctrl/⌘+J on the Estimate tab.", href: "/projects" },
  { key: "finalized", label: "Finalize the quote", hint: "Your edits start teaching the calibration.", href: "/projects" },
  { key: "entered_actuals", label: "Enter actual hours after delivery", hint: "Actuals are the strongest learning signal.", href: "/projects" },
  { key: "viewed_insights", label: "Read Insights", hint: "Accuracy, bias and where the hours go.", href: "/insights" },
];

export function useProgress() {
  return useQuery({ queryKey: ["me-progress"], queryFn: () => api<Progress>("/me/progress") });
}

export function GettingStarted() {
  const { data } = useProgress();
  const { state, update } = useOnboarding();
  if (!data || state.checklist_dismissed) return null;
  const done = STEPS.filter((s) => data[s.key]).length;
  return (
    <Card data-tour="checklist">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle>Getting started</CardTitle>
            <CardDescription>
              {done} of {STEPS.length} done — items tick themselves off as you use the product.
            </CardDescription>
          </div>
          <Button size="icon-xs" variant="ghost" aria-label="Hide checklist" onClick={() => update({ checklist_dismissed: true })}>
            <X />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <ol className="space-y-1.5">
          {STEPS.map((s) => (
            <li key={s.key} data-tour={`step-${s.key}`} className="flex items-start gap-2 text-sm">
              {data[s.key] ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-label="done" />
              ) : (
                <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="not done" />
              )}
              <div>
                <Link href={s.href} className={cn("font-medium hover:underline", data[s.key] && "text-muted-foreground line-through")}>
                  {s.label}
                </Link>
                <div className="text-xs text-muted-foreground">{s.hint}</div>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

// ---------------- welcome + product tour ----------------
const TOUR: { anchor: string; title: string; body: string }[] = [
  { anchor: "nav-projects", title: "1. Create a project", body: "Each client opportunity is a project. Create one, then upload or paste the brief (PDF, DOCX, Markdown or text)." },
  { anchor: "step-generated_estimate", title: "2. Generate an estimate", body: "The brief is turned into groups and tasks with an hour range each, plus P50 and P80 totals from a simulation." },
  { anchor: "step-generated_estimate", title: "3. Read the ranges", body: "Every task has a “Why this number?” panel: the raw AI hours, the calibration applied from your history, similar past projects and the source passage in the brief." },
  { anchor: "step-used_agent", title: "4. Edit with the chat agent", body: "On the Estimate tab press Ctrl/⌘+J. Ask “fit this to 400 hours” or “reduce QA by 20%”: the agent edits the table with visible tool calls, and every change can be undone." },
  { anchor: "step-finalized", title: "5. Finalize", body: "Finalizing makes the quote read-only. The difference between the AI draft and your final numbers teaches the calibration." },
  { anchor: "step-entered_actuals", title: "6. Enter actuals", body: "After delivery, enter the real hours (or import a CSV) and any unplanned work. Actuals are what makes future estimates more accurate." },
  { anchor: "nav-insights", title: "7. Read Insights", body: "See accuracy over time, bias by category, range coverage, unplanned work and estimating productivity. Each chart explains how to read it." },
  { anchor: "account-menu", title: "Help is always here", body: "Guides, the glossary and “Take the tour again” live in this menu." },
];

function useAnchorRect(anchor: string | null) {
  const [rect, setRect] = useState<DOMRect | null>(null);
  useLayoutEffect(() => {
    if (!anchor) return;
    const measure = () => {
      const el = document.querySelector(`[data-tour="${anchor}"]`);
      setRect(el ? el.getBoundingClientRect() : null);
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    const t = setInterval(measure, 500);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
      clearInterval(t);
    };
  }, [anchor]);
  return rect;
}

export function Onboarding() {
  const { data: me } = useMe();
  const { state, update } = useOnboarding();
  const [step, setStep] = useState<number | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const resumed = useRef(false);
  const welcome = !!me && !state.welcome_seen;
  const touring = step !== null;
  const current = touring ? TOUR[step] : null;
  const rect = useAnchorRect(current?.anchor ?? null);

  useEffect(() => {
    // Resume an unfinished tour (e.g. after a reload or after “Take the tour again”).
    if (resumed.current || !me) return;
    resumed.current = true;
    if (state.welcome_seen && !state.tour_done && typeof state.tour_step === "number" && state.tour_step < TOUR.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resume persisted progress once
      setStep(state.tour_step as number);
    }
  }, [me, state.welcome_seen, state.tour_done, state.tour_step]);

  const go = useCallback(
    (n: number | null) => {
      if (n === null || n >= TOUR.length) {
        setStep(null);
        update({ tour_done: true, tour_step: TOUR.length });
        return;
      }
      setStep(Math.max(0, n));
      update({ tour_step: Math.max(0, n) });
    },
    [update],
  );

  useEffect(() => {
    if (!touring) return;
    boxRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") go(null);
      if (e.key === "ArrowRight") go((step ?? 0) + 1);
      if (e.key === "ArrowLeft") go((step ?? 0) - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [touring, step, go]);

  const pos = rect
    ? {
        top: Math.min(window.innerHeight - 220, rect.bottom + 8),
        left: Math.max(8, Math.min(window.innerWidth - 336, rect.left)),
      }
    : { top: 80, left: Math.max(8, window.innerWidth / 2 - 160) };

  return (
    <>
      <Dialog open={welcome} onOpenChange={(o) => !o && update({ welcome_seen: true, tour_done: true })}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Welcome to Calibr{me ? `, ${me.name.split(" ")[0]}` : ""}</DialogTitle>
            <DialogDescription>
              Calibr turns a client brief into an hour estimate you can review, edit with a chat agent and quote. Every quote you
              finalize and every project you deliver makes the next estimate more accurate. Your workspace is private and starts
              empty.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => update({ welcome_seen: true, tour_done: true })}>
              Skip for now
            </Button>
            <Button
              onClick={() => {
                update({ welcome_seen: true, tour_done: false, tour_step: 0 });
                setStep(0);
              }}
            >
              Take the 1-minute tour
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {touring && current && (
        <>
          {rect && (
            <div
              aria-hidden
              className="pointer-events-none fixed z-40 rounded-md ring-2 ring-primary ring-offset-2 ring-offset-background transition-all"
              style={{ top: rect.top - 2, left: rect.left - 2, width: rect.width + 4, height: rect.height + 4 }}
            />
          )}
          <div
            ref={boxRef}
            role="dialog"
            aria-modal="false"
            aria-labelledby="tour-title"
            tabIndex={-1}
            data-testid="tour"
            className="fixed z-50 w-80 rounded-lg border bg-popover p-3 text-sm shadow-lg outline-none"
            style={pos}
          >
            <div id="tour-title" className="font-medium">
              {current.title}
            </div>
            <p className="mt-1 text-muted-foreground">{current.body}</p>
            <div className="mt-3 flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {(step ?? 0) + 1} / {TOUR.length}
              </span>
              <div className="flex gap-1">
                <Button size="xs" variant="ghost" onClick={() => go(null)}>
                  Skip tour
                </Button>
                {(step ?? 0) > 0 && (
                  <Button size="xs" variant="outline" onClick={() => go((step ?? 0) - 1)}>
                    Back
                  </Button>
                )}
                <Button size="xs" onClick={() => go((step ?? 0) + 1)}>
                  {(step ?? 0) + 1 === TOUR.length ? "Done" : "Next"}
                </Button>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}
