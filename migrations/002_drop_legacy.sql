-- ============================================================================
-- MoGoStickers — Migration 002: drop legacy ownership table
-- ============================================================================
-- RUN THIS ONLY AFTER:
--   1. migrations/001_normalize_and_auth.sql has been applied, AND
--   2. scripts/migrate_ownership.py --apply reported all totals "OK", AND
--   3. you have spot-checked the app and confirmed the 3 users' numbers match prod.
--
-- This permanently removes the old per-user columns. Keep a Supabase backup/branch
-- until you are confident.
-- ============================================================================

drop table if exists ownership_legacy;
