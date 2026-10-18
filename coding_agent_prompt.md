# PROMPT FOR CODING AGENT — "Calibr": a self-learning software project estimator

You are building a working, demo-ready repository from scratch in the current (empty) directory. Read this entire brief before writing any code. Do not ask me questions: where something is ambiguous, make the most reasonable decision, record it in `docs/DECISIONS.md` (one short entry per decision), and keep going. Commit at the end of every phase (see "Phases").

---

## 1. MISSION

Build an **internal pre-sales estimation platform** for a software company (think: a simplified, open, self-hosted alternative to the commercial tool "devtimate"), with **one differentiating feature**: the system **logs every edit a PM makes to the AI's draft estimate, plus real delivered hours, and uses that history to produce better estimates next time**, with ranges whose calibration can be measured.

Core user flow:

1. A PM uploads a client brief / RFP / notes (PDF, DOCX, MD, TXT, or pasted text).
2. The AI extracts requirements, assumptions, risks and open questions, then proposes a structured estimate: **modules → tasks**, each with a delivery role, a category, and a **min–max hour range**, with rationale and source references.
3. The PM reviews and edits in a spreadsheet-like editor. A chat **AI Agent** can modify the estimate through natural-language commands, always as **reviewable diffs** (accept/reject).
4. The PM finalizes the estimate. Every deviation from the AI baseline is already in an append-only **edit log**; finalizing triggers a learning update.
5. After delivery, actual hours are entered per task (manually or CSV). This triggers a second learning update.
6. Next time a similar brief arrives, the draft is **calibrated** using what the system learned, and the UI shows exactly why each number is what it is.
7. An **Insights** page shows what was learned; a **Backtest** page proves (with numbers) that learning improves accuracy.

### Non-goals (do NOT build)
Proposal/PDF generation, Jira/Asana integrations, multi-tenancy, billing, email, real authentication/password flows, Celery/Redis/Kubernetes, calendar scheduling. Keep scope tight and polished instead.

---

## 2. FIXED TECH STACK

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router) + TypeScript (strict) + Tailwind + **shadcn/ui** (all UI built from shadcn components; initialize with the shadcn CLI) |
| Frontend libs | TanStack Query, TanStack Table, react-hook-form + zod, dnd-kit (drag & drop), Recharts via shadcn `chart`, sonner (toasts), lucide-react, next-themes (light/dark) |
| Backend | Python 3.12, **FastAPI**, Pydantic v2, SQLAlchemy 2.x, Alembic, psycopg 3 |
| DB | **PostgreSQL 16 with pgvector** (use the `pgvector/pgvector` image) |
| LLM | **OpenAI** models through **LangChain** (`langchain`, `langchain-openai`; use LangGraph only if the current LangChain agent API requires it) |
| Packaging | **Docker + docker compose**: `db`, `backend`, `frontend`. One command (`make up`) starts everything; migrations run automatically on backend start |
| Tooling | `uv` or `pip-tools` for Python lockfile, `pnpm` for frontend, ruff, pytest, ESLint, Makefile |

Rules for versions and APIs:
- Look up the **current stable versions** yourself and pin them in lockfiles. LangChain's agent/tool-calling API has changed across major versions: **read the installed version's documentation/source before writing agent code**; do not rely on memory.
- Do not hard-code OpenAI model names in code. Read `OPENAI_MODEL` (chat, must support structured outputs/tool calling) and `OPENAI_EMBEDDING_MODEL` from env; document in `.env.example` that the user must set a current model.
- Never commit secrets. Provide `.env.example`.

---

## 3. REPOSITORY LAYOUT

```
.
├── docker-compose.yml
├── Makefile                  # up, down, logs, seed, warm-cache, backtest, test, lint, reset
├── .env.example
├── README.md                 # quickstart + screenshots section + architecture summary
├── docs/
│   ├── ARCHITECTURE.md
│   ├── LEARNING.md           # the math + rationale of the learning system (section 7)
│   ├── DATASETS.md           # sources, licenses, mapping, limitations
│   ├── DECISIONS.md
│   └── DEMO.md               # 5-minute demo script (section 12)
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/ , alembic.ini
│   ├── app/
│   │   ├── main.py
│   │   ├── core/             # config (pydantic-settings), logging, deps
│   │   ├── db/               # session, base, models/*.py
│   │   ├── schemas/          # pydantic request/response models
│   │   ├── api/              # routers: projects, documents, estimates, tasks, agent, actuals,
│   │   │                     #         insights, backtest, settings, jobs, health
│   │   ├── services/         # estimates, edit_log, proposals, calibration, retrieval,
│   │   │                     # simulation, sensitivity, backtest, actuals, exports
│   │   ├── llm/              # client factory, cache/replay, cost logging, embeddings
│   │   ├── agents/           # extraction, decomposition, estimation, lessons, chat_agent (tools)
│   │   └── prompts/          # versioned prompt files (*.md or *.jinja), PROMPT_VERSION constants
│   ├── scripts/              # fetch_datasets.py, seed_demo.py, warm_cache.py, run_backtest.py
│   └── tests/
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── components.json       # shadcn config
│   └── src/ (app/, components/, lib/, hooks/)
├── data/                     # gitignored raw datasets; data/fixtures/ is committed (cached LLM outputs)
└── uploads/                  # gitignored, docker volume
```

---

## 4. DATA MODEL (PostgreSQL, Alembic migrations, UUID primary keys, `created_at/updated_at` everywhere)

Create all of these tables with proper foreign keys, indexes, and enums (use Postgres enums or CHECK constraints).

**Reference data**
- `users` (id, name, email, role `pm|engineer|admin`). Demo-only auth: seeded users + a user switcher in the UI; the frontend sends `X-User-Id`. Do not build passwords.
- `delivery_roles` (id, name, hourly_rate, currency, color) — seed: PM, Designer, Frontend, Backend, Mobile, QA, DevOps, ML/CV Engineer, Data Engineer.
- `task_categories` (id, key, name, description) — seed a taxonomy that includes at least: `auth`, `crud_admin`, `ui_frontend`, `api_backend`, `integration_3rd_party`, `payments`, `data_migration`, `reporting_analytics`, `notifications`, `ml_cv`, `infra_devops`, `testing_qa`, `design_ux`, `pm_overhead`, `security_compliance`, `other`.
- `settings` (key, value jsonb) — learning hyperparameters, model config, display options.

**Projects & documents**
- `projects` (name, client_name, domain, tech_tags text[], description, status `draft|quoted|won|lost|delivered`, `data_source` `user|dataset|synthetic`, started_at, delivered_at, created_by).
- `documents` (project_id, filename, mime, storage_path, extracted_text, uploaded_by).
- `document_chunks` (document_id, idx, text, `embedding vector(N)`), HNSW index.

**Estimate structure**
- `estimates` (project_id, version int, status `draft|final`, source `ai|manual|clone`, learning_enabled bool, model_snapshot jsonb, finalized_at, finalized_by, parent_estimate_id). Multiple versions per project; only one `final` is the "quoted" one.
- `modules` (estimate_id, name, description, position).
- `tasks` (estimate_id, module_id, title, description, category_id, delivery_role_id, `min_hours`, `max_hours`, position, enabled bool, confidence `low|medium|high`, rationale text, source_chunk_ids uuid[], origin `ai|user|agent`, `ai_key` text — stable key linking a task to its AI baseline, `embedding vector(N)`).
- `task_ai_baselines` — **immutable snapshot written at generation time**, one row per AI-generated task: `raw_min`, `raw_max` (uncalibrated LLM output, median of K samples), `analog_mid`, `analog_task_ids uuid[]`, `calibrated_min`, `calibrated_max`, `applied_factor`, `provenance jsonb` (see §6), `prompt_version`, `model`. Never updated after creation.
- `assumptions` (estimate_id, kind `assumption|risk|out_of_scope`, text, source_chunk_ids).
- `clarifying_questions` (project_id, estimate_id, question, why_it_matters, affected_task_keys text[], scenario_delta_min, scenario_delta_max, prior_probability, impact_score, status `open|asked|answered|dismissed`, answer, answered_at).

**The edit log (the heart of the idea)**
- `edit_events` — **append-only, never updated or deleted**: id, estimate_id, task_id (nullable), user_id (nullable), `actor` `user|agent|system`, `event_type` (`task_added|task_removed|task_restored|hours_changed|role_changed|category_changed|title_changed|task_toggled|module_added|module_removed|task_moved|estimate_finalized`), `field`, `old_value jsonb`, `new_value jsonb`, `reason_tag` (`underestimated_complexity|overestimated|reuse_existing_code|client_specific|scope_added|scope_removed|risk_buffer|other`), `reason_text`, `proposal_id` (nullable), created_at.
- `change_proposals` (estimate_id, session_id, status `pending|accepted|rejected|partial`, `ops jsonb` — list of operations each with its own status, rationale, resolved_by, resolved_at).
- `agent_sessions` (estimate_id, mode `generate|chat`, created_by) and `agent_messages` (session_id, role, content, tool_calls jsonb).

**Actuals**
- `task_actuals` (task_id, actual_hours, source `manual|csv|dataset`, recorded_by, note).
- `unplanned_actuals` (project_id, title, category_id, hours, note) — work done that was never in the estimate, so scope creep is **separable** from estimation error.

**Learning**
- `calibration_stats` (layer `edit|actual`, scope_type `global|category|category_author`, scope_key, n, mean_log_ratio, var_log_ratio, shrunk_mean, shrunk_var, residuals jsonb (capped at 500 values), updated_at).
- `calibration_runs` (trigger `estimate_finalized|project_delivered|manual|backtest`, layer, stats_snapshot jsonb, created_at) — lets the Insights page chart "what the system believed over time".
- `learned_rules` (text, layer, scope jsonb, evidence_event_ids uuid[], evidence_count, status `proposed|active|disabled`, approved_by, created_at) — natural-language lessons (see §7.4).

**Ops / evaluation**
- `llm_calls` (purpose, model, prompt_hash, input_tokens, output_tokens, latency_ms, cost_usd, cache_hit bool, request jsonb, response jsonb).
- `llm_raw_estimates` (project_id, task_key, run_idx, prompt_version, model, raw_min, raw_max, payload jsonb) — cached raw LLM outputs so backtests never re-call the LLM.
- `backtest_runs` (config jsonb, status, created_at) and `backtest_results` (run_id, estimator_key, project_id, level `task|project`, n_train, predicted_p50, predicted_p80, actual, ape, covered_p80, interval_width).
- `jobs` (kind, status `queued|running|done|failed`, progress float, error, result_ref, created_at) — long operations (generation, backtest) run via FastAPI `BackgroundTasks` and the frontend polls `/jobs/{id}`.

---

## 5. LLM LAYER (backend/app/llm, backend/app/agents)

1. **One LLM gateway** wrapping `ChatOpenAI`/`OpenAIEmbeddings`. Every call goes through it. It must: retry with backoff, log to `llm_calls` (tokens, latency, estimated cost), and support `LLM_MODE`:
   - `live`: call OpenAI.
   - `replay`: serve from cache keyed by `prompt_hash` (hash of model + prompt version + rendered messages); **raise a clear error on cache miss** instead of silently calling the API.
   - `record`: live + write to cache (used by `make warm-cache`).
   Commit the cache fixtures for seeded demo projects under `data/fixtures/` so the demo works offline with no API key.
2. **All outputs use Pydantic structured output** (`with_structured_output` or the current equivalent). No regex parsing of free text.
3. **Prompts live in `app/prompts/`** as versioned files, with `PROMPT_VERSION` recorded in baselines. Taxonomies (categories, roles) are injected from the DB, not hard-coded in prompts.
4. **Determinism**: temperature ≤ 0.2 for extraction/decomposition. For hour estimation, take **K samples (`RAW_SAMPLES`, default 3)** and use the per-task **median**; store the spread.
5. Prompts must define the unit explicitly: *hours of work by one competent mid-level engineer of the given role, including implementation, self-testing, and code review, excluding project management overhead unless the task is a PM task*.

### Agents / chains
- **Extraction** → `ExtractionResult { summary, requirements[{id, text, type: functional|non_functional|constraint, source_chunk_ids}], ambiguities[], assumptions[], out_of_scope[], unknowns[{question, why_it_matters, affected_requirement_ids, scenario_if_yes: [task drafts with min/max hours], prior_probability}] }`. Every requirement must cite chunk ids; reject (and retry once) outputs that cite nonexistent chunks.
- **Decomposition** → modules and tasks (title, description, category key, role name, rationale, requirement ids, confidence). Must always include the "hidden" tasks (CI/CD, environments, QA/regression, code review, PM/communication) unless the brief says otherwise. Hours are NOT produced here.
- **Estimation** → given the *fixed* task list, return `{task_key, min_hours, max_hours}` for each. Run K times (§5.4). Structure comes from one call; hours from K calls. This prevents task-matching problems across samples and keeps variance measurable.
- **Lessons** → see §7.4.
- **Chat agent** (LangChain tool-calling agent with streaming over SSE). Tools (all **read-only or proposal-creating — tools never mutate the estimate directly**):
  `list_tasks`, `get_task_details`, `find_similar_past_tasks` (retrieval, §7.2), `explain_task` (returns provenance), `propose_add_task`, `propose_update_task`, `propose_remove_task`, `propose_split_task`, `propose_bulk_adjust` (e.g. "increase backend hours by 20%", filter by role/category/module), `propose_add_module`. Each tool appends an op to a pending `change_proposal`. The user accepts/rejects per-op or all; only then does the service layer apply the change **and write `edit_events` with `actor=agent`, `proposal_id`**. Rejections are also logged (`reason` optional) because they are signal too.
  The agent's system prompt must include the active `learned_rules` and a one-line summary of calibration for the categories involved.

---

## 6. GENERATION PIPELINE (service: `estimates.generate`)

Triggered by `POST /projects/{id}/estimates/generate` with `{ document_ids, learning: true|false }`. Runs as a job. Steps:

1. **Ingest**: extract text (PDF via `pypdf`/`pdfplumber`, DOCX via `python-docx`, MD/TXT direct). Chunk (~500–800 tokens, overlap), store chunks with embeddings.
2. **Extract** (§5) → store assumptions, risks, out-of-scope, unknowns.
3. **Decompose** → modules/tasks with categories and roles. Create `tasks` rows (`origin=ai`, `ai_key` set).
4. **Estimate raw hours** (K samples, median) → `raw_min/raw_max`. Also write `llm_raw_estimates`.
5. **Retrieve analogs** per task: embed `title + description`; vector search over tasks belonging to **other projects whose estimate is final/delivered**; filter same category when ≥3 candidates exist; `top_k=5`. Each analog carries `(raw_mid, final_mid, actual_mid?)`. **Always exclude the current project** (and, during backtests, any project not in the training set — see §8).
6. **Blend with analogs** (only if `learning=true`): see §7.2.
7. **Calibrate** (only if `learning=true`): see §7.3 → `calibrated_min/max`, `applied_factor`.
8. The task's displayed `min_hours/max_hours` = calibrated values when `learning=true`, else raw values. Persist `task_ai_baselines` including a **`provenance` JSON** per task:
   `{ raw: {min,max,samples:[...]}, analogs:[{task_id,project_name,title,similarity,raw_mid,final_mid,actual_mid}], blend_weight, calibration:{scope_used, n_edit, n_actual, mu_edit, mu_actual, factor, sigma}, source_chunk_ids, rules_applied:[rule_ids] }`.
9. **Sensitivity / clarifying questions** (§7.6): compute and store `clarifying_questions` with `impact_score`, ranked.
10. **Simulation**: compute project-level P10/P50/P80/P90 (§7.5) and store on the estimate (`estimates.summary jsonb`).

`learning=false` must produce the pure-LLM baseline using the same code path (so A/B comparisons are fair). The UI exposes a **"Generate with / without learning"** toggle and a side-by-side comparison view.

---

## 7. THE LEARNING SYSTEM (the differentiator — implement carefully; document in `docs/LEARNING.md`)

### 7.0 Principles
- **Always learn against the raw (uncalibrated) LLM output** stored in `task_ai_baselines.raw_*`. Never against the calibrated numbers the PM saw. This keeps the learning problem stationary and avoids double-counting.
- Two evidence layers with different trust:
  - **Edit layer**: `ratio = final_mid / raw_mid` (what PMs believe). Available at quote time, from the first project. It is a *proxy* for truth.
  - **Actual layer**: `ratio = actual_mid / raw_mid` (what happened). Available after delivery. Ground truth.
  Work in **log space**: `x = ln(ratio)`. `mid = (min + max) / 2`.
- Learning is **additive and auditable**: no opaque model training. Everything is counts, means, variances, retrieval, and text rules a human can read and disable.
- Cold start must degrade gracefully to the raw LLM (factor 1.0, wide default sigma).

### 7.1 When learning updates fire
- `estimate_finalized`: for every enabled AI-origin task with a baseline, compute the edit-layer sample `x_edit` from `(raw_mid, final_mid)` and update `calibration_stats(layer=edit)`. Also derive **structural signals** from `edit_events`: tasks the PM **added** (AI missed them → "missing-task rate" per category) and tasks the PM **removed** (false positives). Write a `calibration_runs` row.
- `project_delivered` (when actuals are saved and the project is marked delivered): for tasks with `task_actuals`, compute `x_actual` from `(raw_mid, actual_mid)`; update `calibration_stats(layer=actual)`. Compute **unplanned work share** from `unplanned_actuals` and store as a project-level stat (scope creep is reported separately and **not** mixed into per-task estimation error). Write a `calibration_runs` row, then run the Lessons chain (§7.4).
- Updates must be **idempotent** (recomputing from the full history yields the same stats). Implement as "recompute stats from scratch for affected scopes" — datasets are small — and keep it testable.

### 7.2 Analog (case-based) estimate
For each task, take retrieved analogs with `similarity ≥ SIM_MIN` (default 0.75). Reference hours = `actual_mid` if present, else `final_mid`. `analog_mid` = similarity-weighted median. Blend in log space: `ln(blend_mid) = (1-w)·ln(raw_mid) + w·ln(analog_mid)` with `w = clamp(W_PER_ANALOG · n_eff, 0, W_MAX)` where `n_eff` = number of qualifying analogs (defaults: `W_PER_ANALOG=0.12`, `W_MAX=0.6`). Make all constants settings.

### 7.3 Calibration factor with hierarchical shrinkage
Scopes: `global` → `category` → (edit layer only) `category_author` (the PM whose edits these are; applied only when the requesting user has enough history).
For a scope `s` with sample count `n`, mean `μ_s`, variance `σ²_s`, and parent shrunk values:
```
μ̃_s  = (n·μ_s + k·μ̃_parent) / (n + k)          # k = SHRINK_K, default 5
σ̃²_s = (n·σ²_s + k·σ̃²_parent) / (n + k)        # global parent default σ̃² = 0.25 until data exists
```
Combine layers: the edit layer is the **prior** for the actual layer:
```
μ_pred(scope) = (n_a·μ_a + k_a·μ̃_edit) / (n_a + k_a)         # k_a default 4
```
So with zero actuals the system follows PM consensus; as actuals accumulate they dominate. Final calibrated mid = `blend_mid · exp(μ_pred)` — **but if analogs were blended, avoid double counting**: apply calibration to the *raw* mid first (`raw_mid·exp(μ_pred)`) and then blend that with `analog_mid` using §7.2 weights. Document this decision in `docs/DECISIONS.md`.
Displayed range per task: lognormal quantiles around the calibrated mid using `σ̃`, default quantiles P10–P90 (`RANGE_QUANTILES` setting). Clamp to sensible bounds (min ≥ 0.25h, max ≤ 20× mid) and round to 0.5h.

### 7.4 Lessons (qualitative memory)
After finalize/deliver, run an LLM **Lessons chain** over aggregated deltas: top outlier tasks by |x|, structural additions/removals, and PM `reason_tag/reason_text`. It proposes short rules, each with scope and evidence, e.g. *"Integration tasks with third-party APIs are usually underestimated by ~30%: PMs raised 11 of 14 such tasks (reason: undocumented API quirks)."* Rules start as `proposed`; a human **approves/disables them in the UI**. Active rules (max 10, ranked by evidence_count) are injected into the Decomposition/Estimation prompts and the chat agent prompt, and their ids are listed in `provenance.rules_applied`. Never auto-activate rules; never let a rule contain client names or personal data.

### 7.5 Interval simulation (Evidence-Based-Scheduling style)
Monte Carlo (default 10,000 draws), per estimate:
- For each task draw a residual from the **empirical pool** of its category's actual-layer residuals `(x_i − μ_s)` if `n ≥ 8`, else from `N(0, σ̃²)`. Task draw = `calibrated_mid · exp(residual)`.
- Add one **shared project-level factor** per draw (from project-level log-ratio history when `≥ 5` delivered projects, else `N(0, σ_proj²)` with a configurable default) so task errors are not assumed independent.
- Report `P10/P50/P80/P90` of the total. Display P50 and P80 as the headline numbers; show the distribution as a histogram.
- Vectorize with NumPy; seed the RNG for reproducibility in tests.

### 7.6 Sensitivity → ranked clarifying questions
Each `unknown` from Extraction has `prior_probability p` and a scenario delta (`delta_mid` hours if "yes"). `impact_score = delta_mid · 4·p·(1-p)` (largest when most uncertain). Rank descending; show per question: "Resolving this could shift the total by ±X h". When a question is answered (`answered`), apply it: add/remove the scenario tasks via a **change proposal** (so it's logged and reviewable) and re-run the simulation.

### 7.7 Edit-log capture rules (must be correct — everything depends on it)
- All writes to tasks/modules go through **one service layer** (`services/estimates.py`) that diffs old vs. new and writes `edit_events` in the **same DB transaction**. The frontend never writes events.
- The first time a PM changes an AI task, the event's `old_value` must equal the baseline, so deltas are traceable to `task_ai_baselines`.
- UI nicety: when hours change by more than 20%, show a **non-blocking** "Why?" chip row (the `reason_tag` options + optional text). Skipping it must never block editing.
- Learning is computed from **(baseline, final task state)** at finalize time; the event stream is used for structural signals, reasons, audit, and the activity feed. Intermediate flip-flopping edits must not skew stats.

---

## 8. EVALUATION / BACKTEST (service: `backtest`, page `/backtest`, CLI `scripts/run_backtest.py`)

Goal: **prove** that learning helps, honestly, on small data.

- Input: projects with `data_source in (dataset, synthetic)` that have a final estimate, baselines, and actuals.
- Protocol (configurable): **leave-one-project-out**, or **chronological expanding window** if dates exist. For each held-out project, build calibration stats and the analog index **only from the training projects** — **no leakage**: retrieval, calibration, and rules must never see the held-out project. Write a unit test that fails if a held-out project's data influences its own prediction.
- **Never call the LLM during a backtest**: use cached `llm_raw_estimates`. Backtests must be cheap and deterministic.
- Estimators compared (each a function of train set → predictions):
  - `E0_median`: per-category median hours from training tasks (naive baseline).
  - `E1_raw_llm`: raw LLM median.
  - `E2_analogs`: raw + analog blend.
  - `E3_calibrated_edit`: + edit-layer calibration.
  - `E4_calibrated_full`: + actual layer (the full system).
- Metrics at **task level and project-total level**: MAPE, MdAPE, MMRE, PRED(25), signed bias (mean log-ratio), **P80 coverage** (share of actuals inside the P80 range/upper bound), and mean normalized interval width.
- Also output a **learning curve**: error vs. number of training projects (average over random orderings/folds).
- With ≤ 20 projects, report **bootstrap confidence intervals** for the headline metrics and show a visible warning "small sample" in the UI. Do not overclaim.
- UI: table of estimators × metrics (best highlighted, CI shown), learning-curve chart, coverage chart, per-project drill-down. Include a button "Re-run backtest" that starts a job.

---

## 9. API (FastAPI, `/api/v1`, OpenAPI auto-generated; generate TS types for the frontend with `openapi-typescript`)

- Projects: CRUD, list with status filter and search.
- Documents: upload (size limit, MIME/extension allowlist), list, delete, get chunks.
- Estimates: generate (job), list versions, get tree (modules→tasks with baselines and provenance), clone, finalize, delete; `GET /estimates/{id}/summary` (totals by module/role, cost via rate cards, P50/P80, histogram bins); `GET /estimates/{id}/compare?with=<estimate_id>` for raw-vs-learned.
- Tasks/modules: create, patch (with optional `reason_tag/reason_text`), delete (soft toggle), move/reorder, bulk ops.
- Agent: `POST /estimates/{id}/agent/messages` (SSE stream of tokens + proposal events); `GET/POST /proposals/{id}/ops/{op}/accept|reject`, `/proposals/{id}/accept_all|reject_all`.
- Questions: list ranked, answer, dismiss.
- Actuals: per-task upsert, CSV import (template download), unplanned actuals, `POST /projects/{id}/deliver`.
- Insights: calibration stats by scope/layer, calibration timeline, learned rules (list/approve/disable), accuracy-over-time series, structural signals.
- Backtest: start (job), list runs, get results.
- Export: estimate to XLSX/CSV (flat + structured).
- Settings: roles/rates, categories, learning hyperparameters (with defaults and validation), `POST /admin/reset-learning`.
- Jobs: get status/progress.
- Health: `/health` (db + migrations ok).

All endpoints typed, validated, with consistent error shape `{error: {code, message, details}}`.

---

## 10. FRONTEND (shadcn/ui, professional and dense, like a modern B2B SaaS)

Layout: collapsible **Sidebar** (Projects, Insights, Backtest, Settings), top bar with **user switcher** (demo users), theme toggle, `Toaster`. Light/dark. Keyboard-friendly. Skeletons for loading, helpful empty states, error boundaries.

Pages:
1. **/projects** — data table (TanStack): name, client, status badge, data-source badge (`Demo data` for synthetic/dataset — always visible), P50 hours, final estimate, actual hours, accuracy %. "New project" dialog; filters; search.
2. **/projects/[id]** — tabs:
   - **Overview & Documents**: drag-and-drop upload, paste text, parsed-chunk viewer, "Generate estimate" dialog (learning on/off toggle, document selection) with job progress.
   - **Estimate** (main screen): a **tree table** (modules as collapsible rows, tasks as rows): columns Title, Category (select), Role (select), Min, Max (inline numeric inputs, Tab/Enter navigation), Confidence badge, Δ vs AI badge (shows `+35%` when the PM changed it), enabled switch, drag handle (dnd-kit), comment count. Footer/side panel: totals by module & role, cost via rate cards, **P50/P80 + histogram**, version selector, Finalize button with confirm dialog explaining learning will update. Per-task **"Why this number?" Sheet** showing provenance: source quotes from the document, raw LLM range and samples, analogs found (with their final/actual hours), calibration factor and the evidence behind it (`n` edits / `n` actuals), and rules applied. Show the "Why?" reason chips on large edits. **Raw vs Learned** comparison toggle.
   - **Agent panel**: right-hand resizable panel/sheet (shadcn `Sheet` + `ResizablePanel`) with chat (mode: generate/chat), streaming responses, and **diff cards** for proposals (green/red highlights on affected rows, per-op accept/reject, accept-all). Accepted ops animate into the table.
   - **Questions & Risks**: ranked clarifying questions with impact badges ("could shift total ±X h"), answer inline; assumptions, risks, out-of-scope lists with source references.
   - **Actuals**: editable table of final tasks with Actual hours column, variance coloring, CSV import/export, "unplanned work" section, "Mark delivered" button (explains learning will update), post-delivery **accuracy summary** (estimate P50/P80 vs actual).
   - **Activity**: timeline of `edit_events` (who/what/when, reason chips), filterable by actor (user/agent).
3. **/insights** — "What the system has learned": calibration factors by category (bar chart of `exp(μ)` with `n` and uncertainty), edit-layer vs actual-layer comparison, **timeline of beliefs** from `calibration_runs`, accuracy-over-time line chart (APE per delivered project), P80 coverage gauge, structural signals (missing-task rates), and **Learned rules** list with approve/disable switches and evidence links to edit events.
4. **/backtest** — per §8.
5. **/settings** — rate cards, categories, learning hyperparameters (with reset-to-default and explanatory tooltips), model/LLM mode display, "Reset learned data" (confirm dialog), seed/demo info.

Use shadcn components throughout: `sidebar`, `data-table`, `table`, `tabs`, `sheet`, `dialog`, `alert-dialog`, `dropdown-menu`, `select`, `input`, `textarea`, `switch`, `badge`, `tooltip`, `popover`, `command`, `accordion`, `skeleton`, `progress`, `resizable`, `chart`, `card`, `separator`, `scroll-area`, `sonner`. Generate typed API hooks from OpenAPI types. No inline CSS hacks; consistent spacing/typography via Tailwind tokens. **Do not use `localStorage` for domain data** (UI preferences only).

---

## 11. DATASETS & DEMO DATA (`backend/scripts`, document in `docs/DATASETS.md`)

I want to demo with external data. Implement `scripts/fetch_datasets.py` with an adapter per dataset, and `scripts/seed_demo.py` to load everything:

1. **Primary (real, has hours):** the Mendeley Data set "Software Projects User Stories Estimates with PRED & MMRE" (DOI `10.17632/ytmwsf2997`): ten completed industrial web/mobile projects, 100+ user stories, with **actual hours** and **Planning Poker estimates**. Try to download it programmatically. **I have not verified a direct download URL or its license**: inspect the dataset page/files, check the license, and record both in `docs/DATASETS.md`. If direct download fails, print precise manual instructions (where to place the file under `data/raw/`) and continue with the fallback. **Inspect the actual columns before writing the mapper** and do not assume names.
   Mapping: dataset project → `projects` (`data_source=dataset`); user stories → tasks (module = epic/feature group if available, else "Backlog"); **Planning Poker = the human final** (write `edit_events` from the AI baseline to PP, `actor=user`, user = a seeded "Historical team" user); **actual hours → `task_actuals`**. The AI baseline = raw LLM estimate produced from the story text (via the gateway in `record` mode, cached to `data/fixtures/`). Category per task via a one-time cached LLM classification. This gives a real three-way comparison: raw LLM vs. human estimate vs. actual.
   Limitation to document: this evaluates *estimation given a decomposition*, not decomposition quality, and `n` is small.
2. **Optional (story points, larger):** note in `DATASETS.md` the existence of public story-point datasets (e.g. the Choetkiertikul/Tawosi sets of ~23k issues from 16 open-source projects). They use story points, not hours, so any point→hour conversion is an assumption; implement an adapter only if time permits and label such data clearly.
3. **Fallback & scale (synthetic):** `scripts/synthetic_projects.py` generates ~20 plausible projects (brief text, tasks, categories, roles) with **controllable, documented biases** (e.g. the LLM underestimates `integration_3rd_party` by ~35%, over-estimates `crud_admin` by ~15%, PMs add ~20% to `ml_cv`, ~12% of delivered hours are unplanned scope creep) plus noise, so the learning loop is demonstrable and verifiable (tests can assert the recovered factors are close to the planted ones). Briefs/descriptions may be generated once and cached as fixtures.
4. **Every non-user project shows a visible "Demo data" badge** (and synthetic ones a distinct "Synthetic" badge). Never present synthetic results as real-world evidence anywhere in the UI or docs.
5. `make seed` must be idempotent. `make warm-cache` runs the live LLM once to populate `data/fixtures/` (requires `OPENAI_API_KEY`); `LLM_MODE=replay` then runs the whole demo offline.

---

## 12. DEMO SCRIPT (implement `docs/DEMO.md` and make this exact flow work)

1. Open Projects: ~10–30 seeded delivered projects with badges, accuracy, actuals.
2. **Backtest**: calibrated estimators show lower error and better P80 coverage than raw LLM and the median baseline, with CIs and a small-sample warning.
3. **Insights**: calibration factors per category, timeline of beliefs, learned rules (approve one live).
4. New project → upload a messy brief → **Generate with learning OFF**, then **ON**: side-by-side view; open "Why this number?" on an integration task and show analogs + factor + evidence.
5. Edit a few hours with "Why?" chips; ask the **Agent** "increase backend hours by 20% and add an SSO task" → diff cards → accept one, reject one.
6. **Finalize** → Insights shows the category factor move (e.g. 1.21 → 1.24) and a new calibration run. Enter actuals → **Mark delivered** → accuracy summary + new lesson proposals.
7. Generate again for a similar brief: the draft now reflects the PM's earlier edits.

---

## 13. QUALITY BAR

- **Tests (pytest)**, LLM always mocked via `replay`/fakes: calibration math (shrinkage, idempotent recompute), simulation (seeded; quantile sanity, shared-factor effect), edit-log capture (diffs, transaction atomicity, baseline linkage), proposal accept/reject applying + logging, sensitivity scoring, **backtest leakage test**, CSV import validation, planted-bias recovery on synthetic data. Aim for the learning/evaluation modules to be well covered; don't chase coverage elsewhere.
- Backend: ruff clean, type hints, services separated from routers, no business logic in routers. Frontend: ESLint clean, `tsc --noEmit` passes, no `any` in domain code.
- Docker: multi-stage builds, healthchecks, `depends_on: condition: service_healthy`, named volumes for Postgres and uploads, non-root users where practical. `docker compose up` on a fresh clone with only `.env` filled must work.
- Observability: structured logs; `llm_calls` table is queryable; a small "LLM usage" card in Settings (calls, tokens, estimated cost).
- Security/privacy hygiene: upload limits and type checks; never log full document text at INFO; README note that client documents are sent to OpenAI and a stub setting `LLM_REDACT_PII` (off by default) documented as future work.
- README: quickstart in ≤ 6 commands, architecture diagram (Mermaid), screenshots placeholder, and a "How learning works" summary linking to `docs/LEARNING.md`.

---

## 14. PHASES (commit after each; keep the app runnable at every phase)

1. **Scaffold**: repo layout, docker compose (db+backend+frontend), health endpoint, Alembic baseline, shadcn init, app shell with sidebar/theme/user switcher, Makefile.
2. **Data model & CRUD**: all tables/migrations, seed reference data (roles, categories, users), projects/documents APIs and UI, upload + parsing + chunking.
3. **LLM gateway & generation**: gateway with record/replay + cost logging, extraction → decomposition → K-sample estimation, baselines + provenance, estimate editor UI (tree table, inline editing, totals).
4. **Edit log & proposals & agent**: service-layer diffing, `edit_events`, reason chips, activity feed, change proposals, chat agent with tools and diff cards (SSE).
5. **Learning core**: stats recompute, shrinkage calibration, analog retrieval/blending, simulation, sensitivity questions, finalize hook, "Why this number?" sheet, raw-vs-learned toggle.
6. **Actuals & delivery**: actuals UI/CSV, unplanned work, deliver hook, lessons chain + rules UI.
7. **Datasets & seeding**: fetch adapters, mappers, synthetic generator, `make seed`, fixtures cache.
8. **Backtest & Insights**: backtest service/UI/CLI, insights charts, small-sample CIs.
9. **Polish & verification**: tests green, lint clean, docs written, fresh-clone `docker compose up` verified end-to-end, demo script walked through and fixed.

---

## 15. RULES OF ENGAGEMENT

- Prioritize **correctness of the edit log and learning math** over feature breadth and visual extras. If time is tight, cut UI polish before cutting tests for those modules.
- Build for **explainability**: any number shown to a PM must be traceable (provenance) to a source, analogs, and calibration evidence.
- Keep hyperparameters in `settings`, not scattered constants; document each with defaults and rationale in `docs/LEARNING.md`.
- Don't invent data silently: all synthetic/dataset-derived records carry `data_source`, and the UI shows it.
- When you finish, verify by actually running: `docker compose up --build`, `make seed`, `make test`, `make backtest`, and walk through `docs/DEMO.md`. Report what works, what doesn't, and any deviations from this brief at the end of your final message and in `docs/DECISIONS.md`.
