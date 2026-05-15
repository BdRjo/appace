-- Migration v86: Add time fields to sas_records + remove auto-email flag
-- Run this on your existing database

-- Add time tracking fields to sas_records
ALTER TABLE sas_records ADD COLUMN IF NOT EXISTS all_day INTEGER DEFAULT 1;
ALTER TABLE sas_records ADD COLUMN IF NOT EXISTS time_from VARCHAR(10);
ALTER TABLE sas_records ADD COLUMN IF NOT EXISTS time_to VARCHAR(10);

-- Set existing records as all-day
UPDATE sas_records SET all_day = 1 WHERE all_day IS NULL;
