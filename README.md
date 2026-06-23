# MoGoStickers

Interactive Streamlit web dashboard for tracking Monopoly GO sticker ownership and coordinating
trades between members. Members sign in with Google; new members join by invite/approval.
Production: [mogostickers.streamlit.app](https://mogostickers.streamlit.app).

## Features

- **Login**: Google sign-in with persistent auto-login (Streamlit native OIDC auth).
- **Dashboard**: Your ready-to-send, incoming, completed, and missing stickers.
- **Trades**: Automatically calculates who has duplicates of what others still need.
- **Collection**: Browse every set; edit *your own* ownership (own + the in-game "+N" duplicates).
- **Audit**: Upload album screenshots → analyzed by Gemini → **review before saving**, plus a
  durable "Review Last Upload" view showing exactly what was detected and why.
- **Admin**: Approve pending members and create invites with a pre-filled screenname.
- **History & Rollbacks**: Revert ownership to a previous state.

## Architecture

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI and orchestration. |
| `db.py` | Supabase data-access layer (service-role key, RLS-protected). |
| `auth.py` | Google login gate, invite claiming, approval screens. |
| `gemini.py` | Screenshot analysis (owned + "+N" extras) and name matching. |
| `migrations/` | SQL schema migrations (run in the Supabase SQL editor). |
| `scripts/migrate_ownership.py` | One-time data migration from the legacy schema. |

Data model: `profiles` (members, keyed by email, identified by unique **screenname**),
normalized `ownership(user_id, sticker_id, owned, extras)`, `invites`, `uploads` / `upload_items`
(durable analysis records), and a private `screenshots` Storage bucket.

## Setup

1. **Install dependencies**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   make setup
   ```

2. **Apply the database migrations** (on a Supabase branch/copy first):
   - Run `migrations/001_normalize_and_auth.sql` in the Supabase SQL editor.
   - Set env vars and run `python scripts/migrate_ownership.py` (dry run), then `--apply`.
   - After verifying totals, run `migrations/002_drop_legacy.sql`.

3. **Configure secrets**: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
   (gitignored) and fill in Supabase service-role key, Gemini key, and the Google OAuth
   `[auth]` block. On Streamlit Cloud, paste the same into Settings → Secrets.

4. **Google OAuth**: create an OAuth client in Google Cloud Console; add the redirect URI
   (`http://localhost:8501/oauth2callback` for local, your prod URL for deploy).

## Run

```bash
make run
```
