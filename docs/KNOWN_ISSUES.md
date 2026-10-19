# Known issues

| # | Issue | Impact | Workaround / plan |
|---|---|---|---|
| 1 | API not yet verified on Render itself. The full path was rehearsed locally with the production image (`make deploy-check` 21/21), but the Render deploy needs the owner's Render account and secrets. | Until deployed, `/api/*` on https://project-calibrate.vercel.app returns 404 and sign-in does not work. | Follow [DEPLOYMENT.md](DEPLOYMENT.md), then run `make deploy-check URL=https://project-calibrate.vercel.app`. |
| 2 | Per-user hourly rate limit and agent concurrency are counted in-process. | Correct with one API process (the Render service runs one); with several instances each would count separately. | Move counters to Postgres or Redis before scaling out. |
| 3 | Render free plan sleeps after ~15 min idle; free Postgres expires after 30 days. | First request after idle can take ~1 min; the database must be upgraded to keep data. | Paid plan, or re-create and re-seed (`SEED_ARCHIVE=true` loads the archive into an empty DB). |
| 4 | No persistent disk for uploaded originals on Render free. | Original files of uploaded briefs cannot be downloaded after a redeploy; extracted text, chunks and estimates are in Postgres and keep working. | Attach a disk (paid) or object storage. |
| 5 | `tsc` may report errors under `frontend/.next/dev/types` while a developer's own `next dev` is running. | Generated, stale type files only; `pnpm build` and `tsc` on sources pass. | Ignore, or restart the dev server. |
| 6 | Inside Docker on a network with TLS inspection, outbound HTTPS to OpenAI fails certificate verification. | Local Docker only (seen during the rehearsal); not on Render. | Mount the host CA bundle and set `SSL_CERT_FILE` for local container runs. |
| 7 | Quick sign-in (`AUTH_MODE=quick`) has no identity check by design. | Anyone who knows a member's email can open their projects; unlimited guests can be created (per-user caps reset per guest). | Total spend stays bounded by `LLM_BUDGET_USD`; switch back to `AUTH_MODE=password` when accounts are needed. |

## Prompt 6
- Live LLM spend for the post-deploy checks was not read back from the production ledger (admin password is not available to this session). Several estimate generations and three chat messages ran on the live model; expected to be a few cents, well under the USD 1.00 cap. Check Admin > Usage.
- Designer hourly rate (550.000 ₫) is an assumption (no Vietnam-specific source); see `docs/RATES_VN.md`.
- Test guest accounts/projects from the live pass remain in production.
