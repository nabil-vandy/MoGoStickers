-- ============================================================================
-- MoGoStickers — Migration 004: per-user changelog marker
-- ============================================================================
-- Adds profiles.last_seen_changelog so the "What's new" welcome-back popup can
-- remember which changelog set each user has already acknowledged. NULL means the
-- user has never dismissed a changelog (treated as caught-up on first login so
-- returning-only users see the popup, not brand-new ones).
--
-- Run in the Supabase SQL editor (test on a branch first per CLAUDE.md).
-- ============================================================================

alter table if exists profiles
    add column if not exists last_seen_changelog text;
