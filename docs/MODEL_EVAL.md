# Model bake-off (2026-10-18)

Script: `backend/scripts/bakeoff.py` (`--dry-run` prints planned calls/cost and refuses above the $1.50 section
budget). Raw results: `data/fixtures/bakeoff_results.json`. Inputs are 3 seeded **synthetic** briefs (small with
an appended block of deliberately contradictory/ambiguous notes, medium, large). Pipeline per brief:
Extraction → Decomposition → K=3 Estimation (learning off), recorded under the model's `model_key`; then 8
scripted agent commands on the medium estimate.

**Caveat:** 3 short briefs (≈0.8–1.1k characters each — the synthetic briefs are small, so "large" is only
modestly larger) and 8 commands is a very small evaluation. The thresholds below are heuristics, not
statistically validated cut-offs.

## Results

| Metric | A `gpt-6-luna` (reasoning `none`) | B `gpt-6.1-sol` (reasoning `low`) |
|---|---|---|
| Schema validity, first attempt | 15/15 (100%), 0 retries | not run (see decision) |
| Citation validity (first attempt) | 40/40 valid (0% invalid), 0 uncited requirements | — |
| Tasks / modules (small, medium, large) | 19/7, 19/7, 22/10 | — |
| Hidden tasks (CI/CD, QA, review, PM) | present in 3/3 | — |
| Unknowns on ambiguous brief | 5 — all 5 planted contradictions found (payments yes/no, Azure SSO, native vs PWA, regional visibility, 6 weeks vs 3 months) | — |
| Median per-task CV of midpoints across K=3 | 0.083 / 0.035 / 0.109 | — |
| Project-total spread (max−min)/mean across samples | 0.20 / 0.12 / 0.26 | — |
| Raw total ÷ seeded actual (sanity only) | 3.09 / 2.87 / 3.75 | — |
| Agent: correct tool selection | 8/8 | — |
| Agent: malformed/failed tool calls | 1 (a `propose_remove_module` lookup that found no exact match) | — |
| Estimate mutated without accept | no | — |
| Latency per call p50 / p95 | 2.2 s / 15.9 s (generation ≈ 40 s end to end) | — |
| Cost per full generation (structured calls) | ≈ $0.0028 | dry-run estimate ≈ $0.08 |
| Cost of the 8 agent commands | $0.0021 | — |
| Total bake-off spend | **$0.0107** | $0 |

Manual notes:
* Ambiguity detection on the contradictory brief was good: each planted contradiction became a clarifying
  question with a sensible `why_it_matters`.
* The raw totals are ≈3× the synthetic "actuals". That is expected — the synthetic generator's hour scale is
  arbitrary (template base hours), not calibrated to a real model. Calibration should learn a large
  down-scaling factor; this is a property of the synthetic data, not evidence about Luna's real accuracy.
* "remove the admin dashboard module": no such module existed; Luna said so but still proposed removing the
  closest module (Catalog & Content Administration). It is only a pending proposal, but a stricter behaviour
  (ask first) would be better. Counted as correct tool selection, noted as a quality issue.
* "set QA tasks to at least 8 hours": the QA task was already above 8 h; Luna explained this but still filed a
  no-op update proposal. Minor.
* "make it cheaper": asked a clarifying question, no proposal — correct.
* Streaming bug found here: the final assistant text was emitted twice over SSE (fixed in §5).

## Decision

Heuristic rule: choose A if first-attempt schema validity ≥ 95%, invalid citations ≤ 5%, ≥ 7/8 correct agent
tool calls, median per-task CV ≤ 0.35, and the main ambiguities are detected.

**A (`gpt-6-luna`, reasoning `none`) passes every criterion → chosen.** Following the hard rule "cheapest
model that passes; only move up if it fails", **B was not run** — no Sol spend was needed. The B column is
therefore empty on purpose; the comparison claim is only "A is sufficient on these criteria", not "A is as
good as B".

`.env.example` now sets `OPENAI_MODEL=gpt-6-luna`, `LLM_REASONING_EFFORT=none`,
`OPENAI_EMBEDDING_MODEL=text-embedding-3-small`.
