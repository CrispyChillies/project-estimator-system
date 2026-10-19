# Data inventory

All existing data is preserved. Before any Prompt-5 schema change a full dump was taken:
`backups/calibr-pre-prompt5-*.dump` (`pg_dump -Fc`, gitignored, kept on disk; restore with
`pg_restore -d calibr --clean <file>` only if ever needed).

Row counts are produced by `backend/scripts/data_inventory.py snapshot <label>` (JSON in `data/inventory/`)
and compared with `... compare <before> <after>` (exit 1 if any table shrank).

## Before Prompt 5 (`pre-prompt5`)

| table | rows |
|---|---:|
| agent_messages | 10 |
| agent_operations | 2 |
| agent_sessions | 6 |
| alembic_version | 1 |
| assumptions | 148 |
| backtest_results | 8988 |
| backtest_runs | 4 |
| calibration_runs | 60 |
| calibration_stats | 63 |
| change_proposals | 2 |
| clarifying_questions | 29 |
| delivery_roles | 9 |
| document_chunks | 27 |
| documents | 27 |
| edit_events | 377 |
| estimates | 28 |
| jobs | 12 |
| learned_rules | 5 |
| llm_calls | 159 |
| llm_raw_estimates | 1722 |
| modules | 220 |
| project_embeddings | 24 |
| project_memories | 0 |
| projects | 28 |
| retrieval_logs | 1 |
| settings | 2 |
| task_actuals | 454 |
| task_ai_baselines | 572 |
| task_categories | 16 |
| tasks | 581 |
| unplanned_actuals | 44 |
| users | 4 |

## After migration 0004 (accounts) — `post-accounts`

All tables unchanged or larger (`users` +1: the admin). New empty tables: `sessions`, `project_members`,
`login_attempts`, `password_resets`.

Incident (recovered): a test server started with `LLM_MODE=fake` against the dev database recomputed
`calibration_stats` for the fake model key (63 → 0 rows). These rows are derived data; they were recomputed from the
preserved edit/actual records for the real model key (back to 63, check snapshot `check2`), and startup now refuses to
replace stored stats with empty ones. No source data (projects, edits, actuals, documents) was affected.

## End of Prompt 5 — `final` (dev database `calibr`)

`python -m scripts.data_inventory compare pre-prompt5 final`: **no table lost rows.** Changes vs the backup
snapshot: `users` 4 → 5 (the admin account), `calibration_runs` 60 → 64 (append-only recomputation log), new
empty tables `sessions`, `login_attempts`, `password_resets`, `project_members`. All other tables are
identical in count (projects 28, estimates 28, tasks 581, task_actuals 454, edit_events 377, backtest_results
8988, llm_calls 159, …). Snapshot: `data/inventory/final.json`.

The deployment copy of this data is `deploy/seed/admin_archive.sql.gz` (built from a scratch copy, password
hashes removed, not committed) — see [DEPLOYMENT.md](DEPLOYMENT.md#the-admin-archive-your-existing-test-data).
