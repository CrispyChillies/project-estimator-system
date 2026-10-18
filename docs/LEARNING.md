# How Calibr learns

Calibr never trains an opaque model. Everything it "knows" is counts, means, variances, retrieved
examples, and human-approved text rules — all inspectable in **Insights** and per task in
**"Why this number?"**. Code: `backend/app/services/calibration.py` (pure math),
`learning.py` (DB recompute + hooks), `simulation.py`, `backtest.py`.

## 0. Principles

* **Learn against the raw LLM output.** Every AI task has an immutable `task_ai_baselines` row with
  `raw_min/raw_max` (median of K samples). All learning signals are ratios against this raw value,
  never against the calibrated number the PM saw. This keeps the problem stationary and prevents
  double counting (the system would otherwise learn its own corrections).
* **Two evidence layers**, in log space `x = ln(reference_mid / raw_mid)`, `mid = (min+max)/2`:
  * *edit layer* — reference = PM's final mid. Available at quote time. Proxy for truth.
  * *actual layer* — reference = delivered actual hours. Ground truth, available later.
* **Recompute from scratch.** Every update (`finalize`, `deliver`, manual) rebuilds all scopes from
  the full history. Updates are therefore idempotent and order-independent (tested).
* **Cold start = raw LLM** (factor 1.0, default σ² = 0.25).

## 1. When learning fires

| Trigger | Layer | What happens |
|---|---|---|
| `POST /estimates/{id}/finalize` | edit | For each enabled AI task: `x_edit = ln(final_mid/raw_mid)`. Structural signals from tasks the PM added (missing-task rate) and removed (false positives). A `calibration_runs` row snapshots the beliefs. Lessons chain proposes rules. |
| `POST /projects/{id}/deliver` | actual | For each task with actual hours: `x_actual = ln(actual/raw_mid)`. Unplanned work share is computed separately and **not** mixed into per-task error. New `calibration_runs` row, lessons chain. |

Only the latest final estimate per project is used. Intermediate flip-flopping edits are irrelevant:
the signal is `(baseline, final state)`. The event log is used for structure, reasons and audit.

## 2. Hierarchical shrinkage (§7.3)

Scopes: `global → category → category_author` (edit layer only). For a scope with `n` samples, mean
`μ`, variance `σ²`, and a parent's shrunk values:

```
μ̃  = (n·μ  + k·μ̃_parent)  / (n + k)          k = shrink_k (5)
σ̃² = (n·σ² + k·σ̃²_parent) / (n + k)          global parent: μ=0, σ²=default_sigma2 (0.25)
```

The author scope is used only when that PM has ≥ `author_min_n` (5) samples in the category.

**Combining layers** — the edit layer is the prior for the actual layer:

```
μ_pred = (n_a·μ_a + k_a·μ̃_edit) / (n_a + k_a)          k_a = actual_prior_k (4)
σ²_pred = (n_a·σ̃²_a + k_a·σ̃²_edit) / (n_a + k_a)
```

`μ_a`, `n_a` come from the category's actual-layer stats (falling back to global actual stats when
the category has no deliveries). With zero actuals the system follows PM consensus; as actuals
accumulate they dominate. σ² is floored at 0.01.

## 3. Analog blending (§7.2)

For each new task, retrieve top-`analog_top_k` similar tasks (pgvector cosine on
`title + description`) from **other projects with a final estimate**; prefer same-category analogs
when ≥ 3 exist. Analogs with similarity ≥ `sim_min` (0.75) qualify; their reference hours are
`actual` if known, else the PM's final mid. `analog_mid` = similarity-weighted median.

```
w = clamp(w_per_analog · n_eff, 0, w_max)          (0.12, 0.6)
ln(mid) = (1−w)·ln(calibrated_mid) + w·ln(analog_mid)
```

**Order of operations (avoids double counting):** calibration is applied to the *raw* mid first
(`raw_mid · exp(μ_pred)`), then the result is blended with `analog_mid`. Analog hours already
contain the historical correction, so calibrating the blend would apply the factor twice to the analog
part.

## 4. Displayed range

Lognormal quantiles around the final mid: `[mid·exp(z_low·σ), mid·exp(z_high·σ)]` with
`range_low_q/range_high_q` = P10/P90, min ≥ 0.25 h, max ≤ 20×mid, rounded to 0.5 h.
Without learning the raw LLM range is shown as-is.

## 5. Interval simulation (§7.5)

Monte Carlo (`sim_draws` = 10,000, seeded): each task draw = `mid · exp(residual)` where the
residual is sampled from the category's empirical actual-layer residual pool when `n ≥ 8`, else
`N(0, σ_task²)`. One **shared project factor** per draw (empirical pool of per-project mean residuals
when ≥ 5 delivered projects, else `N(0, sigma_proj²)`, default 0.15) captures correlated errors.
We report P10/P50/P80/P90 and a histogram; P50 and P80 are headline numbers.

Known approximation: empirical task residuals also contain part of the project effect, so with
plenty of data the spread is mildly conservative.

## 6. Clarifying questions (§7.6)

Each unknown has prior probability `p` and a scenario delta (sum of scenario task mids, calibrated
by the category's applied factor). `impact = |Δ| · 4p(1−p)` — largest when most uncertain.
Answering "yes" creates a **change proposal** with the scenario tasks (reviewable, logged).

## 7. Lessons (§7.4)

After finalize/deliver, aggregated evidence (per-category bias in both layers, most common
`reason_tag`, frequently added tasks) is sent to the Lessons chain, which proposes ≤ 5 short rules.
Rules start as `proposed`; only a human can activate them. Active rules (≤ 10, by evidence count)
are injected into decomposition/estimation prompts and the agent prompt, and listed in each task's
`provenance.rules_applied`. Rules must not contain client names; the offline fake chain builds rules
only from category names and counts.

## 8. Hyperparameters (`settings.learning`, editable in Settings)

| Key | Default | Rationale |
|---|---|---|
| `shrink_k` | 5 | ~5 samples before a category's own mean counts as much as its parent |
| `actual_prior_k` | 4 | PM consensus is worth ~4 delivered tasks |
| `default_sigma2` | 0.25 | σ≈0.5 in log space ≈ ±65% at 1σ — honest cold-start uncertainty |
| `author_min_n` | 5 | avoid personalising on noise |
| `sim_min` | 0.75 | analog similarity threshold |
| `analog_top_k` | 5 | |
| `w_per_analog`, `w_max` | 0.12, 0.6 | analogs never fully override the model |
| `range_low_q`, `range_high_q` | 0.10, 0.90 | displayed P10–P90 |
| `min_task_hours`, `max_range_multiple` | 0.25, 20 | clamps |
| `sim_draws` | 10000 | |
| `empirical_min_n` | 8 | below this, residuals are sampled from a normal |
| `project_factor_min_n`, `sigma_proj` | 5, 0.15 | shared project factor |
| `raw_samples` | 3 | K LLM samples for hours |
| `max_active_rules` | 10 | |
| `large_edit_threshold` | 0.2 | shows "Why?" chips |

## 9. Evaluation

See `backtest.py` and the Backtest page: leave-one-project-out or chronological; analog index and
statistics are rebuilt from the training projects only (a unit test fails on leakage); no LLM calls;
bootstrap CIs over projects; a small-sample warning when ≤ 20 projects.
