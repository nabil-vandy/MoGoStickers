-- ============================================================================
-- MoGoStickers — Migration 001: normalize ownership + add auth/upload tables
-- ============================================================================
-- WHAT THIS DOES
--   * Renames the legacy per-user `ownership(sticker_id, hana, jon, nabil)` table
--     to `ownership_legacy` (data preserved, nothing dropped).
--   * Creates a normalized `ownership(user_id, sticker_id, owned, extras)` table.
--   * Adds `profiles` (real users w/ screennames), `invites`, `uploads`,
--     `upload_items`, and a `user_id` column on `database_history`.
--   * Enables Row-Level Security so the public/anon key alone grants NOTHING.
--     The app connects with the Supabase service-role key (which bypasses RLS),
--     so no permissive policies are needed.
--
-- HOW TO RUN (do this on a Supabase BRANCH / copy first — never prod first):
--   1. Run this file in the Supabase SQL editor.
--   2. Run `python scripts/migrate_ownership.py` to seed profiles + copy data.
--   3. Verify totals match (the script prints a report).
--   4. Only then run migrations/002_drop_legacy.sql.
--
-- ASSUMPTIONS (verify against your actual schema before running):
--   * `stickers.id` is a bigint/int identity PK.
--   * legacy `ownership` has columns: sticker_id, hana, jon, nabil.
--   Adjust the id types below if yours differ.
-- ============================================================================

-- Needed for gen_random_uuid()
create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- profiles — one row per real person. Identity is keyed by login email, but the
-- SCREENNAME is the display name shown everywhere (decoupled from email/real name).
-- ---------------------------------------------------------------------------
create table if not exists profiles (
    id          uuid primary key default gen_random_uuid(),
    email       text unique not null,         -- Google login identity
    screenname  text unique not null,         -- display name everyone trades to
    real_name   text,                         -- optional, for people known IRL
    emoji       text default '👤',
    color       text default '#93c5fd',
    is_admin    boolean not null default false,
    approved    boolean not null default false,
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- invites — created by an admin with the screenname PRE-FILLED. The new user
-- claims it on first Google login (matched by ?invite=<code>).
-- ---------------------------------------------------------------------------
create table if not exists invites (
    id           uuid primary key default gen_random_uuid(),
    code         text unique not null,
    screenname   text not null,
    email        text,                         -- optional: lock invite to one email
    emoji        text default '👤',
    color        text default '#93c5fd',
    is_admin     boolean not null default false,
    auto_approve boolean not null default true, -- invited users skip the pending queue
    used_by      uuid references profiles(id) on delete set null,
    used_at      timestamptz,
    created_at   timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- ownership — NORMALIZED. One row per (user, sticker).
--   owned  = does the user have the sticker at all
--   extras = the in-game "+N" duplicates beyond the first
--   total  = owned ? 1 + extras : 0   (computed in app code)
-- ---------------------------------------------------------------------------
alter table if exists ownership rename to ownership_legacy;

create table ownership (
    id         bigint generated always as identity primary key,
    user_id    uuid   not null references profiles(id) on delete cascade,
    sticker_id bigint not null references stickers(id) on delete cascade,
    owned      boolean not null default false,
    extras     integer not null default 0,
    updated_at timestamptz not null default now(),
    unique (user_id, sticker_id)
);

create index if not exists idx_ownership_user    on ownership(user_id);
create index if not exists idx_ownership_sticker on ownership(sticker_id);

-- ---------------------------------------------------------------------------
-- uploads / upload_items — durable record of each screenshot analysis so users
-- can review WHY a count was chosen (replaces the ephemeral local-disk archive).
-- The image itself goes to Supabase Storage bucket 'screenshots'; image_path is
-- the object path within that bucket.
-- ---------------------------------------------------------------------------
create table if not exists uploads (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null references profiles(id) on delete cascade,
    image_path   text,                          -- path in the 'screenshots' bucket
    original_name text,
    model_name   text,
    raw_response jsonb,                          -- Gemini's verbatim JSON output
    status       text not null default 'pending', -- pending | applied | discarded
    created_at   timestamptz not null default now()
);

create index if not exists idx_uploads_user on uploads(user_id, created_at desc);

create table if not exists upload_items (
    id                bigint generated always as identity primary key,
    upload_id         uuid not null references uploads(id) on delete cascade,
    detected_name     text,
    detected_owned    boolean,
    detected_extras   integer,
    matched_sticker_id bigint references stickers(id) on delete set null,
    match_method      text,        -- exact | fuzzy | unmatched
    previous_owned    boolean,
    previous_extras   integer,
    new_owned         boolean,
    new_extras        integer,
    applied           boolean not null default false
);

create index if not exists idx_upload_items_upload on upload_items(upload_id);

-- ---------------------------------------------------------------------------
-- database_history — keep, but record the acting user as a uuid going forward.
-- (Legacy `user_profile` text column is left in place for old rows.)
-- ---------------------------------------------------------------------------
alter table if exists database_history
    add column if not exists user_id uuid references profiles(id) on delete set null;

-- ---------------------------------------------------------------------------
-- Storage bucket for screenshots (private). If this errors because the bucket
-- already exists, ignore it. You can also create it from the Storage UI.
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('screenshots', 'screenshots', false)
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- Row-Level Security: enable on all app tables. With NO permissive policies,
-- the anon/authenticated roles get zero access; the app's service-role key
-- bypasses RLS. This closes the "anyone with the anon key can write" hole.
-- ---------------------------------------------------------------------------
alter table profiles        enable row level security;
alter table invites         enable row level security;
alter table ownership       enable row level security;
alter table uploads         enable row level security;
alter table upload_items    enable row level security;
alter table stickers        enable row level security;
alter table database_history enable row level security;
-- Note: ownership_legacy is intentionally left for the data migration; it is
-- dropped by migrations/002_drop_legacy.sql after verification.
