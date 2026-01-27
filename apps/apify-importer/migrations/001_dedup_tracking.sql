-- Migration: 001_dedup_tracking.sql
-- Purpose: Add provenance tracking and deduplication support for Redfin imports
-- Created: 2025-01-26

-- Provenance tracking columns
ALTER TABLE properties ADD COLUMN first_seen_at TEXT;
ALTER TABLE properties ADD COLUMN first_seen_source TEXT;
ALTER TABLE properties ADD COLUMN listing_last_seen_at TEXT;
ALTER TABLE properties ADD COLUMN delisted_at TEXT;

-- Unique constraint on redfin_id (prevents Redfin-to-Redfin duplicates)
CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_redfin_id_unique
ON properties(redfin_id) WHERE redfin_id IS NOT NULL;

-- Backfill existing records with provenance data
UPDATE properties SET
    first_seen_at = created_at,
    first_seen_source = source
WHERE first_seen_at IS NULL;

-- Set listing_last_seen_at for existing Redfin records
UPDATE properties SET
    listing_last_seen_at = updated_at
WHERE source = 'redfin' AND listing_last_seen_at IS NULL;
