# Golf Match Captain — Deployment Guide
**Verma Cup 2026 | April 2026**

---

## Architecture Summary

GMC now uses **Supabase PostgreSQL** as its database — not SQLite. This means:

- Data **persists permanently** even when Streamlit Cloud restarts or redeploys
- No more manual backup/restore routine before each round
- No more "Quick Load" button needed
- The schema lives in Supabase; GMC connects via `psycopg2`

---

## Prerequisites

- Access to https://github.com/PXLabs/golf-match-captain (private repo)
- Streamlit Community Cloud account — sign in at [share.streamlit.io](https://share.streamlit.io)
- Anthropic API key (`sk-ant-...`)
- Supabase project credentials (see Step 1)

---

## Step 1 — Set up the Supabase database

### 1a. Create the schema

1. Go to your Supabase project → **SQL Editor**
2. Open the file `database/schema_supabase.sql` from this repo
3. Paste the full contents into the SQL Editor and click **Run**
4. You should see 9 tables created with no errors: `player`, `score_record`, `player_tag`, `course`, `tee_deck`, `event`, `event_player`, `round`, `match`

### 1b. Get the connection string

1. In Supabase → **Project Settings → Database → Connection string**
2. Choose **Session mode** (not Transaction mode)
3. Copy the URI — it looks like:
   ```
   postgresql://postgres.YOURREF:PASSWORD@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
   ```
4. Keep this — you'll need it for Streamlit secrets

---

## Step 2 — Push the repo to GitHub

```bash
cd "Golf App/golf_match_captain"
git add .
git commit -m "Migrate to Supabase PostgreSQL — Verma Cup 2026"
git push origin main
```

> **Check before pushing:** run `git status` and confirm `.streamlit/secrets.toml` is NOT listed.
> The `.gitignore` excludes it, but always verify before a push.

---

## Step 3 — Create the app on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in
2. Click **New app**
3. Fill in:

| Field | Value |
|---|---|
| Repository | `PXLabs/golf-match-captain` |
| Branch | `main` |
| Main file path | `app.py` |
| App URL (optional) | e.g. `verma-golf-captain` |

4. Click **Deploy** — Streamlit installs `requirements.txt` (~2 mins)

---

## Step 4 — Add secrets in Streamlit Cloud

**Do this before first use.** The app will error without these.

1. In your app dashboard, click **⋮ → Settings → Secrets**
2. Paste the following, replacing each placeholder with your real values:

```toml
ANTHROPIC_API_KEY    = "sk-ant-YOUR_KEY_HERE"
SUPABASE_URL         = "https://YOURREF.supabase.co"
SUPABASE_SERVICE_KEY = "eyYOUR_SERVICE_ROLE_KEY"
SUPABASE_DB_URL      = "postgresql://postgres.YOURREF:PASSWORD@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
SCOREBOARD_PASSWORD  = ""
```

- `SUPABASE_DB_URL` — the Session pooler URI from Step 1b
- `SUPABASE_SERVICE_KEY` — from Supabase → Project Settings → API → **service_role** key (not anon)
- `SUPABASE_URL` — from Supabase → Project Settings → API → Project URL

3. Click **Save** — the app restarts automatically

---

## Step 5 — Seed the Verma Cup data

On first launch, the Supabase database will be empty. You need to load the event data once:

1. Open GMC → **⚙️ Admin & Archive** (sidebar)
2. Find the **Load Verma Cup 2026** section
3. Click **🏆 Load Verma Cup 2026 Data**

This populates: 12 players, 7 courses + 2 extra courses, the Verma Cup event, and all 7 rounds.

> **This only needs to be done once.** Data now lives in Supabase — it survives restarts, redeployments, and inactivity.

---

## Step 6 — Verify the deployment

Check these pages load without errors:

- [ ] Dashboard — event summary shows Verma Cup 2026
- [ ] Roster Manager — 12 players listed
- [ ] Course Library — 9 courses listed
- [ ] Event Setup — Verma Cup 2026 active, 6 players per team
- [ ] Match Analysis — AI Advisor loads
- [ ] Results — round tabs visible
- [ ] Scoreboard — loads

---

## Step 7 — Add Round 1 pairings

Before May 2:

1. **Results** page → **R1 tab** → add the 6v6 draw for the warm-up round
2. Click **Publish to Supabase** to lock the round and make it visible in the scoring app

---

## Database — no backup needed

Because data is now stored in Supabase PostgreSQL (not on the Streamlit container), you **do not need to take manual database backups**. The data persists regardless of what happens to the Streamlit app container.

If you ever need to reset and re-seed (e.g. to correct a mistake):

1. Go to Admin → Load Verma Cup 2026 → check **"Clear existing data first"**
2. Click **Load** — this wipes all GMC data in Supabase and re-seeds from scratch

> Note: this will clear match results too. Only do this before any rounds have been played.

---

## Redeploying during the trip (May 2–9)

You can now redeploy safely at any time — the database is on Supabase, not the container. No backup step needed before pushing a fix.

---

## Step 8 — Share the URL

Share the Streamlit URL with Peter Callahan and Bill Stanton only.
URL format: `https://verma-golf-captain.streamlit.app`
