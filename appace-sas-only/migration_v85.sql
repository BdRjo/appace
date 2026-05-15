-- ============================================
-- ARS/SAS v85 Enhancement Migration
-- Safe to run multiple times (fully idempotent)
-- Run on PostgreSQL production database
-- ============================================

-- 1. Add indexes for performance
CREATE INDEX IF NOT EXISTS ix_sas_records_record_date ON sas_records (record_date);
CREATE INDEX IF NOT EXISTS ix_sas_records_record_type ON sas_records (record_type);
CREATE INDEX IF NOT EXISTS ix_sas_records_student_id ON sas_records (student_id);
CREATE INDEX IF NOT EXISTS ix_sas_records_status ON sas_records (status);
CREATE INDEX IF NOT EXISTS ix_sas_records_date_type ON sas_records (record_date, record_type);
CREATE INDEX IF NOT EXISTS ix_sas_class_leaves_leave_date ON sas_class_leaves (leave_date);
CREATE INDEX IF NOT EXISTS ix_sas_class_leaves_status ON sas_class_leaves (status);
CREATE INDEX IF NOT EXISTS ix_sas_class_leaves_student_id ON sas_class_leaves (student_id);
CREATE INDEX IF NOT EXISTS ix_sas_students_section_id ON sas_students (section_id);
CREATE INDEX IF NOT EXISTS ix_sas_students_is_active ON sas_students (is_active);
CREATE INDEX IF NOT EXISTS ix_sas_students_student_number ON sas_students (student_number);

-- 2. Add theme columns to SASConfig
ALTER TABLE sas_configs ADD COLUMN IF NOT EXISTS theme_primary VARCHAR(20) DEFAULT '#0891b2';
ALTER TABLE sas_configs ADD COLUMN IF NOT EXISTS theme_primary_dark VARCHAR(20) DEFAULT '#0e7490';
ALTER TABLE sas_configs ADD COLUMN IF NOT EXISTS theme_primary_light VARCHAR(20) DEFAULT '#22d3ee';
ALTER TABLE sas_configs ADD COLUMN IF NOT EXISTS theme_bg VARCHAR(20) DEFAULT '#ecfeff';

-- 3. Clean duplicate attendance records (keep earliest)
DELETE FROM sas_records
WHERE id NOT IN (
    SELECT MIN(id) FROM sas_records GROUP BY student_id, record_date, record_type
);

-- 4. Add unique constraint to prevent future duplicates
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_sas_record_student_date_type'
    ) THEN
        ALTER TABLE sas_records
        ADD CONSTRAINT uq_sas_record_student_date_type
        UNIQUE (student_id, record_date, record_type);
    END IF;
END $$;

-- Done
SELECT 'v85 Migration completed successfully' AS status;
