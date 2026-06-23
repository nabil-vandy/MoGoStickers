# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make setup    # install dependencies into .venv
make syntax   # compile-check app.py only
make run      # streamlit run app.py (uses .venv/bin/python if present)
```

**Preview** (Claude Code desktop): uses `.claude/launch.json` + `.claude/run_app.sh`. The preview sandbox blocks `os.getcwd()` and file access to `~/Documents`, so the launcher copies app files to `/tmp/mogostickers/` and monkey-patches the blocked syscalls. After editing source files, resync the copy before reloading the preview:

```bash
cp app.py db.py auth.py gemini.py /tmp/mogostickers/
```

Note: the Claude preview cannot complete Google OIDC login (sandbox blocks the OAuth redirect). Use the live site at https://mogostickers.streamlit.app/ for end-to-end auth testing.

## Architecture

Four Python files; no framework besides Streamlit.

| File | Role |
|------|------|
| `app.py` | All UI (tabs, widgets, event handlers). Auth gate runs at the top, then the full page renders per `st.session_state.active_tab`. |
| `db.py` | Supabase REST + Storage calls via `urllib`. No ORM. Uses the **service-role key** (bypasses RLS). |
| `auth.py` | Streamlit-native OIDC gate (`st.login`/`st.user`/`st.logout`). Handles invite-claiming and pending-approval screens. |
| `gemini.py` | Screenshot analysis: sends image + reference JSON → Pydantic schema → name matching (`difflib`). |

`app.py` imports `auth`, `db`, `gemini`; the other three are self-contained.

## Data Model

**Ownership** is `(user_id uuid, sticker_id bigint, owned bool, extras int)` with `UNIQUE(user_id, sticker_id)`. `owned` = has the sticker; `extras` = the in-game "+N" badge. Total = `db.total_for(owned, extras)` = `(1 + extras) if owned else 0`. Never store or derive a raw total.

**Profiles** hold `(id, email, screenname, emoji, color, is_admin, approved)`. The `screenname` is the sole display identity across all UI — email is only for login matching, never shown.

**Upload flow**: analyze → store raw JSON in `uploads.raw_response` + per-sticker rows in `upload_items` → show `st.data_editor` review panel → only write `ownership` on Confirm. Never write on analyze.

**Database tables**: `stickers`, `profiles`, `invites`, `ownership`, `uploads`, `upload_items`, `database_history`. Screenshots persist in the private Supabase Storage bucket `screenshots/`.

`ownership_legacy` still exists in the DB (renamed from `ownership` during migration 001). Drop it only after verifying sticker totals in the live app, then run `migrations/002_drop_legacy.sql`.

## Key Constraints

- A user may only write `ownership` rows where `user_id == current_user["id"]`.
- Never silently flip `owned=True → False` during an upload review; require explicit user action.
- `gemini.py` reports the "+N" badge directly as `extras`; the prompt must not say "convert to a total."
- `db.py` uses `urllib` (stdlib only) — no `requests`/`httpx`.
- Stickers cache lives in `st.session_state.stickers_cache`; call `db._invalidate_sticker_cache()` after any ownership write.
- Gold stickers show a 🔒 in the Trades tab (not checkboxable — manual trade only).
- Recipients need ≥ 10 owned stickers before they appear as trade targets (cuts noise for new users).

## Secrets / Config

All credentials go in `.streamlit/secrets.toml` (gitignored). On Streamlit Cloud, paste the same content into **Settings → Secrets**.

Required keys: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GEMINI_API_KEY`. Optional: `GEMINI_MODEL` (default `gemini-3.1-flash-lite`). The `[auth]` + `[auth.google]` blocks configure OIDC. See `.streamlit/secrets.toml.example`.

**Key name**: `db.py` reads `SUPABASE_SERVICE_KEY` (falling back to `SUPABASE_KEY` for backwards-compat). Always use `SUPABASE_SERVICE_KEY` in new config.

**OAuth redirect URI**: the Google Cloud Console client must have `https://mogostickers.streamlit.app/oauth2callback` as an authorized redirect URI (Streamlit appends `/oauth2callback`, not just `/`).

## Deployment

Auto-deploys from GitHub `nabil-vandy/MoGoStickers` (branch `main`) to https://mogostickers.streamlit.app/ via Streamlit Cloud. Push to `main` to deploy.

## Migration

Schema migrations live in `migrations/`. Run order: `001_normalize_and_auth.sql` (in the Supabase SQL editor) → `scripts/migrate_ownership.py --apply` → `002_drop_legacy.sql`. Never run on prod without testing on a Supabase branch first.

A pre-go-live DB snapshot lives in `backups/20260622-191721-prelive/` with a `restore.py` script. Git tag `prelive-savepoint-20260622` marks the code at that point.
