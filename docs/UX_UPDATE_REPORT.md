# UX update report (Prompt 6)

## Items
| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | VND default currency, USD toggle, admin FX rate, VN rate card, money parser, `fit_to_cost_budget` | Done | `tests/test_money.py` (27), `tests/test_vnd.py` (10), E2E `currency.spec.ts`, `money-utils.spec.ts` |
| 2 | Fixed-height agent panel, pinned composer, auto-scroll + Jump to latest, collapsed tool cards, drawer < 1024px | Done | E2E `layout.spec.ts` at 1440x900, 1280x720, 1024x700, 390x800 (page never scrolls, axe clean, keyboard) |
| 3 | Coloured role/category tags, central token map, per-user colours, chart colours | Done | E2E `tags-contrast.spec.ts` (>= 4.5:1), `tags.spec.ts` |
| 4 | Push + redeploy | Done | SHA `386dec0`; `/ready` = migration 0006; deploy-check 14/14; live Playwright pass (VND default, toggle persists, composer pinned at 1280x720, real-model chat edit, tags, logout) |

## Numbers
- Exchange rate: 1 USD = 25,869.40 VND, open.er-api.com, updated 19 Oct 2026 00:02 UTC (attribution shown in the UI).
- VN rate card, method, sources and assumptions (Designer rate is an assumption): `docs/RATES_VN.md`.
- Backend: 148 passed; ruff clean. Frontend: eslint, tsc clean; `make check-copy` OK. E2E: 42 passed, 2 skipped (live-only specs).
- Data proof: `docs/DATA_INVENTORY.md` (pre-prompt6 vs final6, all tables equal). Backup: `backups/calibr-pre-prompt6-20261020-013913.dump`. Migration 0006 is additive.
- LLM spend: local ledger unchanged at about USD 0.0604 (tests use the fake LLM). The live site ran several real estimates and 3 chat messages; production spend not read back (see KNOWN_ISSUES), expected a few cents.
- Landing/help screenshots regenerated with `make landing-shots`.

## Known issues
See `docs/KNOWN_ISSUES.md`. Decisions 66-73 in `docs/DECISIONS.md`.
