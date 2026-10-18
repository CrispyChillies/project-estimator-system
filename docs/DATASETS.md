# Datasets

All non-user data carries `projects.data_source` and a visible badge (**Synthetic** or
**Demo data**). Synthetic results are never presented as real-world evidence.

## 1. Mendeley — "Software Projects User Stories Estimates with PRED & MMRE" (primary, real)

* DOI: `10.17632/ytmwsf2997`, page: https://data.mendeley.com/datasets/ytmwsf2997
* Described as ten completed industrial web/mobile projects, 100+ user stories, with actual hours
  and Planning Poker estimates.
* **Status at build time: NOT verified.** The Mendeley page and public API returned HTTP 503 during
  development, so neither a direct download URL nor the license could be confirmed. In the live-validation
  session (2026-10-18), `data/raw/mendeley/` was still empty; the importer and backtest on this dataset were
  skipped and nothing was approximated. Do not
  redistribute the files until you have checked the license on the dataset page and recorded it here:
  * License: _to be filled in after manual verification_
* Adapter: `backend/app/datasets/mendeley.py`
  * `make fetch-datasets` tries `https://data.mendeley.com/public-api/datasets/ytmwsf2997`
    (metadata + file download URLs). On failure it prints manual instructions:
    download the files from the dataset page and put the CSV/XLSX files in `data/raw/mendeley/`.
  * `inspect()` prints file names, row counts and the **actual columns**. `load()` maps columns by
    header pattern (project, story text, actual hours, Planning Poker) and stops with the column
    list if it cannot map them unambiguously — edit the mapping then.
* Mapping:
  * dataset project → `projects` (`data_source=dataset`), one "Backlog" module
  * user story → task; category via the classifier (keyword classifier offline; replace with a
    cached LLM classification in live/record mode if desired)
  * raw AI baseline = K LLM estimates of the story text through the gateway (cached in
    `data/fixtures` in record mode)
  * **Planning Poker = the human final**, written as `hours_changed` edit events from the AI
    baseline (actor = "Historical team"). The final range is PP ±15% (mid = PP).
  * actual hours → `task_actuals` (source `dataset`)
* Limitations: evaluates *estimation given a decomposition*, not decomposition quality; n is small;
  if Planning Poker values are story points rather than hours the edit layer is meaningless for this
  dataset (inspect before use).

## 2. Story-point datasets (optional, not implemented)

Public story-point datasets exist (e.g. Choetkiertikul et al. and Tawosi et al., ~23k issues from
16 open-source projects). They use story points, not hours; any point→hour conversion is an
assumption. No adapter was implemented.

## 3. Synthetic history (fallback & scale)

`backend/app/datasets/synthetic.py` — deterministic (seeded) generator of 20 projects with briefs,
modules, tasks, K raw samples, PM edits (with reason tags), PM-added/removed tasks, actuals and
unplanned work. Planted biases (also printed by `scripts/synthetic_projects.py`):

| Category | actual / true-size | final / raw (PM) |
|---|---|---|
| integration_3rd_party | 1.35 | 1.16 |
| crud_admin | 1/1.15 | 0.93 |
| ml_cv | 1.25 | 1.20 (PMs add ~20%) |
| data_migration | 1.30 | 1.14 |
| others | see `ACTUAL_BIAS` | √(actual bias) — PMs correct about half the bias in log space |

Plus: per-task noise σ=0.18, shared project noise σ=0.10, raw-LLM noise σ=0.25 and the raw LLM sees
only `size^0.5` of project scale; PMs edit ~65% of tasks; PMs add *Security hardening* in ~60% of
projects (the AI misses it) and remove *Code review* in ~30%; ~12% of delivered hours are unplanned
scope creep. `tests/test_planted_bias.py` asserts these factors are recovered within statistical
tolerance.

In `fake` mode, raw estimates for synthetic projects come from the simulator (`model=synthetic-raw-llm`,
`model_key=fake-v1`). In `record`/`live`/`replay` they come from the configured model (gpt-6-luna, recorded in
`data/fixtures/llm_cache`). Actuals and PM edits are always simulated.
