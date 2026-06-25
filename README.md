# MoGoStickers

Interactive Streamlit web dashboard for tracking Monopoly GO sticker ownership and coordinating
trades between members. Members sign in with Google; new members join by invite/approval.
Production: [mogostickers.streamlit.app](https://mogostickers.streamlit.app).

## Features

The app is organized into tabs (the Admin tab only appears for admins):

- **Dashboard**: At-a-glance cards — stickers you're ready to send, incoming, completed, and missing.
- **Trades**: Automatically works out who has duplicates of what others still need, grouped by
  recipient, with one-click "Mark Selected" / "Mark received".
- **Upload**: Upload album screenshots → analyzed by Gemini → **review before saving**. Also holds
  "Review Last Upload" (a durable record of what was detected) and "Manual Edit" for editing *your
  own* counts (owned + the in-game "+N" duplicates).
- **Manifest**: Read-only grid of everyone's ownership, one expander per album.
- **Admin**: Approve pending members and create invites with a pre-filled screenname.

## Architecture

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI and orchestration. |
| `db.py` | Supabase data-access layer (service-role key; bypasses RLS — RLS denies the public anon key). |
| `auth.py` | Google login gate, invite claiming, approval screens. |
| `gemini.py` | Screenshot analysis (owned + "+N" extras) and name matching. |
| `changelog.py` | Release notes that drive the "What's new" popup. |
| `migrations/` | SQL schema migrations (run in the Supabase SQL editor). |
| `scripts/migrate_ownership.py` | One-time data migration from the legacy schema. |

Data model: `profiles` (members, keyed by email, identified by a unique **screenname**),
normalized `ownership(user_id, sticker_id, owned, extras)`, `invites`, `uploads` / `upload_items`
(durable analysis records), and a private `screenshots` Storage bucket. See
[CLAUDE.md](CLAUDE.md) for the full data model, constraints, and architecture notes.

## Setup

1. **Install dependencies**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   make setup
   ```

2. **Apply the database migrations** (on a Supabase branch/copy first). The full ordered list and
   each migration's purpose live in [CLAUDE.md](CLAUDE.md#migration); the short version:
   - Run `migrations/001_normalize_and_auth.sql` in the Supabase SQL editor.
   - Run `python scripts/migrate_ownership.py` (dry run), then `--apply`.
   - After verifying totals, run the later migrations (`002`–`004`).

3. **Configure secrets**: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
   (gitignored) and fill in the Supabase service-role key, Gemini key, and the Google OAuth
   `[auth]` block. On Streamlit Cloud, paste the same into Settings → Secrets.

4. **Google OAuth**: create an OAuth client in Google Cloud Console; add the redirect URI
   (`http://localhost:8501/oauth2callback` for local, your prod URL for deploy).

## Run

```bash
make run
```

To preview locally without Google login (e.g. in the Claude Code sandbox), set the optional
`MOGO_DEV_EMAIL` key in your local `.streamlit/secrets.toml` to a real, approved member's email —
the app then auto-logs-in as that account. Keep this key out of Streamlit Cloud's secrets so
production always requires real login. See [CLAUDE.md](CLAUDE.md) for details.
