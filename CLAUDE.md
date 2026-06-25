# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make setup    # install dependencies into .venv
make syntax   # compile-check app.py only
make run      # streamlit run app.py (uses .venv/bin/python if present)

# compile-check all source files
python -m py_compile app.py db.py auth.py gemini.py
```

**Preview** (Claude Code desktop): uses `.claude/launch.json` + a launcher that copies app files to `/tmp/mogostickers/` and monkey-patches syscalls blocked by the preview sandbox (`os.getcwd()`, file access to `~/Documents`). After editing source files, resync the copy before reloading the preview:

```bash
cp app.py db.py auth.py gemini.py changelog.py /tmp/mogostickers/
```

Note: the Claude preview cannot complete Google OIDC login (sandbox blocks the OAuth redirect). Use the live site at https://mogostickers.streamlit.app/ for end-to-end auth testing.

## Architecture

Four Python files; no framework besides Streamlit.

| File | Role |
|------|------|
| `app.py` | All UI (tabs, widgets, event handlers). Auth gate runs at the top, then the full page renders per `st.session_state.active_tab`. |
| `db.py` | Supabase REST + Storage calls via `urllib`. No ORM. Uses the **service-role key** (bypasses RLS). |
| `auth.py` | Streamlit-native OIDC gate (`st.login`/`st.user`/`st.logout`). Handles invite-claiming and pending-approval screens. |
| `gemini.py` | Screenshot analysis: crop → send image + reference JSON → Pydantic schema → name matching (`difflib`). |

`app.py` imports `auth`, `db`, `gemini`; the other three are self-contained.

### Navigation & page flow

`app.py` is one top-to-bottom script — there is no router. After the auth gate, a sidebar renders nav buttons and the page body is a single `if/elif` chain on `st.session_state.active_tab`. The active tab is also mirrored to the `?tab=` query param so links and deep-links work. `TABS = ["Dashboard", "Trades", "Upload", "Manifest"]` (+ `"Admin"` when `current_user["is_admin"]`); the list order **is** the on-screen order, and `tab_icons` maps each to its emoji.

| Tab | Renders |
|-----|---------|
| **📊 Dashboard** | Greeting + four metric cards (ready-to-send, pending, completed, missing). Cards are `<a href="/?tab=...">` deep-links. "Ready to Send" counts distinct **non-gold** stickers only. |
| **⚡ Trades** ("Trade Center") | `find_trade_rows(stickers, pool)` output. **👯 Send to friends** is grouped by recipient (checkboxes → Mark Selected; gold renders a 🔒, manual-only). **📥 Expected to receive** lists what friends can send *you*, each with a checkbox → **✅ Mark received**, which sets *your* ownership to owned (extras unchanged) so you drop off every sender's list. Senders' counts are intentionally left alone — they self-correct on their next upload. |
| **🔍 Upload** ("Upload Center") | `st.radio` sub-tabs: **Upload Screenshots** (parallel analyze → changed-only review panel → batch commit), **Review Last Upload** (durable per-upload audit), **Manual Edit** (per-user owned/extras editor with Undo / Confirm & Commit). |
| **📁 Manifest** | Read-only ownership grid across all pool members, one expander per album. No editing here. |
| **🛠️ Admin** | Pending approvals + invite creation only. (Per-player profile editing was removed in v3.2.0.) |

Editing your own counts lives **only** in Upload → Manual Edit. The Manifest tab is view-only. When adding a tab, update `TABS`, `tab_icons`, and add the matching `elif` block. Page titles use the shared `page_header(title, subtitle)` helper so every tab's header matches.

### Identity: real vs. acting user (v3.2.0)

`real_user` (= `auth.require_auth()`) is always the logged-in account — it drives Admin-tab access and the changelog popup. The **acting** identity (`my_id` / `my_name`) is normally the same, but an admin can impersonate any player via the sidebar **"Viewing as"** switcher (`st.session_state.act_as_id`). When impersonating, `my_id` is the selected player and **all reads and writes** (dashboard, trades, manual edits, uploads, Review Last Upload) act on that player's account; a 🔭 banner shows at the top. Impersonation is honored only when `real_user["is_admin"]`. `my_id`/`my_name` are assigned **after** the sidebar renders (the switcher sets them).

### Changelog popup (v3.2.0)

`changelog.py` holds a newest-first list of releases (the only reliable source — Streamlit Cloud has no git). On load, if `changelog.entries_since(real_user["last_seen_changelog"])` is non-empty, a `@st.dialog` "What's new" modal shows the combined unseen changes; **Got it** calls `db.mark_changelog_seen(real_id, changelog.latest_id())`. Dismissal persists per-user (profiles column `last_seen_changelog`, migration 004) until a newer entry ships. Brand-new accounts (no marker) are silently marked caught-up. The popup is keyed to `real_user`, never the impersonated one. Bump `changelog.CHANGELOG` + the app version when shipping user-facing changes.

### Upload flow (v3.1.1)

Screenshots are processed in parallel via `ThreadPoolExecutor` (up to 8 workers). Each worker:
1. Calls `gemini.crop_screenshot(bytes, mime)` — strips top 9% / bottom 15% (game UI chrome)
2. Uploads the cropped bytes to Supabase Storage (`db.upload_screenshot`)
3. Calls `gemini.analyze` (Gemini API, one call per image)
4. Runs `gemini.match` for each detected sticker (local fuzzy match, safe to call from threads)

Workers return their rows to the main thread; never touch `st.session_state`. The Streamlit script context is attached to worker threads via `add_script_run_ctx` so `st.error` stays valid inside `db._request`.

The review panel shows **only rows whose count changed** vs. the previous upload, sorted ascending by `matched_sticker_id` (MoGo_ID order). Commit uses `db.upsert_ownership_bulk` (single HTTP POST array) instead of one call per sticker.

### Set numbering

Albums are numbered 1–N by their lowest sticker id (`set_number_by_album` dict, built at startup in `app.py`). Sets 1–21 are the regular collection (`REGULAR_SET_MAX = 21`); sets 22+ are Bonus Sets, and only the one with the highest number (`current_bonus_album`) is treated as the "current" bonus. The Upload heading is group-wide (`group_sets_needing_upload` checks all pool members, not just the current user) so it reads the same for everyone.

## Data Model

**Ownership** is `(user_id uuid, sticker_id bigint, owned bool, extras int)` with `UNIQUE(user_id, sticker_id)`. `owned` = has the sticker; `extras` = the in-game "+N" badge. Total = `db.total_for(owned, extras)` = `(1 + extras) if owned else 0`. Never store or derive a raw total.

**Profiles** hold `(id, email, screenname, emoji, color, is_admin, approved)`. The `screenname` is the sole display identity across all UI — email is only for login matching, never shown. Screennames are managed by admins via the Admin tab; there is no self-serve rename for regular users.

**Upload flow**: analyze → store raw JSON in `uploads.raw_response` + per-sticker rows in `upload_items` → show `st.data_editor` review panel (changed rows only) → only write `ownership` on Confirm. Never write on analyze.

**Database tables**: `stickers`, `profiles`, `invites`, `ownership`, `uploads`, `upload_items`, `database_history`. Screenshots persist in the private Supabase Storage bucket `screenshots/`.

`database_history`: every ownership-mutating action (trades, manual edits, upload commits) first calls `db.log_history(...)` to snapshot state. The user-facing History & Rollbacks UI was removed in v3.0.2, so `db.fetch_history()` / `db.apply_rollback()` still exist but are currently unreferenced.

`ownership_legacy` still exists in the DB (renamed from `ownership` during migration 001). Drop it only after verifying sticker totals in the live app, then run `migrations/002_drop_legacy.sql`.

## Key Constraints

- A user may only write `ownership` rows where `user_id == current_user["id"]`.
- Never silently flip `owned=True → False` during an upload review; require explicit user action.
- `gemini.py` reports the "+N" badge directly as `extras`; the prompt must not say "convert to a total."
- `db.py` uses `urllib` (stdlib only) — no `requests`/`httpx`. Each `_request()` call opens a fresh connection (no pooling).
- Stickers cache lives in `st.session_state.stickers_cache`; call `db._invalidate_sticker_cache()` after any ownership write. The bulk helper `db.upsert_ownership_bulk` does this once for the whole batch.
- Gold stickers show a 🔒 in the Trades tab (not checkboxable — manual trade only) and are excluded from the "Ready to Send" dashboard count.
- Recipients need ≥ 10 owned stickers before they appear as trade targets (cuts noise for new users).
- Upload workers must not touch `st.session_state` — collect results and merge on the main thread only.

## Secrets / Config

All credentials go in `.streamlit/secrets.toml` (gitignored). On Streamlit Cloud, paste the same content into **Settings → Secrets**.

Required keys: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GEMINI_API_KEY`. Optional: `GEMINI_MODEL` (default `gemini-3.1-flash-lite`). The `[auth]` + `[auth.google]` blocks configure OIDC. See `.streamlit/secrets.toml.example`.

**Key name**: `db.py` reads `SUPABASE_SERVICE_KEY` (falling back to `SUPABASE_KEY` for backwards-compat). Always use `SUPABASE_SERVICE_KEY` in new config.

**OAuth redirect URI**: the Google Cloud Console client must have `https://mogostickers.streamlit.app/oauth2callback` as an authorized redirect URI (Streamlit appends `/oauth2callback`, not just `/`).

## Deployment

Auto-deploys from GitHub `nabil-vandy/MoGoStickers` (branch `main`) to https://mogostickers.streamlit.app/ via Streamlit Cloud. Push to `main` to deploy. Current version: **v3.2.0**.

## Migration

Schema migrations live in `migrations/`. Run order:
1. `001_normalize_and_auth.sql` — in the Supabase SQL editor
2. `scripts/migrate_ownership.py --apply` — seeds profiles + copies data from the legacy table
3. `002_drop_legacy.sql` — only after verifying sticker totals on the live app
4. `003_history_user_profile_nullable.sql` — makes `database_history.user_profile` nullable (required for `log_history()` which no longer writes that column)
5. `004_profile_last_seen_changelog.sql` — adds `profiles.last_seen_changelog` (text) for the changelog popup. Run before v3.2.0 traffic, or `db.mark_changelog_seen()` PATCHes fail-soft and the popup reappears each load.

Never run on prod without testing on a Supabase branch first.

A pre-go-live DB snapshot lives in `backups/20260622-191721-prelive/` with a `restore.py` script. Git tag `prelive-savepoint-20260622` marks the code at that point.
