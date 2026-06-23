# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make setup    # install dependencies into .venv
make syntax   # compile-check app.py only
make run      # streamlit run app.py (uses .venv/bin/python if present)
```

**Preview** (Claude Code desktop): uses `.claude/launch.json` + `/tmp/mogo_launch.py`. The preview sandbox blocks `os.getcwd()` and file access to `~/Documents`, so the launcher copies app files to `/tmp/mogostickers/` and monkey-patches the blocked syscalls. After editing source files, resync the copy before reloading the preview:

```bash
cp app.py db.py auth.py gemini.py /tmp/mogostickers/
```

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

## Key Constraints

- A user may only write `ownership` rows where `user_id == current_user["id"]`.
- Never silently flip `owned=True → False` during an upload review; require explicit user action.
- `gemini.py` reports the "+N" badge directly as `extras`; the prompt must not say "convert to a total."
- `db.py` uses `urllib` (stdlib only) — no `requests`/`httpx`.
- Stickers cache lives in `st.session_state.stickers_cache`; call `db._invalidate_sticker_cache()` after any ownership write.
- Gold stickers show a 🔒 in the Trades tab (not checkboxable — manual trade only).
- Recipients need ≥ 10 owned stickers before they appear as trade targets (cuts noise for new users).

## Secrets / Config

All credentials go in `.streamlit/secrets.toml` (gitignored). Required keys: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GEMINI_API_KEY`. Optional: `GEMINI_MODEL` (default `gemini-3.1-flash-lite`). The `[auth]` + `[auth.google]` blocks configure OIDC. See `.streamlit/secrets.toml.example`.

## Migration

Schema migrations live in `migrations/`. Run order: `001_normalize_and_auth.sql` → `scripts/migrate_ownership.py --apply` → `002_drop_legacy.sql`. Never run on prod without testing on a Supabase branch first.
