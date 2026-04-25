# Golf Match Captain — Streamlit Cloud Deployment Guide
**Verma Cup 2026 | April 2026**

---

## Prerequisites

- Access to https://github.com/PXLabs/golf-match-captain (private repo)
- Streamlit Community Cloud account — sign in at [share.streamlit.io](https://share.streamlit.io) using the GitHub account that has access to PXLabs
- Your Anthropic API key (`sk-ant-...`)

---

## Step 1 — Push the repo to GitHub

```bash
cd "Golf App/golf_match_captain"
git add .
git commit -m "Add Streamlit Cloud config — Verma Cup 2026"
git push origin main
```

> **Check before pushing:** run `git status` and confirm `.streamlit/secrets.toml` is NOT listed.
> The `.gitignore` excludes it, but always verify before a push.

---

## Step 2 — Create the app on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with the PXLabs GitHub account
2. Click **New app**
3. Set the fields as follows:

| Field | Value |
|---|---|
| Repository | `PXLabs/golf-match-captain` |
| Branch | `main` |
| Main file path | `app.py` |
| App URL (optional) | e.g. `verma-golf-captain` |

4. Click **Deploy** — Streamlit installs `requirements.txt` and boots the app (~2 mins)

---

## Step 3 — Add secrets in Streamlit Cloud

**Do this before anyone uses the app.** The AI Advisor and Scorecard pages will error without the API key.

1. In your app dashboard, click **⋮ → Settings → Secrets**
2. Paste the following with your real values:

```toml
ANTHROPIC_API_KEY = "sk-ant-YOUR_REAL_KEY_HERE"
SCOREBOARD_PASSWORD = ""
```

3. Click **Save** — the app restarts automatically

---

## Step 4 — Verify the deployment

Check these pages load without errors:

- [ ] Dashboard (home) — welcome screen loads
- [ ] Roster Manager — no database error
- [ ] Course Library — loads
- [ ] Event Setup — loads
- [ ] Match Analysis — loads
- [ ] Results — loads
- [ ] Scoreboard — loads

---

## Step 5 — Set up event data before May 2

Once deployed, configure the Verma Cup event in GMC:

1. **Roster Manager** — add all 12 players with their handicap indices (from CONTEXT.md Section 4)
2. **Course Library** — add the 6 official courses (Ballyliffin Glashedy, Ballyliffin Old, Rosapenna Sandy Hills, Cruit Island, Portsalon, Rosapenna St Patricks)
3. **Event Setup** — create the Verma Cup 2026 event, assign teams, configure the 7 rounds
4. **Admin → Download Snapshot** — take a backup once setup is complete (see below)

---

## Database Backup & Restore (important for the trip)

GMC uses SQLite stored at `data/golf_captain.db`. On Streamlit Community Cloud the database **resets if the app container restarts** from scratch (e.g. after a new deployment or extended inactivity).

**The Admin page (sidebar → ⚙️ Admin & Archive) already has full backup and restore built in:**

### Daily backup routine (before each round)
1. Open GMC → **⚙️ Admin & Archive**
2. Section **💾 Database Archive Restore** → click **⬇️ Download golf_captain.db**
3. Save the file locally (or to OneDrive) — name it with the date e.g. `golf_captain_backup_20260503.db`

### If the database resets
1. Open GMC → **⚙️ Admin & Archive**
2. Section **💾 Database Archive Restore** → upload your most recent `.db` backup file
3. Click **⚠️ Restore Database File** — the app reloads with your data restored

**Rule: download a backup every morning before setting pairings. Takes 10 seconds.**

---

## Do NOT redeploy during the trip (May 2–9)

A new deployment resets the container. If you must push a fix during the trip:
1. Download a database backup first
2. Push the fix
3. Restore the backup immediately after the app reboots

---

## Step 6 — Share the URL

Share the private Streamlit URL with Peter Callahan and Bill Stanton only.
URL format: `https://verma-golf-captain.streamlit.app`

---

## Next steps after GMC is live

| Step | Task |
|---|---|
| 1 | Provision Supabase — run `verma-shared/superbase/verma_cup_schema.sql` then `verma_cup_seed_data.sql` |
| 2 | Add `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY` to Streamlit secrets and Vercel env vars |
| 3 | Build GMC Supabase module — Publish Pairings + Lock Round |
| 4 | Build GMC Sync Results function |
| 5 | Build Weather App Scoreboard tab |
| 6 | Build Verma Scoring App (photo scan → review → tally) |
