import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, Bot, ChartColumn, FileText, FlaskConical, ListChecks, Scale, Search, Upload } from "lucide-react";

import { Wordmark } from "@/components/brand";
import { PublicHeader } from "@/components/public-header";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: { absolute: "Calibr — Project Calibrate UI · calibrated software estimates" },
  alternates: { canonical: "/" },
};

const FOOTNOTE = "Screenshots show fictional sample data.";

/** A real product screenshot, light + dark variants (the inactive one is hidden and, being lazy, not downloaded). */
function Shot({ name, alt, priority = false }: { name: string; alt: string; priority?: boolean }) {
  const src = (theme: string) => ({
    src: `/landing/${name}-${theme}-sm.webp`,
    srcSet: `/landing/${name}-${theme}-sm.webp 1280w, /landing/${name}-${theme}.webp 2880w`,
  });
  const common = { width: 1440, height: 900, sizes: "(min-width: 1152px) 1088px, 100vw", decoding: "async" as const };
  return (
    <figure className="overflow-hidden rounded-xl border bg-muted/30 shadow-sm">
      <div className="flex items-center gap-1.5 border-b bg-muted/60 px-3 py-2" aria-hidden>
        <span className="size-2.5 rounded-full bg-foreground/15" />
        <span className="size-2.5 rounded-full bg-foreground/15" />
        <span className="size-2.5 rounded-full bg-foreground/15" />
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element -- pre-optimised static webp with srcset */}
      <img alt={alt} {...common} {...src("light")} className="block h-auto w-full dark:hidden" loading={priority ? "eager" : "lazy"} fetchPriority={priority ? "high" : "auto"} />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img alt={alt} {...common} {...src("dark")} className="hidden h-auto w-full dark:block" loading="lazy" />
    </figure>
  );
}

const STEPS = [
  { icon: Upload, title: "Add the brief", text: "Create a project and upload or paste the client brief (PDF, DOCX, Markdown or text)." },
  { icon: FileText, title: "Generate a draft", text: "Calibr breaks the brief into tasks with min–max hours, a confidence level and the passage each task came from." },
  { icon: Bot, title: "Review with the agent", text: "Edit the table directly or ask the chat agent. Every change is listed, can be undone, and big swings ask first." },
  { icon: Scale, title: "Close the loop", text: "Finalize the quote, then enter the hours actually spent. Your edits and actuals calibrate the next estimate." },
];

const FEATURES = [
  {
    id: "workspace",
    icon: ListChecks,
    title: "An estimate you can review line by line",
    text: "Tasks grouped by module, ranges instead of single numbers, and totals from a Monte Carlo simulation (P50/P80) with cost by role from configurable rates and currency.",
    shot: "estimate",
    alt: "Estimate workspace: grouped tasks with category, role and hour ranges, next to the total-effort distribution and cost by role.",
  },
  {
    id: "agent",
    icon: Bot,
    title: "A chat agent that edits the table with you",
    text: "Ask it to reduce QA by 20%, add a task or explain a number. Each tool call is shown with its arguments, timing and result, with Undo and “Show in table”.",
    shot: "agent",
    alt: "Chat agent panel showing the tool calls it made (list tasks, bulk adjust, create task), each with Undo, next to the updated estimate.",
  },
  {
    id: "why",
    icon: Search,
    title: "“Why this number?” for every task",
    text: "See the passage of the brief behind a task, the raw model samples, the calibration factor applied and the past tasks used as analogs — including how much evidence there is.",
    shot: "why",
    alt: "The “Why this number?” sheet: source passage from the brief, raw model samples, calibration factor and evidence, and analog tasks.",
  },
  {
    id: "references",
    icon: BookOpen,
    title: "Grounded in your own delivered projects",
    text: "Similar past projects are retrieved from your history with their quoted range, actual hours and what PMs changed. When nothing is similar enough, it says so instead of guessing.",
    shot: "agent-refs",
    alt: "Similar past projects listed by the agent with similarity, quoted range, actual hours and the edits PMs made.",
  },
  {
    id: "insights",
    icon: ChartColumn,
    title: "Insights that show their sample size",
    text: "Eight charts: estimate vs actual, accuracy over time, bias by category, range coverage, unplanned work, planned vs actual by role, estimating productivity and learning impact. Every chart shows n and explains how to read it; small samples are flagged.",
    shot: "insights-charts",
    alt: "Insights page with estimate-vs-actual, accuracy-over-time and bias-by-category charts, each with its sample size.",
  },
  {
    id: "backtest",
    icon: FlaskConical,
    title: "Measure it before you trust it",
    text: "Backtests replay held-out delivered projects to compare the raw model, analogs, calibration and the full system — with confidence intervals and a warning when the sample is small.",
    shot: "backtest",
    alt: "Backtest results table comparing estimators by error metrics with confidence intervals and a small-sample warning.",
  },
];

const FAQ = [
  {
    q: "Which AI model does it use?",
    a: "One model chosen by the workspace administrator. Users cannot switch models, and each user has a daily AI spending limit.",
  },
  {
    q: "Does it work without past projects?",
    a: "Yes. The first estimates come from the brief alone, and calibration starts neutral. It improves as you finalize quotes and enter actual hours; until then, charts and the “Why” sheet show how little evidence there is.",
  },
  {
    q: "Who can see my projects?",
    a: "Projects are private to their owner unless shared with specific people or the whole workspace. Administrators can see everything.",
  },
  {
    q: "Can I export the estimate?",
    a: "Yes — export to CSV or Excel from the estimate tab.",
  },
  {
    q: "Is the agent allowed to change anything without asking?",
    a: "Small edits apply immediately and can be undone. Deletions and large changes ask for confirmation first, and nothing touches a finalized estimate.",
  },
];

export default function Landing() {
  return (
    <>
      <PublicHeader />
      <main id="main">
        <section className="mx-auto max-w-6xl px-4 pt-16 pb-12 text-center md:pt-24">
          <h1 className="mx-auto max-w-3xl text-4xl font-semibold tracking-tight text-balance md:text-5xl">
            Software estimates you can explain — that learn from what projects really took.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-pretty text-muted-foreground">
            Calibr turns a client brief into a task-level estimate with ranges, shows where every number comes from, lets a
            chat agent edit it with you, and calibrates against the hours your team actually spent.
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <Button size="lg" render={<Link href="/signup" />}>
              Get started <ArrowRight />
            </Button>
            <Button size="lg" variant="outline" render={<Link href="/help/getting-started" />}>
              Read the guide
            </Button>
          </div>
          <div className="mt-12 text-left">
            <Shot name="agent" alt="Calibr estimate workspace with the chat agent panel open, showing the edits it made." priority />
            <p className="mt-2 text-center text-xs text-muted-foreground">{FOOTNOTE}</p>
          </div>
        </section>

        <section id="how-it-works" className="scroll-mt-16 border-y bg-muted/30">
          <div className="mx-auto max-w-6xl px-4 py-16">
            <h2 className="text-center text-2xl font-semibold tracking-tight md:text-3xl">How it works</h2>
            <ol className="mt-10 grid gap-6 md:grid-cols-4">
              {STEPS.map((s, i) => (
                <li key={s.title} className="rounded-xl border bg-background p-5">
                  <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                    <s.icon className="size-4" aria-hidden /> Step {i + 1}
                  </div>
                  <h3 className="mt-2 font-semibold">{s.title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{s.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="features" className="mx-auto max-w-6xl scroll-mt-16 space-y-20 px-4 py-20">
          {FEATURES.map((f, i) => (
            <article key={f.id} className="grid items-center gap-8 md:grid-cols-5">
              <div className={i % 2 ? "md:order-2 md:col-span-2" : "md:col-span-2"}>
                <f.icon className="size-5 text-muted-foreground" aria-hidden />
                <h2 className="mt-2 text-2xl font-semibold tracking-tight">{f.title}</h2>
                <p className="mt-3 text-muted-foreground">{f.text}</p>
              </div>
              <div className={i % 2 ? "md:order-1 md:col-span-3" : "md:col-span-3"}>
                <Shot name={f.shot} alt={f.alt} />
              </div>
            </article>
          ))}
          <p className="text-center text-xs text-muted-foreground">{FOOTNOTE}</p>
        </section>

        <section id="how-it-learns" className="scroll-mt-16 border-y bg-muted/30">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 md:grid-cols-2">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">How it learns</h2>
              <p className="mt-3 text-muted-foreground">
                Nothing is retrained. Calibr keeps simple, inspectable statistics about your own work and applies them
                with caution.
              </p>
            </div>
            <ul className="space-y-4 text-sm">
              <li>
                <span className="font-medium">Your edits.</span>{" "}
                <span className="text-muted-foreground">When PMs consistently raise or lower a category, that becomes a calibration factor for it.</span>
              </li>
              <li>
                <span className="font-medium">Actual hours.</span>{" "}
                <span className="text-muted-foreground">Delivered projects outweigh edits as they accumulate; with little data, factors stay close to neutral.</span>
              </li>
              <li>
                <span className="font-medium">Analogs.</span>{" "}
                <span className="text-muted-foreground">Similar past tasks are blended in only when they are similar enough, and you can see which ones.</span>
              </li>
              <li>
                <span className="font-medium">Lessons you approve.</span>{" "}
                <span className="text-muted-foreground">Recurring patterns (such as an often-missed task) are proposed as rules; they apply only after you accept them.</span>
              </li>
            </ul>
          </div>
        </section>

        <section id="faq" className="mx-auto max-w-3xl scroll-mt-16 px-4 py-16">
          <h2 className="text-center text-2xl font-semibold tracking-tight md:text-3xl">Questions</h2>
          <div className="mt-8 divide-y rounded-xl border">
            {FAQ.map((f) => (
              <details key={f.q} className="group px-5 py-4">
                <summary className="cursor-pointer list-none font-medium marker:hidden">
                  <span className="flex items-center justify-between gap-4">
                    {f.q}
                    <span aria-hidden className="text-muted-foreground transition-transform group-open:rotate-45">+</span>
                  </span>
                </summary>
                <p className="mt-2 text-sm text-muted-foreground">{f.a}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="border-t">
          <div className="mx-auto max-w-6xl px-4 py-16 text-center">
            <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">Start with one brief.</h2>
            <p className="mt-3 text-muted-foreground">Create an account, paste a brief and review the draft in a few minutes.</p>
            <div className="mt-6 flex justify-center gap-3">
              <Button size="lg" render={<Link href="/signup" />}>
                Create an account <ArrowRight />
              </Button>
              <Button size="lg" variant="ghost" render={<Link href="/signin" />}>
                Sign in
              </Button>
            </div>
          </div>
        </section>
      </main>
      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 text-sm text-muted-foreground md:flex-row md:items-center">
          <Wordmark descriptor />
          <nav aria-label="Footer" className="flex gap-4 md:ml-8">
            <Link href="/help" className="hover:text-foreground">Help</Link>
            <Link href="/help/faq" className="hover:text-foreground">FAQ</Link>
            <Link href="/signin" className="hover:text-foreground">Sign in</Link>
          </nav>
          <p className="text-xs md:ml-auto">{FOOTNOTE}</p>
        </div>
      </footer>
    </>
  );
}
