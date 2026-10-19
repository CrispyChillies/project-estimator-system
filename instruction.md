# Setup instructions: deploy the Calibr backend on Render

Frontend (already live): https://project-calibrate.vercel.app
Backend + database: Render (this guide). Config file: `render.yaml`.

## 0. What you need

- A GitHub account with access to `CrispyChillies/project-estimator-system`
- A Render account (https://render.com, sign in with GitHub)
- An OpenAI API key
- Choose an admin email and an admin password (10+ characters)

## 1. Push the code to GitHub

```bash
cd ~/project-estimator-system
git push origin main
```

## 2. Create the services on Render

1. Open https://dashboard.render.com
2. **New → Blueprint**
3. Connect GitHub if asked, then pick `project-estimator-system`
4. Render reads `render.yaml` and shows:
   - Web service `project-calibrate-api`
   - Database `project-calibrate-db`
5. Fill in the 3 secrets it asks for:

   | Name | Value |
   |---|---|
   | `OPENAI_API_KEY` | your OpenAI key |
   | `ADMIN_EMAIL` | your admin email |
   | `ADMIN_PASSWORD` | 10+ characters |

6. Click **Apply** and wait for the first build (about 5-10 minutes).

Everything else is preset in `render.yaml` (model, $3 total spend cap, quick sign-in for users, generated `SESSION_SECRET`). On start the service creates the database tables and your admin account by itself.

## 3. Check the API URL

Open `project-calibrate-api` in Render and read its URL at the top.

- If it is exactly `https://project-calibrate-api.onrender.com`, go to step 4.
- If it has a suffix (for example `https://project-calibrate-api-ab12.onrender.com`), update Vercel:

```bash
cd ~/project-estimator-system/frontend
npx vercel env rm BACKEND_URL production -y
printf "https://<your-render-url>" | npx vercel env add BACKEND_URL production
npx vercel deploy --prod --yes
```

Also update `PUBLIC_APP_URL`/`CORS_ORIGINS` on Render only if the Vercel address ever changes.

## 4. Test

```bash
curl https://project-calibrate-api.onrender.com/health      # returns JSON with a status field
make deploy-check URL=https://project-calibrate.vercel.app
```

Then open https://project-calibrate.vercel.app, click **Get started**, enter a name, **Continue**.

The free plan sleeps after about 15 minutes idle; the first request after that can take about a minute.

## 5. (Optional) Load your existing test data

The dump `deploy/seed/admin_archive.sql.gz` is not on GitHub (public repo). It is only on your machine. To rebuild it from your local database: `make admin-archive`.

1. Render → `project-calibrate-db` → **Connect → External Database URL** → copy it (do not commit or share it).
2. Run:

```bash
cd ~/project-estimator-system
DATABASE_URL='<External Database URL>' ADMIN_EMAIL='<same ADMIN_EMAIL as on Render>' scripts/restore_admin_archive.sh
```

   It only loads when the database has no projects, so running it twice is safe.
3. Render → `project-calibrate-api` → **Manual Deploy → Restart service**.
4. Sign in as admin: on the sign-in page click "Administrator? Sign in with a password".
5. To let everyone's estimates learn from this data: **Admin → Data archive → include archive for all**.

## Database notes

- Render Postgres 16 with pgvector; the API enables the extension and creates/upgrades tables on every start (changes only add, never delete).
- Free database: 1 GB, **deleted after 30 days** unless upgraded. Upgrade to a paid plan (or use Neon/Supabase and paste its URL into `DATABASE_URL` on the service) to keep data.
- Backups: paid plans only.

## Switching back to real accounts

On the Render service, set `AUTH_MODE=password`, `SIGNUP_MODE=invite` and `INVITE_CODE` (8+ characters), then redeploy.

## Troubleshooting

| Problem | Fix |
|---|---|
| Sign-in page says "Can't reach the server" | API is asleep or not deployed; wait a minute, check Render logs. |
| Service fails on start with "Invalid configuration" | A required variable is missing (`OPENAI_API_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`); the log lists which. |
| `/api/v1/health` on the Vercel URL returns 404 | `BACKEND_URL` on Vercel is wrong or the frontend was not redeployed after changing it. |
| AI calls fail with 429 | A spend or rate cap was reached (`LLM_BUDGET_USD`, `USER_DAILY_USD_CAP`). |

More detail: `docs/DEPLOYMENT.md`.
