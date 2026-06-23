# Codex Guide

## Project Purpose

Tracks Monopoly GO sticker ownership and trades for a group of members who sign in with Google.
Members are identified by a unique **screenname** (decoupled from their login email/real name).
Production: [mogostickers.streamlit.app](https://mogostickers.streamlit.app).

## Important Files

- `app.py`: Streamlit UI + orchestration.
- `db.py`: Supabase data-access layer (uses the service-role key; RLS denies the anon key).
- `auth.py`: Google login gate, invite claiming, approval screens.
- `gemini.py`: Screenshot analysis + name matching.
- `migrations/`: SQL schema migrations. `scripts/migrate_ownership.py`: one-time data migration.

## Data model

- `profiles(id, email, screenname, real_name, emoji, color, is_admin, approved)`.
- `ownership(user_id, sticker_id, owned, extras)` — normalized, one row per (user, sticker).
  `owned` = has the sticker; `extras` = the in-game "+N" duplicates. Total = `owned ? 1 + extras : 0`
  (use `db.total_for`). There are NO per-user columns anymore.
- `invites`, `uploads`, `upload_items`; screenshots live in the private `screenshots` Storage bucket.

## Commands

```bash
make syntax   # python syntax check
make run      # start the Streamlit app
```

## Coding Notes

- Keep the Streamlit UI premium and fast.
- Never hard-code API keys; use Streamlit secrets / env (service-role key stays server-side).
- A user may only edit their OWN ownership rows.
- Screenshot uploads are **review-before-commit**: analyze, show the user, save only on confirm.
- Safeguard: do not silently flip a known `owned=true` to `owned=false` during an upload.
- Report the in-game "+N" directly into `extras`; never convert to a total in the prompt.
- Simple, clean, well-commented functions are preferred.
