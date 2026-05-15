# Claude Completion Prompt — ARS/SAS v85 Enhancement

> **How to use:** Copy this entire file and paste it into a Claude conversation along with
> the source files that still need patching. Claude will generate complete, production-ready
> file replacements.

---

## ROLE

You are a senior Python/Flask full-stack developer specializing in bilingual (Arabic RTL / English LTR) educational management systems deployed on Render with PostgreSQL.

## SYSTEM BEING ENHANCED

**ARS (Applied Reservation System)** v84 → v85, specifically its **SAS (Student Attendance System)** module.

**Stack:** Python 3, Flask 3.0.3, SQLAlchemy 2.0.36, PostgreSQL, Bootstrap 5.3 (RTL+LTR), HTMX 1.9.10, Chart.js 4.4, ReportLab 4.2.5 (Arabic PDF), Gunicorn on Render.

**Architecture:**
- `app.py` — Factory pattern, DB session via `g.db`, context processor
- `models/database.py` — ~50 models, SAS hierarchy: Config→Year→Semester→Stage→Class→Section→Student
- `routes/sas.py` — ~2700 lines: staff portal, attendance recording, admin dashboard, student management, CSV export, comparison engine, timetable, holidays, class leave
- `templates/sas/` — 14 templates with bilingual AR/EN support

## FIXES ALREADY APPLIED (v85)

The following have already been applied to the codebase you're receiving:

### models/database.py ✅
- `UniqueConstraint` on SASRecord `(student_id, record_date, record_type)`
- `index=True` on SASRecord.student_id, record_date, record_type, status
- `index=True` on SASClassLeave.student_id, leave_date, status
- `index=True` on SASStudent.section_id, student_number, is_active
- Theme columns on SASConfig: theme_primary, theme_primary_dark, theme_primary_light, theme_bg

### routes/sas.py ✅ (being applied)
- Holiday collision check in record_save
- Duplicate record prevention with skip counter
- Academic year date range scoping for dashboard
- Monthly trend gap filling (no more missing months)
- Date validation (from ≤ to) in compare
- Bulk delete batch endpoint
- Class leave status transition validation
- Period overlap validation helper
- Theme color save in config
- Error logging with `current_app.logger.exception()`

### New files ✅
- `templates/sas/_sas_admin_styles.html` — Shared CSS partial with color variables
- `migration_v85.sql` — Idempotent PostgreSQL migration

## REMAINING WORK — COMPLETE THESE

When the user provides remaining source files, apply these fixes:

### 1. `app.py` — Context Processor & Error Handling
- Add config file caching with 30-second TTL (replace raw `json.load()` calls)
- Fix DB session teardown: call `db.close()` unconditionally, not just on exception
- Add `inject_sas_theme` context processor for SAS routes
- Add global 404/500 error handlers with bilingual pages
- Add real health check that tests DB connectivity

### 2. `templates/sas/admin/dashboard.html`
- Replace hardcoded `:root` CSS variables with `{% include 'sas/_sas_admin_styles.html' %}`
- Use standardized color tokens (`var(--sas-absent)` etc.) for stat cards and charts

### 3. `templates/sas/admin/config.html`
- Add theme color picker section (4 color inputs: primary, dark, light, bg)
- Include the shared CSS partial

### 4. `templates/sas/admin/compare.html`
- Fix division-by-zero: show "N/A" when denominator is 0
- Include the shared CSS partial

### 5. `templates/sas/admin/students.html`
- Replace `bulkDeleteStudents()` JS to use single batch POST endpoint
- Include the shared CSS partial

### 6. `templates/sas/admin/print_report.html`
- Use `@media print` color overrides from shared partial
- Include the shared CSS partial

### 7. `templates/sas/admin/staff.html`, `stages.html`, `periods.html`
- Include the shared CSS partial (replace duplicated CSS blocks)

### 8. All route files (`routes/*.py`)
- Replace bare `except Exception:` + `pass` with specific logging:
  `except Exception as e: current_app.logger.exception(f'...: {e}')`

## OUTPUT FORMAT

For each file, output the COMPLETE file (not diffs). Mark each with:
```
===== FILE: <relative_path> =====
```

## CONSTRAINTS
- Maintain full backward compatibility
- All UI text bilingual using `_t(ar_text, en_text)` or `{% if ar %}...{% else %}...{% endif %}`
- Preserve RTL/LTR, rounded corners, gradient design language
- Database migrations must be idempotent and non-destructive
- No new dependencies
