-- ============================================================================
-- MoGoStickers — Migration 003: relax legacy database_history.user_profile
-- ============================================================================
-- The legacy `user_profile` TEXT column is NOT NULL, but log_history() now records
-- the acting user via `user_id` (added in migration 001) and no longer writes
-- `user_profile`. Without this, every history-logging action (trades, manual edits,
-- upload commits) fails with code 23502.
--
-- Run in the Supabase SQL editor (test on a branch first per CLAUDE.md).
-- ============================================================================

alter table if exists database_history
    alter column user_profile drop not null;
