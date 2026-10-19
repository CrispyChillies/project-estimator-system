import Link from "next/link";

import { CHART_GUIDES, type ChartGuideId } from "@/lib/chart-guides";

function Shot({ name, alt, caption }: { name: string; alt: string; caption: string }) {
  return (
    <figure className="my-4 overflow-hidden rounded-lg border">
      {/* eslint-disable-next-line @next/next/no-img-element -- static screenshots captured by Playwright */}
      <img src={`/help/${name}.png`} alt={alt} width={1440} height={900} loading="lazy" className="h-auto w-full" />
      <figcaption className="border-t bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        {caption} Screenshots show fictional sample data.
      </figcaption>
    </figure>
  );
}

const H2 = ({ id, children }: { id?: string; children: React.ReactNode }) => (
  <h2 id={id} className="mt-8 scroll-mt-20 text-lg font-semibold">
    {children}
  </h2>
);

function GettingStarted() {
  return (
    <>
      <p>This is the whole loop, from a client brief to a quote that improves the next one.</p>
      <H2 id="project">1. Create a project</H2>
      <p>
        Open <b>Projects → New project</b>. Give it a name and, optionally, the client, domain and a short description. Every
        project is private to you until you share it.
      </p>
      <Shot name="projects" alt="Projects list with the New project button" caption="Projects list." />
      <H2 id="brief">2. Upload or paste the brief</H2>
      <p>
        On <b>Overview &amp; Documents</b>, upload PDF, DOCX, Markdown or text files (up to 15 MB each) or paste text. The
        document is split into passages so every task can point back to the text it came from.
      </p>
      <H2 id="generate">3. Generate an estimate</H2>
      <p>
        Click <b>Generate estimate</b>. The AI extracts requirements, groups them into tasks and estimates each task as an hour
        range. Your history is applied as calibration, and similar past projects are used as context. When it finishes, the
        Estimate tab and the chat agent open.
      </p>
      <Shot name="estimate" alt="Estimate table with groups, tasks, ranges and the totals panel" caption="Estimate workspace." />
      <H2 id="review">4. Review and edit</H2>
      <p>
        Edit hours inline, change roles and categories, drag tasks to reorder, hide tasks or add your own. Open{" "}
        <b>Why this number?</b> on any task to see the raw AI hours, the calibration applied and the source passage.
      </p>
      <Shot name="why" alt="Why this number panel with raw AI hours, calibration and references" caption="Why this number?" />
      <H2 id="agent">5. Edit with the chat agent</H2>
      <p>
        Press <b>Ctrl/⌘+J</b> on the Estimate tab and type what you want, for example “fit this to 400 hours”. See{" "}
        <Link href="/help/chat-agent">Working with the chat agent</Link>.
      </p>
      <Shot name="agent" alt="Chat agent panel next to the table with tool call cards" caption="Chat agent editing the table." />
      <H2 id="finalize">6. Finalize the quote</H2>
      <p>
        <b>Finalize</b> makes the version read-only. The differences between the AI draft and your final numbers now feed the
        calibration. To change a finalized quote, <b>Clone</b> it into a new draft version.
      </p>
      <H2 id="actuals">7. After delivery: enter actuals</H2>
      <p>
        On the <b>Actuals</b> tab, enter the real hours per task (or import the CSV template), add unplanned work with its
        reason, and click <b>Mark delivered</b>. See <Link href="/help/closing-the-loop">Closing the loop</Link>.
      </p>
      <H2 id="insights">8. Read Insights</H2>
      <p>
        Insights shows how accurate your quotes were and where the hours went. See{" "}
        <Link href="/help/analytics">Analyzing productivity with the charts</Link>.
      </p>
      <Shot name="insights" alt="Insights page with productivity and accuracy charts" caption="Insights." />
    </>
  );
}

function ChatAgent() {
  return (
    <>
      <p>
        The agent works directly on the estimate you are looking at. It changes the table through named tools, and every tool call
        is shown as a card in the chat.
      </p>
      <H2 id="can-do">What it can do</H2>
      <ul className="list-disc space-y-1 pl-5">
        <li>Read: summarize the estimate, list or explain tasks, search the brief, find similar past projects and tasks.</li>
        <li>
          Change: add groups and tasks, change hours, roles and categories, scale or round many tasks, fit the estimate to a
          budget, make a role a share of the total, split, merge, move, hide or delete tasks.
        </li>
        <li>Remember: settings for the session (for example a budget) and facts about the project.</li>
        <li>Ask: when a request is vague, or names something that does not exist, it asks instead of guessing.</li>
      </ul>
      <H2 id="examples">Examples</H2>
      <ul className="list-disc space-y-1 pl-5">
        <li>“Fit this to 400 hours”: hours are scaled with a fixed rule so the total of max hours is exactly 400 (no task is cut by more than 75%).</li>
        <li>“Add an SSO task under Authentication with 12–20 h”</li>
        <li>“Reduce QA by 20%” or “Make backend about 40% of the total”</li>
        <li>“Why is the payments task so high?”</li>
        <li>Select rows in the table, then “make these 20% shorter”.</li>
        <li>
          Shortcuts: <code>/fit 400</code>, <code>/adjust +10% backend</code>, <code>/round</code>, <code>/similar</code>,{" "}
          <code>/remember …</code>, <code>/budget 400</code>, <code>/new</code>.
        </li>
      </ul>
      <H2 id="modes">Auto and Review mode</H2>
      <p>
        In <b>Auto</b> mode, safe changes apply immediately. In <b>Review</b> mode every change waits for your <b>Confirm</b>.
        In both modes the agent always asks first before deleting, before changing the total by more than 30%, before more than
        25 changes in one turn, and before touching rows you edited in the last 30 minutes.
      </p>
      <H2 id="undo">Undo</H2>
      <p>
        Every applied card has <b>Undo</b>; a turn with several changes also has <b>Undo all</b>. If you edited a row after the
        agent changed it, undo keeps your edit and tells you so (partial undo). <b>Show in table</b> highlights the rows a card
        changed.
      </p>
      <H2 id="sessions">Sessions and memory</H2>
      <p>
        Each estimate can have several chat sessions (create, switch, rename, pin, archive). Long conversations are summarized
        automatically. The brain icon opens <b>What the agent remembers</b>: session settings such as the budget (binding for
        tools like fit-to-budget) and project memories you can edit, disable or delete.
      </p>
      <H2 id="limits">Limits and safety</H2>
      <ul className="list-disc space-y-1 pl-5">
        <li>One running turn per session; use <b>Stop</b> to cancel. Each turn has a step limit.</li>
        <li>AI use counts against your daily allowance (see the FAQ).</li>
        <li>Text inside documents is treated as information, never as instructions to the agent.</li>
      </ul>
    </>
  );
}

function Estimates() {
  return (
    <>
      <H2 id="ranges">Ranges</H2>
      <p>
        Each task has a min and a max in hours for one mid-level engineer of the task&apos;s role. Think of them as an optimistic
        and a pessimistic but realistic case (roughly the 10th and 90th percentile).
      </p>
      <H2 id="p50-p80">P50 and P80</H2>
      <p>
        The totals come from a simulation of thousands of possible outcomes. <b>P50</b>: half of the outcomes are below this
        total. <b>P80</b>: 80% are below it. P80 is the safer figure for a commitment.
      </p>
      <H2 id="confidence">Confidence</H2>
      <p>How sure the AI is that it understood the task from the brief. Low confidence often means a clarifying question is worth asking (Questions &amp; Risks tab).</p>
      <H2 id="provenance">Provenance (“Why this number?”)</H2>
      <p>
        For every AI task: the raw AI hours (the median of several samples), the calibration factor and the evidence behind it,
        similar past tasks blended in when they are close enough, the passage of the brief it came from, and any learned rules
        that applied.
      </p>
      <H2 id="references">References</H2>
      <p>
        Up to three of the most similar finalized projects you have access to are given to the AI as context when an estimate is
        generated. If fewer projects are similar enough, fewer are used: the list is never padded.
      </p>
      <H2 id="calibration">Calibration</H2>
      <p>
        The system compares the raw AI hours with what people finally quoted (edit layer) and with delivered actual hours (actual
        layer), per category. The result is a multiplier, pulled toward 1.0 when there is little evidence. With few actuals it
        follows your team&apos;s edits. As actuals accumulate, they dominate.
      </p>
    </>
  );
}

function ClosingTheLoop() {
  return (
    <>
      <H2 id="actuals">Entering actuals</H2>
      <p>
        Open the delivered project&apos;s <b>Actuals</b> tab. Type the real hours per task, or download the CSV template, fill it in
        and import it (invalid rows are reported and nothing is imported until they are fixed).
      </p>
      <H2 id="unplanned">Unplanned work</H2>
      <p>
        Work that was never in the quote is recorded separately with a reason: missed requirement, clarified scope, change
        request or other. It is reported in Insights instead of being mixed into estimation error.
      </p>
      <H2 id="deliver">Mark delivered</H2>
      <p><b>Mark delivered</b> locks in the comparison between quote and actuals and updates the actual-layer calibration.</p>
      <H2 id="learns">What the system learns</H2>
      <ul className="list-disc space-y-1 pl-5">
        <li>At finalize: how your team changed the AI draft, per category (edit layer).</li>
        <li>At delivery: how actual hours compared with the raw AI hours (actual layer).</li>
        <li>Recurring patterns are proposed as lessons. You approve or disable them in Insights.</li>
      </ul>
      <H2 id="why-more">Why more delivered projects help</H2>
      <p>
        Each category&apos;s correction is estimated from your history. With few projects the correction stays cautious. Every
        delivered project with actuals narrows the uncertainty, and makes similar-project references and range coverage more
        reliable.
      </p>
    </>
  );
}

function Analytics() {
  return (
    <>
      <p>
        Insights → <b>Productivity &amp; accuracy</b> uses only projects you can see. Every chart shows its sample size (n). When
        there are too few projects it shows “Not enough data yet” instead of a misleading number.
      </p>
      {(Object.keys(CHART_GUIDES) as ChartGuideId[]).map((id) => {
        const g = CHART_GUIDES[id];
        return (
          <section key={id} id={id} className="scroll-mt-20">
            <H2>{g.title}</H2>
            <dl className="mt-2 space-y-2">
              {(
                [
                  ["What it shows", g.shows],
                  ["How it is computed", g.computed],
                  ["How to read it", g.read],
                  ["What to do next", g.next],
                  ["Pitfalls", g.pitfalls],
                ] as const
              ).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-xs font-semibold text-muted-foreground uppercase">{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          </section>
        );
      })}
    </>
  );
}

const TERMS: [string, string][] = [
  ["Actual layer", "Calibration learned from delivered hours compared with the raw AI hours."],
  ["Brief", "The client document(s) the estimate is generated from."],
  ["Calibration factor", "A per-category multiplier applied to raw AI hours, learned from your history."],
  ["Confidence", "How sure the AI is that it understood a task from the brief."],
  ["Edit layer", "Calibration learned from how people changed AI drafts before finalizing."],
  ["Finalize", "Make an estimate version read-only and the quoted one; triggers learning from your edits."],
  ["Min–max range", "Optimistic to pessimistic hours for one task (about 10th–90th percentile)."],
  ["P50 / P80", "Totals that 50% / 80% of simulated outcomes stay below."],
  ["Reference library", "Archived reference projects an administrator can make available to everyone; marked wherever used."],
  ["References", "Up to three similar finalized projects used as context for a new estimate."],
  ["Session", "One conversation with the chat agent about an estimate."],
  ["Unplanned work", "Hours spent on work that was not in the quote, recorded with a reason."],
];

function Glossary() {
  return (
    <dl className="space-y-3">
      {TERMS.map(([t, d]) => (
        <div key={t}>
          <dt className="font-medium">{t}</dt>
          <dd className="text-muted-foreground">{d}</dd>
        </div>
      ))}
    </dl>
  );
}

const FAQ: [string, React.ReactNode][] = [
  [
    "Who can see my projects and documents?",
    "Only you, until you share a project. Shared people can view or edit as you choose. “Share history with the workspace” shares a finished project's numbers and task titles for other people's calibration and references. Its documents stay private.",
  ],
  [
    "Where do uploaded documents go?",
    "They are stored in the application database and sent to the configured AI provider to produce the estimate. Do not upload material your client has not allowed you to process this way.",
  ],
  [
    "What is the AI allowance?",
    "Each person has a daily AI budget set by the administrator (by default about USD 0.50). If it is used up, AI features pause with a message saying when they reset (00:00 UTC). Editing by hand always works.",
  ],
  ["Can I choose a different AI model?", "No. The model is fixed by the administrator for cost and consistency."],
  ["How do I share a project?", "Open the project and click Share. Add people by the email address they signed up with."],
  ["I forgot my password.", "Ask your administrator for a one-time reset link."],
  ["Can I delete a project?", "Yes, the owner can delete a project. Finalized quotes and actuals are deleted with it."],
];

function Faq() {
  return (
    <div className="space-y-4">
      {FAQ.map(([q, a]) => (
        <section key={q}>
          <h2 className="font-medium">{q}</h2>
          <p className="text-muted-foreground">{a}</p>
        </section>
      ))}
    </div>
  );
}

export const HELP_PAGES = [
  { slug: "getting-started", title: "Getting started", summary: "The end-to-end workflow, step by step.", Body: GettingStarted },
  { slug: "chat-agent", title: "Working with the chat agent", summary: "What it can do, modes, undo, sessions and memory.", Body: ChatAgent },
  { slug: "estimates", title: "Understanding an estimate", summary: "Ranges, P50/P80, confidence, provenance, references, calibration.", Body: Estimates },
  { slug: "closing-the-loop", title: "Closing the loop", summary: "Actuals, unplanned work and what the system learns.", Body: ClosingTheLoop },
  { slug: "analytics", title: "Analyzing productivity with the charts", summary: "Each Insights chart: definition, reading, next steps, pitfalls.", Body: Analytics },
  { slug: "glossary", title: "Glossary", summary: "Short definitions.", Body: Glossary },
  { slug: "faq", title: "FAQ", summary: "Privacy, AI allowance, sharing.", Body: Faq },
] as const;
