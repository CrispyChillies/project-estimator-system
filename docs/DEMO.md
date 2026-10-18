# 5-minute demo

Prerequisites: `cp .env.example .env`, `make up`, `make seed`. Works offline with `LLM_MODE=fake`
(default). With an API key: set `LLM_MODE=live` (or `record`, then `replay` for offline replays).

1. **Projects** (`/projects`) — 20 delivered projects with *Synthetic* badges, P50, final estimate,
   actual hours and accuracy %.
2. **Backtest** (`/backtest`) — click **Re-run backtest**. Project level: E4 (full system) has the
   lowest MdAPE, near-zero bias and P80 coverage ≈ 80% vs ~30% for the raw LLM; CIs are shown and a
   small-sample warning is visible. Learning curve: calibrated error falls with more training projects.
3. **Insights** (`/insights`) — factors per category (3rd-party integration ≈ ×1.4 actual layer),
   timeline of beliefs, P80 coverage, structural signals (PMs add *Security hardening*), learned
   rules → **Approve** one.
4. **New project** → paste or drop `data/fixtures/demo_brief.md` → **Generate estimate** with
   learning **off**, then again with learning **on**. In the Estimate tab pick *Compare with v1*:
   the integration tasks get ×1.2–1.5. Turn comparison off, click **?** on *ERP integration*:
   source quote, raw samples, factor with `n` edits/actuals, analogs from past projects.
5. Edit hours on a task by more than 20% → the **Why?** chips appear (optional). Open **Agent**,
   send *"increase backend hours by 20% and add an SSO task"* → diff cards; accept one op, reject the
   other. Rows are highlighted while pending; Activity shows `agent` and `user` events.
6. **Finalize** → Insights: the edit-layer timeline gains a point and factors move slightly.
   Actuals tab → enter hours (or import the CSV template) → add unplanned work → **Mark delivered** →
   accuracy summary; Insights rules list shows new proposals.
7. Create another project with `data/fixtures/demo_brief_2.md`, generate with learning: analogs now
   include your project's tasks and the factors reflect your edits.

Notes: in `fake` mode the LLM is a deterministic heuristic (see DECISIONS.md); in `replay` mode only
calls recorded by `make warm-cache` succeed — any prompt that changed (e.g. a newly approved rule is
injected) is a cache miss with a clear error.
