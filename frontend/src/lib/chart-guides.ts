/** One source of truth for the chart explanations: shown in the "How to read this" drawers and on /help/analytics. */
export const CHART_GUIDES = {
  "estimate-vs-actual": {
    title: "Estimate vs actual by project",
    shows: "For each delivered project: the quoted range, the P50 quote and the hours actually spent.",
    computed:
      "The quote is the latest finalized estimate. The band is the sum of task minimums to the sum of task maximums of the included tasks. P50 is the simulated median total stored with the estimate (or the midpoint total if no simulation exists). Actual = recorded task actuals + unplanned work.",
    read: "A diamond above the band means the project ran over its whole range; below the band means it finished under the minimum. Diamonds close to the P50 dot are well-calibrated quotes.",
    next: "Open projects with large gaps and check their unplanned work and the categories that ran over. Use Bias by category to see whether it is systematic.",
    pitfalls:
      "Partial actuals (not every task entered) make projects look under budget. One project is an anecdote; look for patterns across several.",
  },
  "accuracy-over-time": {
    title: "Accuracy over time",
    shows: "Absolute percentage error of the P50 quote per delivered project, in delivery order, with a rolling median.",
    computed: "Error = |P50 − actual| ÷ actual for each delivered project. The line is the median of the last 5 projects.",
    read: "A falling rolling median means quotes are getting closer to reality as the system learns from your edits and actuals.",
    next: "If the median stops improving, check whether actuals are being entered for every delivered project and whether new kinds of projects were added.",
    pitfalls: "With few projects one outlier moves the median a lot. Changes in the type of work over time can look like accuracy changes.",
  },
  "bias-by-category": {
    title: "Bias by category",
    shows: "How much actual hours differ from the quoted midpoint, per task category, with uncertainty.",
    computed:
      "For every delivered task with an actual: ratio = actual ÷ quoted midpoint. The bar is the geometric mean of the ratios in the category; whiskers are a 95% interval (mean of log-ratios ± 1.96 standard errors). Categories with fewer than 5 tasks are hidden.",
    read: "1.0 = on target. Above 1 = the category is underestimated; below 1 = overestimated. Wide whiskers mean uncertain.",
    next: "For a clearly biased category, review its tasks' “Why this number?” panels and consider a learned rule; calibration already adjusts future drafts automatically.",
    pitfalls: "A category with whiskers crossing 1.0 has no clear bias yet. Ratios hide absolute size: a small category can be very biased but matter little.",
  },
  "range-coverage": {
    title: "Range coverage",
    shows: "How often actuals landed inside the quoted min–max and how often projects finished at or below P80.",
    computed:
      "Task coverage = share of delivered tasks with min ≤ actual ≤ max. Project coverage = share of delivered projects whose total actual ≤ the P80 total. Both targets are 80% (ranges are meant to be 10th–90th percentile; P80 by definition).",
    read: "Well below target: ranges are too narrow (over-confident). Well above: ranges are wider than needed.",
    next: "If coverage is low, prefer the P80 figure for commitments and review categories with the largest misses.",
    pitfalls: "Needs a reasonable number of tasks and projects before the share is meaningful; a few projects can swing it by tens of points.",
  },
  "unplanned-work": {
    title: "Unplanned work",
    shows: "Hours spent on work that was not in the quote, by reason and per project.",
    computed:
      "Unplanned entries are recorded on the Actuals tab with a reason (missed requirement, clarified scope, change request, other). Share = unplanned hours ÷ total actual hours of delivered projects.",
    read: "A high share of “missed requirement” points at the brief analysis; “change request” is usually client-driven and should be billed or re-quoted.",
    next: "Ask the clarifying questions the system proposes before quoting; add frequently missed items as tasks.",
    pitfalls: "Older entries without a reason show as “Not specified”.",
  },
  "planned-vs-actual": {
    title: "Planned vs actual by role and category",
    shows: "Total quoted midpoint hours against actual hours for delivered tasks, per role and per category.",
    computed: "Sums over delivered tasks that have an actual: planned = (min + max) ÷ 2 of the final quote; actual = recorded hours. Unplanned work is not included here.",
    read: "Bars where actual is clearly longer than planned show where the team spends more than quoted.",
    next: "Check staffing and rates for roles that run over; compare with Bias by category to find the cause.",
    pitfalls: "Absolute sums are dominated by large projects; use Bias by category for per-task ratios.",
  },
  "estimating-productivity": {
    title: "Estimating productivity",
    shows: "How long quoting takes and how much the AI draft is changed before it becomes a quote.",
    computed:
      "Lead time = finalize time − first document upload, per finalized estimate (median shown). Edits = logged changes by people or the agent (excluding the finalize event). Changed share = AI tasks whose hours were changed, or that were hidden or removed, ÷ AI tasks. Agent share = agent edits ÷ all edits.",
    read: "Shorter lead time and fewer edits with stable accuracy means quoting got faster without getting worse.",
    next: "If most AI tasks are changed, look at Bias by category and the learned rules; calibration reduces repeated corrections over time.",
    pitfalls: "Lead time includes waiting time (for example for client answers). Many small edits are not necessarily worse than one big one.",
  },
  "learning-impact": {
    title: "Learning impact",
    shows: "Error of the raw AI draft, the calibrated draft and the final quote for each delivered project, over time.",
    computed:
      "For each delivered project: raw = sum of raw model midpoints of AI tasks; calibrated = sum of the hours the system first showed (after calibration and analogs); final = midpoint total of the final quote. Error = |value − actual| ÷ actual.",
    read: "The gap between the raw and calibrated lines is what learning contributes; the gap between calibrated and final is what people still change.",
    next: "If calibrated is not better than raw, the history may be too small or too different from new work; keep entering actuals.",
    pitfalls: "Projects estimated before any history existed have identical raw and calibrated values.",
  },
} as const;

export type ChartGuideId = keyof typeof CHART_GUIDES;
