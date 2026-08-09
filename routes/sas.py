"""
SAS (School Absent System) - Routes Blueprint
Handles staff portal, admin management, and API endpoints for attendance tracking.
"""

import random
import string
import json
import csv
import io
import base64
import calendar
from datetime import datetime, date, timedelta
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    jsonify, abort, g, flash, Response, current_app
)
from sqlalchemy import func, and_, or_, extract
from sqlalchemy.orm import joinedload

from models.database import (
    SASConfig, SASYear, SASSemester, SASStage, SASClass, SASSection,
    SASStudent, SASStaff, SASRecord, SASHoliday, SASClassLeave,
    SASPeriod, SASTimetable
)
from utils.helpers import admin_required
from utils.i18n import t, get_lang

sas_bp = Blueprint('sas', __name__, url_prefix='/sas')


def _t(ar_text, en_text):
    """Bilingual text helper — t() only takes Arabic, this takes both."""
    return ar_text if get_lang() == 'ar' else en_text


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_db():
    return g.db


def _gen_staff_code():
    return 'SAS-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _get_config():
    """Get or create the SAS config singleton."""
    db = get_db()
    cfg = db.query(SASConfig).first()
    if not cfg:
        cfg = SASConfig(
            school_name='المدرسة',
            school_name_en='School',
            academic_year='2025-2026',
        )
        db.add(cfg)
        db.commit()
    return cfg


def _get_staff_or_404(code):
    """Validate a staff code and return the active staff member, or 404."""
    db = get_db()
    staff = db.query(SASStaff).filter(
        SASStaff.staff_code == code,
        SASStaff.is_active == True,
    ).first()
    if not staff:
        abort(404)
    return staff


def _stage_to_dict(s):
    """Convert SASStage to a JSON-safe dict (for |tojson in templates)."""
    return {
        'id': s.id, 'name': s.name or '', 'name_en': s.name_en or '',
        'order_num': s.order_num,
        'classes': [
            {'id': c.id, 'name': c.name or '', 'name_en': c.name_en or '',
             'sections': [{'id': sc.id, 'name': sc.name or '', 'name_en': sc.name_en or ''} for sc in (c.sections if hasattr(c, 'sections') else [])]}
            for c in (s.classes if hasattr(s, 'classes') else [])
        ],
    }


def _staff_to_dict(s):
    """Convert SASStaff to a JSON-safe dict."""
    return {
        'id': s.id, 'name': s.name or '', 'name_en': s.name_en or '',
        'email': s.email or '', 'phone': s.phone or '',
        'staff_code': s.staff_code or '', 'role': s.role or '',
        'stage_id': s.stage_id, 'is_active': s.is_active,
    }


def _today_str():
    return date.today().strftime('%Y-%m-%d')


def _active_year_date_range():
    """Return (start_date_str, end_date_str) for the active academic year."""
    db = get_db()
    cfg = _get_config()
    active_year = db.query(SASYear).filter(
        SASYear.config_id == cfg.id,
        SASYear.is_active == True,
    ).first()
    if active_year:
        year_name = active_year.name or ''
        parts = year_name.split('-')
        if len(parts) == 2:
            try:
                return (f'{parts[0].strip()}-09-01', f'{parts[1].strip()}-08-31')
            except (ValueError, IndexError):
                pass
    today = date.today()
    if today.month >= 9:
        return (f'{today.year}-09-01', f'{today.year + 1}-08-31')
    else:
        return (f'{today.year - 1}-09-01', f'{today.year}-08-31')


def _active_semester_date_range():
    """Return (start_date_str, end_date_str) for the CURRENT semester.
    Prefers a manually-set date range on the active semester (admin-defined
    in the stages/structure page); falls back to the calendar convention
    already used by the comparison feature: Semester 1 = September–January,
    Semester 2 = February–June."""
    db = get_db()
    cfg = _get_config()
    active_semester = (
        db.query(SASSemester)
        .join(SASYear)
        .filter(SASYear.config_id == cfg.id, SASYear.is_active == True, SASSemester.is_active == True)
        .order_by(SASSemester.order_num)
        .first()
    )
    if active_semester and active_semester.start_date and active_semester.end_date:
        return (active_semester.start_date, active_semester.end_date)

    today = date.today()
    year_start, year_end = _active_year_date_range()
    academic_start_year = int(year_start[:4])  # the "September" year of the active academic year
    if today.month >= 9 or today.month == 1:
        # Semester 1: Sep 1 (of academic_start_year) .. Jan 31 (of academic_start_year+1)
        return (f'{academic_start_year}-09-01', f'{academic_start_year + 1}-01-31')
    else:
        # Semester 2: Feb 1 .. Jun 30 (of academic_start_year+1)
        return (f'{academic_start_year + 1}-02-01', f'{academic_start_year + 1}-06-30')


def _week_bounds():
    """Return (monday, sunday) strings for the current ISO week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime('%Y-%m-%d'), sunday.strftime('%Y-%m-%d')


def _month_bounds():
    """Return (first_day, last_day) strings for the current month."""
    today = date.today()
    first = today.replace(day=1)
    if today.month == 12:
        last = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return first.strftime('%Y-%m-%d'), last.strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# Permission helper
# ---------------------------------------------------------------------------

_PERM_MATRIX = {
    'view_own_stage':   {'supervisor', 'secretary', 'manager'},
    'view_all':         {'manager'},  # secretary/supervisor are confined to their own stage_id (see _enforce_stage_scope)
    'create_record':    {'supervisor', 'secretary', 'manager'},
    'edit_record':      {'manager'},          # Only manager can edit (immutability)
    'delete_record':    {'manager'},
    'approve_record':   {'manager'},
    'create_class_leave': {'supervisor', 'secretary', 'manager'},
    'approve_class_leave': {'secretary', 'manager'},
    'create_holiday':   {'supervisor', 'secretary', 'manager'},
    'approve_holiday':  {'manager'},
    'delete_holiday':   {'manager'},
    'view_pending':     {'secretary', 'manager'},  # secretary sees class leave, manager sees all
    'view_reports':     {'supervisor', 'secretary', 'manager'},
    'upload_attachment': {'supervisor', 'secretary', 'manager'},
}


def _check_perm(staff, action):
    """Return True if staff role is allowed the given action."""
    allowed = _PERM_MATRIX.get(action, set())
    return staff.role in allowed


def _staff_stage_ids_or_none(staff):
    """Return the set of stage IDs this staff member is confined to, or None
    if they're a manager (unrestricted — sees every region).

    Fails CLOSED: a non-manager with no stage_id assigned gets an empty set
    (access to zero regions), never unrestricted access. Every supervisor
    and secretary must have a stage assigned to see anything."""
    if staff.role == 'manager':
        return None
    return {staff.stage_id} if staff.stage_id else set()


def _enforce_stage_scope(staff, stage_id):
    """Abort 403 if this staff member (supervisor or secretary) is assigned
    to a specific region and is trying to access a different one."""
    scope = _staff_stage_ids_or_none(staff)
    if scope is not None and stage_id not in scope:
        abort(403)


def _student_in_scope(db, staff, student):
    """Abort 403 if the student's region doesn't match this staff member's
    assigned region (managers are unrestricted)."""
    scope = _staff_stage_ids_or_none(staff)
    if scope is None:
        return
    stage_id = None
    if student and student.section and student.section.sas_class:
        stage_id = student.section.sas_class.stage_id
    if stage_id not in scope:
        abort(403)


# Class leave type labels (bilingual)
CLASS_LEAVE_TYPES = {
    'library':        ('المكتبة', 'Library'),
    'not_showup':     ('عدم حضور', 'Not Show Up'),
    'day_leave':      ('إذن يومي', 'Day Leave'),
    'counseling':     ('الإرشاد', 'Counseling'),
    'clinic':         ('العيادة', 'Clinic'),
    'cafeteria':      ('المقصف', 'Cafeteria'),
    'exam':           ('اختبار', 'Exam'),
    'partial_day':    ('دوام جزئي', 'Partial Day'),
    'leave_school':   ('مغادرة المدرسة مع ولي الأمر', 'Leaving School with Parent'),
    'other':          ('أخرى', 'Other'),
}


def _leave_type_label(key):
    """Return bilingual label for a class leave type."""
    pair = CLASS_LEAVE_TYPES.get(key, (key, key))
    return pair[0] if get_lang() == 'ar' else pair[1]


def _check_period_overlap(db, stage_id, day_of_week, start_time, end_time, exclude_id=None, class_id=None):
    """Check if a period overlaps with existing periods in the same scope
    (stage default when class_id is None, or that class's override)."""
    query = db.query(SASPeriod).filter(
        SASPeriod.stage_id == stage_id,
        SASPeriod.class_id == class_id,
        SASPeriod.day_of_week == day_of_week,
        SASPeriod.start_time < end_time,
        SASPeriod.end_time > start_time,
    )
    if exclude_id:
        query = query.filter(SASPeriod.id != exclude_id)
    return query.first()


# ===========================================================================
# PUBLIC PORTAL ROUTES
# ===========================================================================

# 1. Welcome page
@sas_bp.route('/')
def welcome():
    cfg = _get_config()
    return render_template('sas/welcome.html', config=cfg)


# 2. Staff login via code
@sas_bp.route('/login', methods=['GET','POST'])
def login():
    staff_code = (request.form.get('code') or request.form.get('staff_code') or '').strip()
    card_role = (request.form.get('role') or '').strip()
    if not staff_code:
        flash(_t('يرجى إدخال الرمز', 'Please enter a code'), 'danger')
        return redirect(url_for('sas.welcome'))

    db = get_db()
    staff = db.query(SASStaff).filter(
        SASStaff.staff_code == staff_code,
        SASStaff.is_active == True,
    ).first()

    if not staff:
        flash(_t('رمز الدخول غير صحيح', 'Invalid staff code'), 'danger')
        return redirect(url_for('sas.welcome'))

    # The welcome page has a separate login card per role (supervisor/secretary/
    # manager). Reject a code entered into the wrong card — a supervisor's code
    # must not be accepted through the "Login as manager" card, etc.
    if card_role and staff.role != card_role:
        flash(_t('هذا الرمز لا يعود لهذا النوع من الحسابات. يرجى استخدام البطاقة الصحيحة حسب دورك',
                  'This code does not belong to this account type. Please use the correct login card for your role'), 'danger')
        return redirect(url_for('sas.welcome'))

    return redirect(url_for('sas.portal_home', code=staff.staff_code))


# 3. Staff portal home
@sas_bp.route('/portal/<code>')
def portal_home(code):
    staff = _get_staff_or_404(code)
    db = get_db()
    cfg = _get_config()
    today = _today_str()

    # Today's stats scoped to the staff member's stage
    stage_filter = []
    if staff.stage_id:
        stage_filter.append(
            SASRecord.student_id.in_(
                db.query(SASStudent.id)
                .join(SASSection)
                .join(SASClass)
                .filter(SASClass.stage_id == staff.stage_id)
            )
        )

    today_absent = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date == today,
        SASRecord.record_type == 'absent',
        *stage_filter,
    ).scalar() or 0

    today_late = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date == today,
        SASRecord.record_type == 'late',
        *stage_filter,
    ).scalar() or 0

    today_leave = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date == today,
        SASRecord.record_type == 'leave',
        *stage_filter,
    ).scalar() or 0

    today_other = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date == today,
        SASRecord.record_type == 'other',
        *stage_filter,
    ).scalar() or 0

    pending_count = db.query(func.count(SASRecord.id)).filter(
        SASRecord.status == 'pending',
        *stage_filter,
    ).scalar() or 0

    today_stats = {
        'total_absent': today_absent,
        'total_late': today_late,
        'total_leave': today_leave,
        'total_other': today_other,
    }

    # Class leave stats for today
    cl_filter = []
    if staff.stage_id:
        cl_filter.append(
            SASClassLeave.student_id.in_(
                db.query(SASStudent.id)
                .join(SASSection)
                .join(SASClass)
                .filter(SASClass.stage_id == staff.stage_id)
            )
        )

    today_class_leave = db.query(func.count(SASClassLeave.id)).filter(
        SASClassLeave.leave_date == today,
        *cl_filter,
    ).scalar() or 0

    pending_class_leave = db.query(func.count(SASClassLeave.id)).filter(
        SASClassLeave.status == 'pending',
        SASClassLeave.leave_date == today,
        *cl_filter,
    ).scalar() or 0

    # All stages with student counts — scoped to this staff member's own
    # region (managers see every stage; supervisors/secretaries see only
    # the one they're assigned to, since that's all they can access anyway)
    stages_q = db.query(SASStage).order_by(SASStage.order_num)
    if staff.role != 'manager':
        stages_q = stages_q.filter(SASStage.id == staff.stage_id) if staff.stage_id else stages_q.filter(SASStage.id.is_(None))
    all_stages = stages_q.all()
    for st in all_stages:
        st.student_count = db.query(func.count(SASStudent.id)).join(
            SASSection
        ).join(SASClass).filter(
            SASClass.stage_id == st.id,
            SASStudent.is_active == True,
        ).scalar() or 0

    return render_template(
        'sas/portal_home.html',
        config=cfg,
        staff=staff,
        stages=all_stages,
        today_stats=today_stats,
        pending_count=pending_count,
        today_class_leave=today_class_leave,
        pending_class_leave=pending_class_leave,
        leave_types=CLASS_LEAVE_TYPES,
    )


# 4. Stage students list with section tabs
@sas_bp.route('/portal/<code>/stage/<int:stage_id>')
def stage_students(code, stage_id):
    staff = _get_staff_or_404(code)
    db = get_db()
    cfg = _get_config()

    stage = db.query(SASStage).options(
        joinedload(SASStage.classes).joinedload(SASClass.sections).joinedload(SASSection.students)
    ).get(stage_id)
    if not stage:
        abort(404)
    _enforce_stage_scope(staff, stage_id)

    section_id = request.args.get('section_id', type=int)
    today = _today_str()

    # Build a set of student IDs who have a record today for quick lookup
    student_ids_in_stage = (
        db.query(SASStudent.id)
        .join(SASSection)
        .join(SASClass)
        .filter(SASClass.stage_id == stage_id)
        .all()
    )
    student_ids_in_stage = [s[0] for s in student_ids_in_stage]

    today_records = {}
    if student_ids_in_stage:
        recs = db.query(SASRecord).filter(
            SASRecord.student_id.in_(student_ids_in_stage),
            SASRecord.record_date == today,
        ).all()
        for r in recs:
            today_records[r.student_id] = r.record_type

    return render_template(
        'sas/stage_students.html',
        config=cfg,
        staff=staff,
        stage=stage,
        classes=stage.classes,
        section_id=section_id,
        today_records=today_records,
        today_date=today,
        leave_types=CLASS_LEAVE_TYPES,
    )


# 5. Student detail + record history
@sas_bp.route('/portal/<code>/student/<int:student_id>')
def student_detail(code, student_id):
    staff = _get_staff_or_404(code)
    db = get_db()
    cfg = _get_config()

    student = db.query(SASStudent).options(
        joinedload(SASStudent.section).joinedload(SASSection.sas_class).joinedload(SASClass.stage)
    ).get(student_id)
    if not student:
        abort(404)
    _student_in_scope(db, staff, student)

    records = (
        db.query(SASRecord)
        .filter(SASRecord.student_id == student_id)
        .order_by(SASRecord.record_date.desc(), SASRecord.created_at.desc())
        .all()
    )

    # Class leave history for this student
    class_leaves = (
        db.query(SASClassLeave)
        .options(joinedload(SASClassLeave.staff))
        .filter(SASClassLeave.student_id == student_id)
        .order_by(SASClassLeave.leave_date.desc(), SASClassLeave.created_at.desc())
        .all()
    )

    section = student.section
    sas_class = section.sas_class if section else None
    stage = sas_class.stage if sas_class else None

    return render_template(
        'sas/student_detail.html',
        config=cfg,
        staff=staff,
        student=student,
        records=records,
        class_leaves=class_leaves,
        leave_types=CLASS_LEAVE_TYPES,
        section=section,
        sas_class=sas_class,
        stage=stage,
    )


# 6. Add attendance record
@sas_bp.route('/portal/<code>/record/add', methods=['POST'])
def record_add(code):
    staff = _get_staff_or_404(code)
    db = get_db()

    student_id = request.form.get('student_id', type=int)
    record_date = request.form.get('record_date', _today_str()).strip()
    record_type = request.form.get('record_type', 'absent').strip()
    notes = request.form.get('notes', '').strip()

    if not student_id:
        flash(_t('يرجى تحديد الطالب', 'Please select a student'), 'danger')
        return redirect(request.referrer or url_for('sas.portal_home', code=code))

    student = db.get(SASStudent, student_id)
    if not student:
        abort(404)
    _student_in_scope(db, staff, student)

    attachment_b64 = None
    attachment_name = None
    file = request.files.get('attachment')
    if file and file.filename:
        attachment_name = file.filename
        attachment_b64 = base64.b64encode(file.read()).decode('utf-8')

    record = SASRecord(
        student_id=student_id,
        staff_id=staff.id,
        record_date=record_date,
        record_type=record_type,
        status='pending',
        notes=notes,
        attachment_b64=attachment_b64,
        attachment_name=attachment_name,
    )
    db.add(record)

    try:
        db.commit()
        flash(_t('تم إضافة السجل بنجاح', 'Record added successfully'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ أثناء الحفظ', 'Error saving record'), 'danger')

    return redirect(url_for('sas.student_detail', code=code, student_id=student_id))


# 7. Edit a record
@sas_bp.route('/portal/<code>/record/<int:rid>/edit', methods=['POST'])
def record_edit(code, rid):
    staff = _get_staff_or_404(code)
    db = get_db()

    record = db.get(SASRecord, rid)
    if not record:
        abort(404)

    # Record immutability: only manager can edit records
    if not _check_perm(staff, 'edit_record'):
        flash(_t('ليس لديك صلاحية تعديل السجل', 'You do not have permission to edit records'), 'danger')
        return redirect(url_for('sas.student_detail', code=code, student_id=record.student_id))

    record.record_date = request.form.get('record_date', record.record_date).strip()
    record.record_type = request.form.get('record_type', record.record_type).strip()
    record.notes = request.form.get('notes', record.notes or '').strip()

    file = request.files.get('attachment')
    if file and file.filename:
        record.attachment_name = file.filename
        record.attachment_b64 = base64.b64encode(file.read()).decode('utf-8')

    record.updated_at = datetime.utcnow()

    try:
        db.commit()
        flash(_t('تم تعديل السجل بنجاح', 'Record updated successfully'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ أثناء التعديل', 'Error updating record'), 'danger')

    return redirect(url_for('sas.student_detail', code=code, student_id=record.student_id))


# 8. Delete a record (manager only)
@sas_bp.route('/portal/<code>/record/<int:rid>/delete', methods=['POST'])
def record_delete(code, rid):
    staff = _get_staff_or_404(code)
    db = get_db()

    if staff.role != 'manager':
        abort(403)

    record = db.get(SASRecord, rid)
    if not record:
        abort(404)

    student_id = record.student_id
    db.delete(record)

    try:
        db.commit()
        flash(_t('تم حذف السجل', 'Record deleted'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ أثناء الحذف', 'Error deleting record'), 'danger')

    return redirect(url_for('sas.student_detail', code=code, student_id=student_id))


# 8b. Download a record's attachment
@sas_bp.route('/portal/<code>/record/<int:record_id>/attachment')
def download_attachment(code, record_id):
    _get_staff_or_404(code)
    db = get_db()
    record = db.get(SASRecord, record_id)
    if not record or not record.attachment_b64:
        abort(404)
    import base64
    data = base64.b64decode(record.attachment_b64)
    filename = record.attachment_name or 'attachment'
    return Response(data, mimetype='application/octet-stream',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


# 9. Approve / reject a record (manager only)
@sas_bp.route('/portal/<code>/record/<int:rid>/approve', methods=['POST'])
def record_approve(code, rid):
    staff = _get_staff_or_404(code)
    db = get_db()

    if staff.role != 'manager':
        abort(403)

    record = db.get(SASRecord, rid)
    if not record:
        abort(404)

    action = request.form.get('action', '').strip()
    if action == 'approve':
        record.status = 'approved'
    elif action == 'reject':
        record.status = 'rejected'
    else:
        flash(_t('إجراء غير صالح', 'Invalid action'), 'danger')
        return redirect(request.referrer or url_for('sas.portal_home', code=code))

    record.approved_by = staff.id
    record.approved_at = datetime.utcnow()
    record.updated_at = datetime.utcnow()

    try:
        db.commit()
        flash(_t('تم تحديث حالة السجل', 'Record status updated'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ', 'An error occurred'), 'danger')

    return redirect(request.referrer or url_for('sas.portal_home', code=code))


# 10. Bulk mark absent
@sas_bp.route('/portal/<code>/bulk-absent', methods=['POST'])
def bulk_absent(code):
    staff = _get_staff_or_404(code)
    db = get_db()

    student_ids = request.form.getlist('student_ids', type=int)
    record_date = request.form.get('record_date', _today_str()).strip()
    record_type = request.form.get('record_type', 'absent').strip()
    bulk_notes = request.form.get('bulk_notes', '').strip()
    bulk_leave_reason = request.form.get('bulk_leave_reason', '').strip()

    # Handle file attachment for bulk records
    attachment_b64 = None
    attachment_name = None
    file = request.files.get('bulk_attachment')
    if file and file.filename:
        attachment_name = file.filename
        attachment_b64 = base64.b64encode(file.read()).decode('utf-8')

    if not student_ids:
        flash(_t('لم يتم تحديد طلاب', 'No students selected'), 'danger')
        return redirect(request.referrer or url_for('sas.portal_home', code=code))

    # Drop any student outside this staff member's assigned region
    # (managers are unrestricted; supervisors/secretaries are confined)
    scope = _staff_stage_ids_or_none(staff)
    if scope is not None:
        in_scope_ids = {
            row[0] for row in
            db.query(SASStudent.id)
            .join(SASSection).join(SASClass)
            .filter(SASStudent.id.in_(student_ids), SASClass.stage_id.in_(scope))
            .all()
        }
        student_ids = [sid for sid in student_ids if sid in in_scope_ids]
        if not student_ids:
            flash(_t('لا يمكنك تسجيل غياب لطلاب خارج منطقتك', 'You cannot record attendance for students outside your assigned region'), 'danger')
            return redirect(request.referrer or url_for('sas.portal_home', code=code))

    # Build notes string with leave reason if provided
    notes_text = ''
    if bulk_leave_reason:
        lt = CLASS_LEAVE_TYPES.get(bulk_leave_reason, (bulk_leave_reason, bulk_leave_reason))
        notes_text = lt[0] if get_lang() == 'ar' else lt[1]
    if bulk_notes:
        notes_text = f'{notes_text} - {bulk_notes}' if notes_text else bulk_notes

    # Holiday collision check
    cfg = _get_config()
    holidays = db.query(SASHoliday).filter(
        SASHoliday.config_id == cfg.id,
        SASHoliday.status == 'approved',
        SASHoliday.start_date <= record_date,
        SASHoliday.end_date >= record_date,
    ).first()
    if holidays:
        flash(
            _t(f'لا يمكن التسجيل: التاريخ {record_date} يصادف إجازة ({holidays.title})',
               f'Cannot record: {record_date} falls on holiday ({holidays.title_en or holidays.title})'),
            'danger',
        )
        return redirect(request.referrer or url_for('sas.portal_home', code=code))

    created = 0
    skipped = 0
    for sid in student_ids:
        existing = db.query(SASRecord).filter(
            SASRecord.student_id == sid,
            SASRecord.record_date == record_date,
            SASRecord.record_type == record_type,
        ).first()
        if existing:
            skipped += 1
            continue
        record = SASRecord(
            student_id=sid,
            staff_id=staff.id,
            record_date=record_date,
            record_type=record_type,
            status='pending',
            notes=notes_text or None,
            attachment_b64=attachment_b64,
            attachment_name=attachment_name,
        )
        db.add(record)
        created += 1

    try:
        db.commit()
        msg_parts = []
        if created:
            msg_parts.append(_t(f'تم تسجيل {created} حالة', f'{created} records created'))
        if skipped:
            msg_parts.append(_t(f'تم تخطي {skipped} مكرر', f'{skipped} duplicates skipped'))
        flash(' | '.join(msg_parts) if msg_parts else _t('لا تغييرات', 'No changes'), 'success' if created else 'warning')
    except Exception as e:
        db.rollback()
        current_app.logger.exception(f'Record save failed: {e}')
        flash(_t('حدث خطأ أثناء الحفظ', 'Error saving records'), 'danger')

    return redirect(request.referrer or url_for('sas.portal_home', code=code))


# 11. Create holiday
@sas_bp.route('/portal/<code>/holiday/add', methods=['POST'])
def holiday_add(code):
    staff = _get_staff_or_404(code)
    db = get_db()
    cfg = _get_config()

    title = request.form.get('title', '').strip()
    title_en = request.form.get('title_en', '').strip()
    start_date = request.form.get('start_date', '').strip()
    end_date = request.form.get('end_date', '').strip()
    applies_to = request.form.get('applies_to', 'all').strip()

    # Scope selection
    scope_type = request.form.get('scope_type', 'school').strip()
    scope_ids_raw = request.form.getlist('scope_ids')
    scope_ids = json.dumps([int(x) for x in scope_ids_raw if x.strip().isdigit()]) if scope_ids_raw else '[]'

    if not title or not start_date or not end_date:
        flash(_t('يرجى تعبئة جميع الحقول المطلوبة', 'Please fill all required fields'), 'danger')
        return redirect(url_for('sas.holidays', code=code))

    # Normalise applies_to as JSON
    if applies_to != 'all':
        try:
            json.loads(applies_to)
        except (json.JSONDecodeError, TypeError):
            applies_to = json.dumps(applies_to)
    else:
        applies_to = json.dumps('all')

    from datetime import date as _date
    try:
        start_date = _date.fromisoformat(start_date)
        end_date = _date.fromisoformat(end_date)
    except ValueError:
        flash(_t('تنسيق التاريخ غير صحيح', 'Invalid date format'), 'danger')
        return redirect(url_for('sas.holidays', code=code))

    holiday = SASHoliday(
        config_id=cfg.id,
        title=title,
        title_en=title_en,
        start_date=start_date,
        end_date=end_date,
        applies_to=applies_to,
        scope_type=scope_type,
        scope_ids=scope_ids,
        status='pending',
        created_by=staff.id,
    )
    db.add(holiday)

    try:
        db.commit()
        flash(_t('تمت إضافة الإجازة بنجاح', 'Holiday added successfully'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ أثناء الحفظ', 'Error saving holiday'), 'danger')

    return redirect(url_for('sas.holidays', code=code))


# 11b. Delete holiday (manager/admin only)
@sas_bp.route('/portal/<code>/holiday/<int:holiday_id>/delete', methods=['POST'])
def holiday_delete(code, holiday_id):
    staff = _get_staff_or_404(code)
    if staff.role not in ('manager',):
        abort(403)
    db = get_db()
    holiday = db.get(SASHoliday, holiday_id)
    if holiday:
        try:
            db.delete(holiday)
            db.commit()
        except Exception:
            db.rollback()
    return redirect(url_for('sas.holidays', code=code))


# 12. List holidays
@sas_bp.route('/portal/<code>/holidays')
def holidays(code):
    staff = _get_staff_or_404(code)
    db = get_db()
    cfg = _get_config()

    holiday_list = (
        db.query(SASHoliday)
        .filter(SASHoliday.config_id == cfg.id)
        .order_by(SASHoliday.start_date.desc())
        .all()
    )

    # Stages for scope selection dropdown
    stages = db.query(SASStage).filter(SASStage.config_id == cfg.id).order_by(SASStage.order_num).all()
    stages_json = [_stage_to_dict(s) for s in stages]

    return render_template(
        'sas/holidays.html',
        config=cfg,
        staff=staff,
        holidays=holiday_list,
        stages=stages,
        stages_json=stages_json,
    )


# 13. Pending approvals (manager sees all, secretary sees class leave only)
@sas_bp.route('/portal/<code>/pending')
def pending(code):
    staff = _get_staff_or_404(code)
    db = get_db()
    cfg = _get_config()

    if not _check_perm(staff, 'view_pending'):
        abort(403)

    # Pending attendance records (manager only)
    records = []
    if staff.role == 'manager':
        query = db.query(SASRecord).options(
            joinedload(SASRecord.student).joinedload(SASStudent.section)
            .joinedload(SASSection.sas_class).joinedload(SASClass.stage),
            joinedload(SASRecord.staff),
        ).filter(SASRecord.status == 'pending')

        if staff.stage_id:
            query = query.filter(
                SASRecord.student_id.in_(
                    db.query(SASStudent.id)
                    .join(SASSection)
                    .join(SASClass)
                    .filter(SASClass.stage_id == staff.stage_id)
                )
            )
        records = query.order_by(SASRecord.created_at.desc()).all()

    # Pending class leave approvals (secretary + manager)
    cl_query = db.query(SASClassLeave).options(
        joinedload(SASClassLeave.student).joinedload(SASStudent.section)
        .joinedload(SASSection.sas_class).joinedload(SASClass.stage),
        joinedload(SASClassLeave.staff),
    ).filter(SASClassLeave.status == 'pending')

    if staff.stage_id:
        cl_query = cl_query.filter(
            SASClassLeave.student_id.in_(
                db.query(SASStudent.id)
                .join(SASSection)
                .join(SASClass)
                .filter(SASClass.stage_id == staff.stage_id)
            )
        )
    class_leaves = cl_query.order_by(SASClassLeave.created_at.desc()).all()

    # Pending holidays (manager only)
    pending_holidays = []
    if staff.role == 'manager':
        pending_holidays = db.query(SASHoliday).filter(
            SASHoliday.config_id == cfg.id,
            SASHoliday.status == 'pending',
        ).order_by(SASHoliday.start_date.desc()).all()

    return render_template(
        'sas/pending.html',
        config=cfg,
        staff=staff,
        records=records,
        class_leaves=class_leaves,
        pending_holidays=pending_holidays,
        leave_types=CLASS_LEAVE_TYPES,
    )


# ===========================================================================
# ADMIN ROUTES
# ===========================================================================

# 14. Admin dashboard
@sas_bp.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    db = get_db()
    cfg = _get_config()
    today = _today_str()
    week_start, week_end = _week_bounds()
    month_start, month_end = _month_bounds()
    year_start, year_end = _active_year_date_range()
    semester_start, semester_end = _active_semester_date_range()

    total_students = db.query(func.count(SASStudent.id)).filter(
        SASStudent.is_active == True,
    ).scalar() or 0

    today_absences = today_absent = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date == today,
        SASRecord.record_type == 'absent',
    ).scalar() or 0

    today_late = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date == today,
        SASRecord.record_type == 'late',
    ).scalar() or 0

    today_leave = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date == today,
        SASRecord.record_type == 'leave',
    ).scalar() or 0

    week_absences = week_total = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date >= week_start,
        SASRecord.record_date <= week_end,
    ).scalar() or 0

    month_absences = month_total = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date >= month_start,
        SASRecord.record_date <= month_end,
    ).scalar() or 0

    # Top 10 absent students
    top_absent = (
        db.query(
            SASStudent,
            func.count(SASRecord.id).label('absence_count'),
        )
        .join(SASRecord, SASRecord.student_id == SASStudent.id)
        .filter(
            SASRecord.record_type == 'absent',
            SASRecord.record_date >= year_start,
            SASRecord.record_date <= year_end,
        )
        .group_by(SASStudent.id)
        .order_by(func.count(SASRecord.id).desc())
        .limit(10)
        .all()
    )

    # Stage distribution
    stage_dist = (
        db.query(
            SASStage.name,
            SASStage.name_en,
            func.count(SASRecord.id).label('record_count'),
        )
        .join(SASClass, SASClass.stage_id == SASStage.id)
        .join(SASSection, SASSection.class_id == SASClass.id)
        .join(SASStudent, SASStudent.section_id == SASSection.id)
        .join(SASRecord, SASRecord.student_id == SASStudent.id)
        .filter(
            SASRecord.record_date >= year_start,
            SASRecord.record_date <= year_end,
        )
        .group_by(SASStage.id, SASStage.name, SASStage.name_en)
        .order_by(func.count(SASRecord.id).desc())
        .all()
    )

    # Monthly trend (last 6 months)
    monthly_trend = []
    today_d = date.today()
    for i in range(5, -1, -1):
        m = today_d.month - i
        y = today_d.year
        while m <= 0:
            m += 12
            y -= 1
        m_start = date(y, m, 1)
        last_day = calendar.monthrange(y, m)[1]
        m_end = date(y, m, last_day)
        count = db.query(func.count(SASRecord.id)).filter(
            SASRecord.record_date >= m_start.strftime('%Y-%m-%d'),
            SASRecord.record_date <= m_end.strftime('%Y-%m-%d'),
            SASRecord.record_type == 'absent',
        ).scalar() or 0
        monthly_trend.append({
            'month': m_start.strftime('%Y-%m'),
            'label': m_start.strftime('%b %Y'),
            'count': count,
        })

    # Class leave stats for dashboard
    today_class_leaves = db.query(func.count(SASClassLeave.id)).filter(
        SASClassLeave.leave_date == today,
    ).scalar() or 0

    # Class leave by type (today)
    cl_by_type = (
        db.query(SASClassLeave.leave_type, func.count(SASClassLeave.id))
        .filter(SASClassLeave.leave_date == today)
        .group_by(SASClassLeave.leave_type)
        .all()
    )

    pending_class_leaves = db.query(func.count(SASClassLeave.id)).filter(
        SASClassLeave.status == 'pending',
    ).scalar() or 0

    return render_template(
        'sas/admin/dashboard.html',
        config=cfg,
        total_students=total_students,
        today_date=today,
        today_absent=today_absent,
        today_late=today_late,
        today_leave=today_leave,
        week_start=week_start,
        week_end=week_end,
        week_total=week_total,
        month_start=month_start,
        month_end=month_end,
        month_total=month_total,
        semester_start=semester_start,
        semester_end=semester_end,
        year_start=year_start,
        year_end=year_end,
        today_absences=today_absences,
        week_absences=week_absences,
        month_absences=month_absences,
        top_absent=top_absent,
        stage_dist=stage_dist,
        monthly_trend=monthly_trend,
        today_class_leaves=today_class_leaves,
        cl_by_type=cl_by_type,
        pending_class_leaves=pending_class_leaves,
        leave_types=CLASS_LEAVE_TYPES,
    )


# 15. Module settings form
@sas_bp.route('/admin/config')
@admin_required
def admin_config():
    cfg = _get_config()
    # Parse ticker_json so the template can read individual fields
    ticker = {}
    if cfg.ticker_json:
        try:
            ticker = json.loads(cfg.ticker_json)
        except Exception:
            pass
    return render_template('sas/admin/config.html', config=cfg, ticker=ticker)


# 16. Save config
@sas_bp.route('/admin/config/save', methods=['POST'])
@admin_required
def admin_config_save():
    db = get_db()
    cfg = _get_config()

    cfg.school_name = request.form.get('school_name_ar', request.form.get('school_name', cfg.school_name or '')).strip()
    cfg.school_name_en = request.form.get('school_name_en', cfg.school_name_en or '').strip()
    cfg.academic_year = request.form.get('academic_year', cfg.academic_year or '').strip()
    cfg.is_active = bool(request.form.get('is_active'))

    logo_file = request.files.get('school_logo')
    if logo_file and logo_file.filename:
        cfg.school_logo_b64 = base64.b64encode(logo_file.read()).decode('utf-8')

    cfg.theme_primary = request.form.get('theme_primary', cfg.theme_primary or '#0891b2').strip()
    cfg.theme_primary_dark = request.form.get('theme_primary_dark', cfg.theme_primary_dark or '#0e7490').strip()
    cfg.theme_primary_light = request.form.get('theme_primary_light', cfg.theme_primary_light or '#22d3ee').strip()
    cfg.theme_bg = request.form.get('theme_bg', cfg.theme_bg or '#ecfeff').strip()

    # Build ticker_json from individual form fields
    feeds_ar_raw = request.form.get('ticker_feeds_ar', '').strip()
    feeds_en_raw = request.form.get('ticker_feeds_en', '').strip()
    feeds_ar = [l.strip() for l in feeds_ar_raw.splitlines() if l.strip()] if feeds_ar_raw else []
    feeds_en = [l.strip() for l in feeds_en_raw.splitlines() if l.strip()] if feeds_en_raw else []

    ticker_data = {
        'feeds_ar': feeds_ar,
        'feeds_en': feeds_en,
        'fg': request.form.get('ticker_text_color', '#ffffff'),
        'bg': request.form.get('ticker_bg_color', '#1e293b'),
        'opacity': int(request.form.get('ticker_bg_opacity', 100)),
        'mask_fade': int(request.form.get('ticker_mask_fade', 12)),
        'font': request.form.get('ticker_font', "'Segoe UI',Tahoma,Arial,sans-serif"),
        'size': int(request.form.get('ticker_font_size', 14)),
        'speed': int(request.form.get('ticker_speed', 35)),
        'logo_url': request.form.get('ticker_logo_url', '').strip(),
        'logo_size': int(request.form.get('ticker_logo_size', 28)),
        'logo_pulse': bool(request.form.get('ticker_logo_pulse')),
        'logo_pulse_speed': int(request.form.get('ticker_logo_pulse_speed', 10)),
        'sep_img_url': request.form.get('ticker_sep_img_url', '').strip(),
    }
    cfg.ticker_json = json.dumps(ticker_data, ensure_ascii=False)

    try:
        db.commit()
        flash(_t('تم حفظ الإعدادات', 'Settings saved'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ أثناء الحفظ', 'Error saving settings'), 'danger')

    return redirect(url_for('sas.admin_config'))


# 17. Staff list
@sas_bp.route('/admin/staff')
@admin_required
def admin_staff():
    db = get_db()
    cfg = _get_config()

    staff_list = (
        db.query(SASStaff)
        .filter(SASStaff.config_id == cfg.id)
        .options(joinedload(SASStaff.stage))
        .order_by(SASStaff.name)
        .all()
    )
    stages = db.query(SASStage).filter(SASStage.config_id == cfg.id).order_by(SASStage.order_num).all()

    staff_json = [_staff_to_dict(s) for s in staff_list]

    return render_template(
        'sas/admin/staff.html',
        config=cfg,
        staff_list=staff_list,
        staff_json=staff_json,
        stages=stages,
    )


# 18. Add staff member
@sas_bp.route('/admin/staff/add', methods=['POST'])
@admin_required
def admin_staff_add():
    db = get_db()
    cfg = _get_config()

    name = request.form.get('name', '').strip()
    name_en = request.form.get('name_en', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    role = request.form.get('role', 'supervisor').strip()
    stage_id = request.form.get('stage_id', type=int)

    if not name:
        flash(_t('يرجى إدخال اسم الموظف', 'Please enter staff name'), 'danger')
        return redirect(url_for('sas.admin_staff'))

    if role in ('supervisor', 'secretary') and not stage_id:
        flash(_t('يجب تحديد المنطقة/المرحلة لهذا الدور، وإلا لن يتمكن الموظف من الدخول لأي منطقة',
                  'A region/stage must be selected for this role, otherwise the staff member will have no region access'), 'danger')
        return redirect(url_for('sas.admin_staff'))

    # Generate unique staff code
    code = _gen_staff_code()
    while db.query(SASStaff).filter(SASStaff.staff_code == code).first():
        code = _gen_staff_code()

    staff = SASStaff(
        config_id=cfg.id,
        name=name,
        name_en=name_en,
        email=email,
        phone=phone,
        staff_code=code,
        role=role,
        stage_id=stage_id,
        is_active=True,
    )
    db.add(staff)

    try:
        db.commit()
        flash(_t(f'تمت الإضافة بنجاح. الرمز: {code}', f'Staff added. Code: {code}'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ أثناء الحفظ', 'Error saving staff'), 'danger')

    return redirect(url_for('sas.admin_staff'))


# 19. Edit staff
@sas_bp.route('/admin/staff/<int:sid>/edit', methods=['POST'])
@admin_required
def admin_staff_edit(sid):
    db = get_db()
    staff = db.get(SASStaff, sid)
    if not staff:
        abort(404)

    staff.name = request.form.get('name', staff.name).strip()
    staff.name_en = request.form.get('name_en', staff.name_en).strip()
    staff.email = request.form.get('email', staff.email or '').strip()
    staff.phone = request.form.get('phone', staff.phone or '').strip()
    new_role = request.form.get('role', staff.role).strip()
    new_stage_id = request.form.get('stage_id', type=int) or staff.stage_id

    if new_role in ('supervisor', 'secretary') and not new_stage_id:
        flash(_t('يجب تحديد المنطقة/المرحلة لهذا الدور، وإلا لن يتمكن الموظف من الدخول لأي منطقة',
                  'A region/stage must be selected for this role, otherwise the staff member will have no region access'), 'danger')
        return redirect(url_for('sas.admin_staff'))

    staff.role = new_role
    staff.stage_id = new_stage_id
    staff.is_active = request.form.get('is_active', '1') == '1'

    try:
        db.commit()
        flash(_t('تم تعديل بيانات الموظف', 'Staff updated'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ أثناء التعديل', 'Error updating staff'), 'danger')

    return redirect(url_for('sas.admin_staff'))


# 20. Delete staff
@sas_bp.route('/admin/staff/<int:sid>/delete', methods=['POST'])
@admin_required
def admin_staff_delete(sid):
    db = get_db()
    staff = db.get(SASStaff, sid)
    if not staff:
        abort(404)

    db.delete(staff)

    try:
        db.commit()
        flash(_t('تم حذف الموظف', 'Staff deleted'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ أثناء الحذف', 'Error deleting staff'), 'danger')

    return redirect(url_for('sas.admin_staff'))


# 20b. Import staff from CSV
@sas_bp.route('/admin/staff/import', methods=['POST'])
@admin_required
def admin_staff_import():
    """Import staff from CSV"""
    db = get_db()
    cfg = _get_config()
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400

    raw = f.read()
    for enc in ('utf-8-sig', 'cp1256', 'latin-1'):
        try:
            text = raw.decode(enc)
            break
        except:
            continue
    else:
        return jsonify({'error': 'Cannot decode file'}), 400

    reader = csv.DictReader(io.StringIO(text))
    created = 0
    errors = []
    for i, row in enumerate(reader, 2):
        name = (row.get('name') or row.get('\u0627\u0644\u0627\u0633\u0645') or '').strip()
        if not name:
            errors.append(f'Row {i}: missing name')
            continue
        code = _gen_staff_code()
        while db.query(SASStaff).filter(SASStaff.staff_code == code).first():
            code = _gen_staff_code()
        staff = SASStaff(
            config_id=cfg.id,
            name=name,
            name_en=(row.get('name_en') or row.get('\u0627\u0644\u0627\u0633\u0645 \u0628\u0627\u0644\u0625\u0646\u062c\u0644\u064a\u0632\u064a\u0629') or '').strip(),
            email=(row.get('email') or row.get('\u0627\u0644\u0628\u0631\u064a\u062f') or '').strip(),
            phone=(row.get('phone') or row.get('\u0627\u0644\u0647\u0627\u062a\u0641') or '').strip(),
            staff_code=code,
            role=(row.get('role') or row.get('\u0627\u0644\u062f\u0648\u0631') or 'supervisor').strip(),
        )
        db.add(staff)
        created += 1
    try:
        db.commit()
    except Exception:
        db.rollback()
        return jsonify({'error': _t('فشل حفظ البيانات', 'Failed to save data')}), 500
    return jsonify({'ok': True, 'created': created, 'errors': errors})


# 20c. Download CSV template for staff import
@sas_bp.route('/admin/staff/template')
@admin_required
def admin_staff_template():
    """Download CSV template for staff import"""
    header = 'name,name_en,email,phone,role\n\u0627\u0644\u0627\u0633\u0645,\u0627\u0644\u0627\u0633\u0645 \u0628\u0627\u0644\u0625\u0646\u062c\u0644\u064a\u0632\u064a\u0629,\u0627\u0644\u0628\u0631\u064a\u062f,\u0627\u0644\u0647\u0627\u062a\u0641,\u0627\u0644\u062f\u0648\u0631\n'
    return Response(header, mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=sas_staff_template.csv'})


# 20d. Export staff list as CSV
@sas_bp.route('/admin/staff/export')
@admin_required
def admin_staff_export():
    """Export staff list as CSV"""
    db = get_db()
    cfg = _get_config()
    staff_list = db.query(SASStaff).filter(SASStaff.config_id == cfg.id).all()

    def generate():
        yield 'Name,Name EN,Email,Phone,Code,Role,Stage,Active\n'
        for s in staff_list:
            stage_name = s.stage.name if s.stage else ''
            yield f'"{s.name}","{s.name_en or ""}","{s.email or ""}","{s.phone or ""}","{s.staff_code}","{s.role}","{stage_name}","{1 if s.is_active else 0}"\n'

    return Response(generate(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=sas_staff_export.csv'})


# 20e. Regenerate a staff member's login code
@sas_bp.route('/admin/staff/<int:sid>/regenerate-code', methods=['POST'])
@admin_required
def admin_staff_regenerate_code(sid):
    """Regenerate a staff member's login code"""
    db = get_db()
    staff = db.get(SASStaff, sid)
    if not staff:
        return jsonify({'error': 'not found'}), 404
    code = _gen_staff_code()
    while db.query(SASStaff).filter(SASStaff.staff_code == code).first():
        code = _gen_staff_code()
    staff.staff_code = code
    db.commit()
    return jsonify({'ok': True, 'new_code': code})


# 20f. Manually send a staff member's login code by email
@sas_bp.route('/admin/staff/<int:sid>/send-code', methods=['POST'])
@admin_required
def admin_staff_send_code(sid):
    """Manually email a staff member their portal login code (never sent automatically)."""
    db = get_db()
    staff = db.get(SASStaff, sid)
    if not staff:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    if not staff.email:
        return jsonify({'ok': False, 'error': _t('لا يوجد بريد إلكتروني لهذا الموظف', 'This staff member has no email on file')}), 400

    from utils.email_helper import send_staff_login_code
    portal_url = url_for('sas.portal_home', code=staff.staff_code, _external=True)
    lang = get_lang()
    try:
        ok = send_staff_login_code(staff.email, staff.name, staff.staff_code, portal_url, lang)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

    if not ok:
        return jsonify({'ok': False, 'error': _t('تعذر إرسال البريد', 'Failed to send email')}), 500
    return jsonify({'ok': True})


# 21. Student list
@sas_bp.route('/admin/students')
@admin_required
def admin_students():
    db = get_db()
    cfg = _get_config()

    stage_id = request.args.get('stage_id', type=int)
    class_id = request.args.get('class_id', type=int)
    section_id = request.args.get('section_id', type=int)

    query = db.query(SASStudent).options(
        joinedload(SASStudent.section)
        .joinedload(SASSection.sas_class)
        .joinedload(SASClass.stage)
    )

    if section_id:
        query = query.filter(SASStudent.section_id == section_id)
    elif class_id:
        query = query.join(SASSection).filter(SASSection.class_id == class_id)
    elif stage_id:
        query = query.join(SASSection).join(SASClass).filter(SASClass.stage_id == stage_id)

    students = query.order_by(SASStudent.name).all()
    stages = db.query(SASStage).filter(SASStage.config_id == cfg.id).order_by(SASStage.order_num).all()
    stages_json = [_stage_to_dict(s) for s in stages]

    return render_template(
        'sas/admin/students.html',
        config=cfg,
        students=students,
        stages=stages,
        stages_json=stages_json,
        stage_id=stage_id,
        class_id=class_id,
        section_id=section_id,
    )


# 21b. Delete a student (admin only)
@sas_bp.route('/admin/student/<int:student_id>/delete', methods=['POST'])
@admin_required
def admin_student_delete(student_id):
    db = get_db()
    student = db.get(SASStudent, student_id)
    if not student:
        return jsonify({'error': 'not found'}), 404
    try:
        db.delete(student)
        db.commit()
        return jsonify({'ok': True})
    except Exception:
        db.rollback()
        return jsonify({'error': _t('فشل حذف الطالب', 'Failed to delete student')}), 500


@sas_bp.route('/admin/students/bulk-delete', methods=['POST'])
@admin_required
def admin_students_bulk_delete():
    db = get_db()
    data = request.get_json(silent=True)
    if not data or 'ids' not in data:
        return jsonify({'ok': False, 'error': 'No IDs provided'}), 400
    ids = [int(i) for i in data['ids'] if str(i).isdigit()]
    if not ids:
        return jsonify({'ok': False, 'error': 'No valid IDs'}), 400
    deleted = db.query(SASStudent).filter(SASStudent.id.in_(ids)).delete(synchronize_session='fetch')
    try:
        db.commit()
        return jsonify({'ok': True, 'deleted': deleted})
    except Exception as e:
        db.rollback()
        current_app.logger.exception(f'Bulk delete failed: {e}')
        return jsonify({'ok': False, 'error': 'Database error'}), 500


# 22. CSV import students
@sas_bp.route('/admin/students/import', methods=['POST'])
@admin_required
def admin_students_import():
    db = get_db()
    cfg = _get_config()

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': _t('لم يتم تحديد ملف', 'No file selected')}), 400

    raw = file.read()

    # Try multiple encodings
    content = None
    for encoding in ('utf-8-sig', 'utf-8', 'cp1256', 'latin-1'):
        try:
            content = raw.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if content is None:
        return jsonify({'success': False, 'error': _t('تعذر قراءة الملف', 'Could not read file')}), 400

    reader = csv.DictReader(io.StringIO(content))
    success_count = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            student_number = (row.get('student_number') or '').strip()
            name = (row.get('name') or '').strip()
            name_en = (row.get('name_en') or '').strip()
            guardian_name = (row.get('guardian_name') or '').strip()
            guardian_phone = (row.get('guardian_phone') or '').strip()
            guardian_email = (row.get('guardian_email') or '').strip()
            stage_name = (row.get('stage') or '').strip()
            class_name = (row.get('class') or '').strip()
            section_name = (row.get('section') or '').strip()

            if not name or not stage_name or not class_name or not section_name:
                errors.append({
                    'row': row_num,
                    'error': _t('حقول مطلوبة مفقودة', 'Missing required fields'),
                })
                continue

            # Find or create stage
            stage = db.query(SASStage).filter(
                SASStage.config_id == cfg.id,
                or_(SASStage.name == stage_name, SASStage.name_en == stage_name),
            ).first()
            if not stage:
                max_order = db.query(func.max(SASStage.order_num)).filter(
                    SASStage.config_id == cfg.id
                ).scalar() or 0
                stage = SASStage(
                    config_id=cfg.id,
                    name=stage_name,
                    name_en=stage_name,
                    order_num=max_order + 1,
                )
                db.add(stage)
                db.flush()

            # Find or create class
            cls = db.query(SASClass).filter(
                SASClass.stage_id == stage.id,
                or_(SASClass.name == class_name, SASClass.name_en == class_name),
            ).first()
            if not cls:
                max_order = db.query(func.max(SASClass.order_num)).filter(
                    SASClass.stage_id == stage.id
                ).scalar() or 0
                cls = SASClass(
                    stage_id=stage.id,
                    name=class_name,
                    name_en=class_name,
                    order_num=max_order + 1,
                )
                db.add(cls)
                db.flush()

            # Find or create section
            section = db.query(SASSection).filter(
                SASSection.class_id == cls.id,
                or_(SASSection.name == section_name, SASSection.name_en == section_name),
            ).first()
            if not section:
                max_order = db.query(func.max(SASSection.order_num)).filter(
                    SASSection.class_id == cls.id
                ).scalar() or 0
                section = SASSection(
                    class_id=cls.id,
                    name=section_name,
                    name_en=section_name,
                    order_num=max_order + 1,
                )
                db.add(section)
                db.flush()

            # Create student (skip if student_number already exists in this section)
            if student_number:
                existing = db.query(SASStudent).filter(
                    SASStudent.student_number == student_number,
                    SASStudent.section_id == section.id,
                ).first()
                if existing:
                    errors.append({
                        'row': row_num,
                        'error': _t(
                            f'الطالب برقم {student_number} موجود مسبقاً',
                            f'Student {student_number} already exists',
                        ),
                    })
                    continue

            student = SASStudent(
                section_id=section.id,
                student_number=student_number,
                name=name,
                name_en=name_en,
                guardian_name=guardian_name,
                guardian_phone=guardian_phone,
                guardian_email=guardian_email,
                is_active=True,
            )
            db.add(student)
            success_count += 1

        except Exception as e:
            errors.append({'row': row_num, 'error': str(e)})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({
        'success': True,
        'imported': success_count,
        'errors': errors,
    })


# 23. CSV template download
@sas_bp.route('/admin/students/template')
@admin_required
def admin_students_template():
    header = 'student_number,name,name_en,guardian_name,guardian_phone,guardian_email,stage,class,section\n'
    sample = '1001,أحمد محمد,Ahmed Mohammed,محمد أحمد,0501234567,parent@email.com,المرحلة الابتدائية,الصف الأول,شعبة أ\n'

    output = header + sample
    return Response(
        '\ufeff' + output,  # BOM for Excel compatibility
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=sas_students_template.csv'},
    )


# 23b. CSV template for class upload
@sas_bp.route('/admin/students/template/class')
@admin_required
def admin_students_template_class():
    header = 'section,student_number,name,name_en,guardian_name,guardian_phone,guardian_email\n'
    sample = '\u0634\u0639\u0628\u0629 \u0623,1001,\u0623\u062d\u0645\u062f \u0645\u062d\u0645\u062f,Ahmed Mohammed,\u0645\u062d\u0645\u062f \u0623\u062d\u0645\u062f,0501234567,parent@email.com\n'
    output = header + sample
    return Response(
        '\ufeff' + output,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=sas_class_upload_template.csv'},
    )


# 23c. CSV template for stage upload
@sas_bp.route('/admin/students/template/stage')
@admin_required
def admin_students_template_stage():
    header = 'class,section,student_number,name,name_en,guardian_name,guardian_phone,guardian_email\n'
    sample = '\u0627\u0644\u0635\u0641 \u0627\u0644\u0623\u0648\u0644,\u0634\u0639\u0628\u0629 \u0623,1001,\u0623\u062d\u0645\u062f \u0645\u062d\u0645\u062f,Ahmed Mohammed,\u0645\u062d\u0645\u062f \u0623\u062d\u0645\u062f,0501234567,parent@email.com\n'
    output = header + sample
    return Response(
        '\ufeff' + output,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=sas_stage_upload_template.csv'},
    )


# 23d. Manual student add
@sas_bp.route('/admin/students/add', methods=['POST'])
@admin_required
def admin_student_add():
    db = get_db()
    section_id = request.form.get('section_id', type=int)
    if not section_id:
        flash(_t('\u064a\u0631\u062c\u0649 \u0627\u062e\u062a\u064a\u0627\u0631 \u0627\u0644\u0634\u0639\u0628\u0629', 'Please select a section'), 'danger')
        return redirect(url_for('sas.admin_students'))
    student = SASStudent(
        section_id=section_id,
        student_number=request.form.get('student_number', '').strip(),
        name=request.form.get('name', '').strip(),
        name_en=request.form.get('name_en', '').strip(),
        guardian_name=request.form.get('guardian_name', '').strip(),
        guardian_phone=request.form.get('guardian_phone', '').strip(),
        guardian_email=request.form.get('guardian_email', '').strip(),
    )
    db.add(student)
    db.commit()
    flash(_t('\u062a\u0645 \u0625\u0636\u0627\u0641\u0629 \u0627\u0644\u0637\u0627\u0644\u0628', 'Student added'), 'success')
    return redirect(url_for('sas.admin_students'))


# 24. Stages / classes / sections hierarchy (Year → Semester → Stage → Class → Section)
@sas_bp.route('/admin/stages')
@admin_required
def admin_stages():
    db = get_db()
    cfg = _get_config()

    years = (
        db.query(SASYear)
        .filter(SASYear.config_id == cfg.id)
        .options(
            joinedload(SASYear.semesters)
            .joinedload(SASSemester.stages)
            .joinedload(SASStage.classes)
            .joinedload(SASClass.sections)
        )
        .order_by(SASYear.order_num)
        .all()
    )

    return render_template('sas/admin/stages.html', config=cfg, years=years)


# 25. Save hierarchy from JSON (AJAX) — Year → Semester → Stage → Class → Section
@sas_bp.route('/admin/stages/save', methods=['POST'])
@admin_required
def admin_stages_save():
    db = get_db()
    cfg = _get_config()
    data = request.get_json(silent=True)

    if not data or 'years' not in data:
        return jsonify({'success': False, 'error': 'Invalid data'}), 400

    try:
        # Collect existing IDs to detect deletions
        existing_year_ids = {y.id for y in db.query(SASYear).filter(SASYear.config_id == cfg.id).all()}
        existing_semester_ids = set()
        existing_stage_ids = set()
        existing_class_ids = set()
        existing_section_ids = set()

        for sem_row in db.query(SASSemester).join(SASYear).filter(SASYear.config_id == cfg.id).all():
            existing_semester_ids.add(sem_row.id)
        for stg_row in db.query(SASStage).join(SASSemester).join(SASYear).filter(SASYear.config_id == cfg.id).all():
            existing_stage_ids.add(stg_row.id)
        # Also include stages linked directly to config (legacy, no semester)
        for stg_row in db.query(SASStage).filter(SASStage.config_id == cfg.id, SASStage.semester_id == None).all():
            existing_stage_ids.add(stg_row.id)
        for cls_row in db.query(SASClass).join(SASStage).filter(SASStage.config_id == cfg.id).all():
            existing_class_ids.add(cls_row.id)
        for sec_row in db.query(SASSection).join(SASClass).join(SASStage).filter(SASStage.config_id == cfg.id).all():
            existing_section_ids.add(sec_row.id)

        incoming_year_ids = set()
        incoming_semester_ids = set()
        incoming_stage_ids = set()
        incoming_class_ids = set()
        incoming_section_ids = set()

        for y_idx, y_data in enumerate(data['years']):
            year_id = y_data.get('id')
            if year_id:
                year = db.get(SASYear, year_id)
                if not year:
                    continue
                year.name = y_data.get('name', year.name)
                year.name_en = y_data.get('name_en', year.name_en)
                year.order_num = y_idx
                incoming_year_ids.add(year.id)
            else:
                year = SASYear(
                    config_id=cfg.id,
                    name=y_data.get('name', ''),
                    name_en=y_data.get('name_en', ''),
                    order_num=y_idx,
                )
                db.add(year)
                db.flush()
                incoming_year_ids.add(year.id)

            for sem_idx, sem_data in enumerate(y_data.get('semesters', [])):
                semester_id = sem_data.get('id')
                if semester_id:
                    semester = db.get(SASSemester, semester_id)
                    if not semester:
                        continue
                    semester.name = sem_data.get('name', semester.name)
                    semester.name_en = sem_data.get('name_en', semester.name_en)
                    semester.order_num = sem_idx
                    semester.year_id = year.id
                    semester.start_date = (sem_data.get('start_date') or '').strip() or None
                    semester.end_date = (sem_data.get('end_date') or '').strip() or None
                    incoming_semester_ids.add(semester.id)
                else:
                    semester = SASSemester(
                        year_id=year.id,
                        name=sem_data.get('name', ''),
                        name_en=sem_data.get('name_en', ''),
                        order_num=sem_idx,
                        start_date=(sem_data.get('start_date') or '').strip() or None,
                        end_date=(sem_data.get('end_date') or '').strip() or None,
                    )
                    db.add(semester)
                    db.flush()
                    incoming_semester_ids.add(semester.id)

                for s_idx, s_data in enumerate(sem_data.get('stages', [])):
                    stage_id = s_data.get('id')
                    if stage_id:
                        stage = db.get(SASStage, stage_id)
                        if not stage:
                            continue
                        stage.name = s_data.get('name', stage.name)
                        stage.name_en = s_data.get('name_en', stage.name_en)
                        stage.order_num = s_idx
                        stage.semester_id = semester.id
                        stage.config_id = cfg.id
                        incoming_stage_ids.add(stage.id)
                    else:
                        stage = SASStage(
                            config_id=cfg.id,
                            semester_id=semester.id,
                            name=s_data.get('name', ''),
                            name_en=s_data.get('name_en', ''),
                            order_num=s_idx,
                        )
                        db.add(stage)
                        db.flush()
                        incoming_stage_ids.add(stage.id)

                    for c_idx, c_data in enumerate(s_data.get('classes', [])):
                        class_id = c_data.get('id')
                        if class_id:
                            cls = db.get(SASClass, class_id)
                            if not cls:
                                continue
                            cls.name = c_data.get('name', cls.name)
                            cls.name_en = c_data.get('name_en', cls.name_en)
                            cls.order_num = c_idx
                            cls.stage_id = stage.id
                            incoming_class_ids.add(cls.id)
                        else:
                            cls = SASClass(
                                stage_id=stage.id,
                                name=c_data.get('name', ''),
                                name_en=c_data.get('name_en', ''),
                                order_num=c_idx,
                            )
                            db.add(cls)
                            db.flush()
                            incoming_class_ids.add(cls.id)

                        for sec_idx, sec_data in enumerate(c_data.get('sections', [])):
                            section_id = sec_data.get('id')
                            if section_id:
                                sec = db.get(SASSection, section_id)
                                if not sec:
                                    continue
                                sec.name = sec_data.get('name', sec.name)
                                sec.name_en = sec_data.get('name_en', sec.name_en)
                                sec.order_num = sec_idx
                                sec.class_id = cls.id
                                incoming_section_ids.add(sec.id)
                            else:
                                sec = SASSection(
                                    class_id=cls.id,
                                    name=sec_data.get('name', ''),
                                    name_en=sec_data.get('name_en', ''),
                                    order_num=sec_idx,
                                )
                                db.add(sec)
                                db.flush()
                                incoming_section_ids.add(sec.id)

        # Delete removed entities (deepest first)
        for sec_id in existing_section_ids - incoming_section_ids:
            sec = db.get(SASSection, sec_id)
            if sec:
                db.delete(sec)
        for cls_id in existing_class_ids - incoming_class_ids:
            cls = db.get(SASClass, cls_id)
            if cls:
                db.delete(cls)
        for stage_id in existing_stage_ids - incoming_stage_ids:
            stg = db.get(SASStage, stage_id)
            if stg:
                db.delete(stg)
        for sem_id in existing_semester_ids - incoming_semester_ids:
            sem = db.get(SASSemester, sem_id)
            if sem:
                db.delete(sem)
        for year_id in existing_year_ids - incoming_year_ids:
            yr = db.get(SASYear, year_id)
            if yr:
                db.delete(yr)

        db.commit()
        return jsonify({'success': True})

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Period Schedule (per stage per day) ──────────────────────────
DAY_NAMES_AR = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
DAY_NAMES_EN = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

@sas_bp.route('/admin/periods/<int:stage_id>')
@admin_required
def admin_periods(stage_id):
    db = get_db()
    cfg = _get_config()
    stage = db.get(SASStage, stage_id)
    if not stage:
        abort(404)

    classes = (
        db.query(SASClass)
        .filter(SASClass.stage_id == stage_id)
        .order_by(SASClass.order_num)
        .all()
    )

    # Which classes currently have their own override (vs using the stage default)?
    override_class_ids = {
        row[0] for row in
        db.query(SASPeriod.class_id)
        .filter(SASPeriod.stage_id == stage_id, SASPeriod.class_id.isnot(None))
        .distinct()
        .all()
    }

    # Resolve requested scope: ?class_id=<id> for an override, absent/blank for the default
    class_id_param = request.args.get('class_id', type=int)
    current_class = None
    if class_id_param:
        current_class = next((c for c in classes if c.id == class_id_param), None)
    scope_class_id = current_class.id if current_class else None

    periods = (
        db.query(SASPeriod)
        .filter(SASPeriod.stage_id == stage_id, SASPeriod.class_id == scope_class_id)
        .order_by(SASPeriod.day_of_week, SASPeriod.order_num)
        .all()
    )
    by_day = {}
    for p in periods:
        by_day.setdefault(p.day_of_week, []).append(p)

    return render_template('sas/admin/periods.html', config=cfg, stage=stage,
                           by_day=by_day, day_names_ar=DAY_NAMES_AR, day_names_en=DAY_NAMES_EN,
                           classes=classes, current_class=current_class,
                           override_class_ids=override_class_ids)


@sas_bp.route('/admin/periods/<int:stage_id>/save', methods=['POST'])
@admin_required
def admin_periods_save(stage_id):
    db = get_db()
    stage = db.get(SASStage, stage_id)
    if not stage:
        return jsonify({'ok': False, 'error': 'Stage not found'}), 404
    data = request.get_json(silent=True)
    if not data or 'days' not in data:
        return jsonify({'ok': False, 'error': 'Invalid data'}), 400

    # targets: list of scopes to write this same schedule to in one save.
    # 'default' -> stage-wide (class_id NULL); an integer -> that class's override.
    targets = data.get('targets') or ['default']
    valid_class_ids = {
        row[0] for row in
        db.query(SASClass.id).filter(SASClass.stage_id == stage_id).all()
    }
    scope_class_ids = []
    for t in targets:
        if t == 'default':
            scope_class_ids.append(None)
        else:
            try:
                cid = int(t)
            except (TypeError, ValueError):
                continue
            if cid in valid_class_ids:
                scope_class_ids.append(cid)
    if not scope_class_ids:
        scope_class_ids = [None]

    try:
        for scope_class_id in scope_class_ids:
            # Delete existing periods for this exact scope only
            db.query(SASPeriod).filter(
                SASPeriod.stage_id == stage_id,
                SASPeriod.class_id == scope_class_id,
            ).delete()
            for day_num_str, items in data['days'].items():
                day_num = int(day_num_str)
                for idx, item in enumerate(items):
                    p = SASPeriod(
                        stage_id=stage_id,
                        class_id=scope_class_id,
                        day_of_week=day_num,
                        order_num=idx,
                        period_type=item.get('type', 'period'),
                        label=item.get('label', ''),
                        label_en=item.get('label_en', ''),
                        start_time=item.get('start', ''),
                        end_time=item.get('end', ''),
                    )
                    db.add(p)
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


@sas_bp.route('/admin/periods/<int:stage_id>/class/<int:class_id>/reset', methods=['POST'])
@admin_required
def admin_periods_reset_class(stage_id, class_id):
    """Remove a class's period override so it falls back to the stage default."""
    db = get_db()
    stage = db.get(SASStage, stage_id)
    if not stage:
        return jsonify({'ok': False, 'error': 'Stage not found'}), 404
    try:
        db.query(SASPeriod).filter(
            SASPeriod.stage_id == stage_id,
            SASPeriod.class_id == class_id,
        ).delete()
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Timetable (per section — subject + teacher per period) ──────
@sas_bp.route('/admin/timetable/<int:section_id>')
@admin_required
def admin_timetable(section_id):
    db = get_db()
    cfg = _get_config()
    section = db.get(SASSection, section_id)
    if not section:
        abort(404)
    cls = section.sas_class
    stage = cls.stage if cls else None
    if not stage:
        abort(404)
    # Get periods: use this class's own override if it has one, otherwise
    # fall back to the stage-wide default schedule.
    periods = (
        db.query(SASPeriod)
        .filter(SASPeriod.stage_id == stage.id, SASPeriod.class_id == cls.id)
        .order_by(SASPeriod.day_of_week, SASPeriod.order_num)
        .all()
    )
    if not periods:
        periods = (
            db.query(SASPeriod)
            .filter(SASPeriod.stage_id == stage.id, SASPeriod.class_id.is_(None))
            .order_by(SASPeriod.day_of_week, SASPeriod.order_num)
            .all()
        )
    by_day = {}
    for p in periods:
        by_day.setdefault(p.day_of_week, []).append(p)
    # Get timetable entries
    entries = (
        db.query(SASTimetable)
        .filter(SASTimetable.section_id == section_id)
        .all()
    )
    entry_map = {e.period_id: e for e in entries}
    return render_template('sas/admin/timetable.html', config=cfg, section=section,
                           cls=cls, stage=stage, by_day=by_day, entry_map=entry_map,
                           day_names_ar=DAY_NAMES_AR, day_names_en=DAY_NAMES_EN,
                           stage_id=stage.id)


@sas_bp.route('/admin/timetable/<int:section_id>/save', methods=['POST'])
@admin_required
def admin_timetable_save(section_id):
    db = get_db()
    section = db.get(SASSection, section_id)
    if not section:
        return jsonify({'ok': False, 'error': 'Section not found'}), 404
    data = request.get_json(silent=True)
    if not data or 'entries' not in data:
        return jsonify({'ok': False, 'error': 'Invalid data'}), 400
    try:
        # Delete existing timetable for this section
        db.query(SASTimetable).filter(SASTimetable.section_id == section_id).delete()
        for item in data['entries']:
            period_id = item.get('period_id')
            subject = (item.get('subject') or '').strip()
            teacher = (item.get('teacher') or '').strip()
            if period_id and (subject or teacher):
                t_entry = SASTimetable(
                    section_id=section_id,
                    period_id=int(period_id),
                    subject_name=subject,
                    teacher_name=teacher,
                    notes=(item.get('notes') or '').strip(),
                )
                db.add(t_entry)
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


# 26. Multi-field comparison (supports up to 3 sides)
@sas_bp.route('/admin/compare')
@admin_required
def admin_compare():
    db = get_db()
    cfg = _get_config()

    field1 = request.args.get('field1', '')
    field2 = request.args.get('field2', '')
    field3 = request.args.get('field3', '')
    value1 = request.args.get('value1', '')
    value2 = request.args.get('value2', '')
    value3 = request.args.get('value3', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    if date_from and date_to and date_from > date_to:
        flash(_t('تاريخ البداية يجب أن يكون قبل تاريخ النهاية',
                  'Start date must be before end date'), 'warning')
        date_from, date_to = date_to, date_from

    results = None

    if field1 and value1:
        def _build_compare_query(field, value):
            """Build a count query filtered by field=value and optional date range.
            For class_leave_type, queries SASClassLeave instead of SASRecord."""

            # Class leave type queries the SASClassLeave table
            if field == 'class_leave_type':
                q = db.query(func.count(SASClassLeave.id)).filter(SASClassLeave.leave_type == value)
                if date_from:
                    q = q.filter(SASClassLeave.leave_date >= date_from)
                if date_to:
                    q = q.filter(SASClassLeave.leave_date <= date_to)
                return q.scalar() or 0

            q = db.query(func.count(SASRecord.id))
            if field == 'stage':
                q = q.join(SASStudent, SASStudent.id == SASRecord.student_id)\
                     .join(SASSection, SASSection.id == SASStudent.section_id)\
                     .join(SASClass, SASClass.id == SASSection.class_id)\
                     .join(SASStage, SASStage.id == SASClass.stage_id)\
                     .filter(or_(SASStage.name == value, SASStage.name_en == value, SASStage.id == (int(value) if value.isdigit() else 0)))
            elif field == 'class':
                q = q.join(SASStudent, SASStudent.id == SASRecord.student_id)\
                     .join(SASSection, SASSection.id == SASStudent.section_id)\
                     .join(SASClass, SASClass.id == SASSection.class_id)\
                     .filter(or_(SASClass.name == value, SASClass.name_en == value, SASClass.id == (int(value) if value.isdigit() else 0)))
            elif field == 'section':
                q = q.join(SASStudent, SASStudent.id == SASRecord.student_id)\
                     .join(SASSection, SASSection.id == SASStudent.section_id)\
                     .filter(or_(SASSection.name == value, SASSection.name_en == value, SASSection.id == (int(value) if value.isdigit() else 0)))
            elif field == 'record_type':
                q = q.filter(SASRecord.record_type == value)
            elif field == 'month':
                try:
                    month_num = int(value)
                    q = q.filter(extract('month', SASRecord.record_date) == month_num)
                except (ValueError, TypeError):
                    pass
            elif field == 'semester':
                # Semester 1 = months 9-1, Semester 2 = months 2-6
                if value == '1':
                    q = q.filter(or_(
                        extract('month', SASRecord.record_date) >= 9,
                        extract('month', SASRecord.record_date) <= 1,
                    ))
                elif value == '2':
                    q = q.filter(
                        extract('month', SASRecord.record_date) >= 2,
                        extract('month', SASRecord.record_date) <= 6,
                    )
            elif field == 'year':
                try:
                    q = q.filter(extract('year', SASRecord.record_date) == int(value))
                except (ValueError, TypeError):
                    pass
            elif field == 'staff':
                try:
                    staff_id = int(value)
                    q = q.filter(SASRecord.staff_id == staff_id)
                except (ValueError, TypeError):
                    q = q.join(SASStaff, SASStaff.id == SASRecord.staff_id)\
                         .filter(or_(SASStaff.name.contains(value), SASStaff.name_en.contains(value)))
            elif field == 'student':
                q = q.join(SASStudent, SASStudent.id == SASRecord.student_id)\
                     .filter(or_(SASStudent.name.contains(value), SASStudent.name_en.contains(value), SASStudent.id == (int(value) if value.isdigit() else 0)))
            elif field == 'day_of_week':
                try:
                    dow = int(value)  # 0=Sunday .. 6=Saturday
                    q = q.filter(extract('dow', SASRecord.record_date) == dow)
                except (ValueError, TypeError):
                    pass

            if date_from:
                q = q.filter(SASRecord.record_date >= date_from)
            if date_to:
                q = q.filter(SASRecord.record_date <= date_to)

            return q.scalar() or 0

        count1 = _build_compare_query(field1, value1)
        count2 = _build_compare_query(field2, value2) if field2 and value2 else 0
        count3 = _build_compare_query(field3, value3) if field3 and value3 else None

        results = {
            'field1': field1, 'value1': value1, 'count1': count1,
            'field2': field2, 'value2': value2, 'count2': count2,
        }
        if field3 and value3:
            results['field3'] = field3
            results['value3'] = value3
            results['count3'] = count3

    stages = db.query(SASStage).filter(SASStage.config_id == cfg.id).order_by(SASStage.order_num).all()
    staff_list = db.query(SASStaff).filter(SASStaff.config_id == cfg.id, SASStaff.is_active == True).order_by(SASStaff.name).all()
    stages_json = [_stage_to_dict(s) for s in stages]
    staff_json = [_staff_to_dict(s) for s in staff_list]

    today = date.today()
    now_month = str(today.month)
    prev_month = str(today.month - 1 if today.month > 1 else 12)

    # Build class leave types for JS
    cl_types_json = [{'value': k, 'label_ar': v[0], 'label_en': v[1]} for k, v in CLASS_LEAVE_TYPES.items()]

    return render_template(
        'sas/admin/compare.html',
        config=cfg,
        results=results,
        stages=stages,
        stages_json=stages_json,
        staff_list=staff_list,
        staff_json=staff_json,
        cl_types_json=cl_types_json,
        field1=field1, field2=field2, field3=field3,
        value1=value1, value2=value2, value3=value3,
        date_from=date_from, date_to=date_to,
        now_month=now_month, prev_month=prev_month,
    )


def _apply_report_scope(db, query, student_id_col, stage_id=None, class_id=None, section_id=None, student_id=None):
    """Narrow a SASRecord/SASClassLeave query to a student, a section, a
    class, or a stage — whichever is the most specific one given. Pass the
    model's own student_id column (e.g. SASRecord.student_id)."""
    if student_id:
        return query.filter(student_id_col == student_id)
    if section_id:
        return query.filter(
            student_id_col.in_(db.query(SASStudent.id).filter(SASStudent.section_id == section_id))
        )
    if class_id:
        return query.filter(
            student_id_col.in_(
                db.query(SASStudent.id).join(SASSection).filter(SASSection.class_id == class_id)
            )
        )
    if stage_id:
        return query.filter(
            student_id_col.in_(
                db.query(SASStudent.id).join(SASSection).join(SASClass)
                .filter(SASClass.stage_id == stage_id)
            )
        )
    return query


# 27. Export records (CSV stream or PDF redirect)
@sas_bp.route('/admin/export')
@admin_required
def admin_export():
    db = get_db()
    fmt = request.args.get('format', 'csv')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    stage_id = request.args.get('stage_id', type=int)
    class_id = request.args.get('class_id', type=int)
    section_id = request.args.get('section_id', type=int)
    student_id = request.args.get('student_id', type=int)
    record_type = request.args.get('record_type', '')

    query = db.query(SASRecord).options(
        joinedload(SASRecord.student).joinedload(SASStudent.section)
        .joinedload(SASSection.sas_class).joinedload(SASClass.stage),
        joinedload(SASRecord.staff),
    )

    if date_from:
        query = query.filter(SASRecord.record_date >= date_from)
    if date_to:
        query = query.filter(SASRecord.record_date <= date_to)
    if record_type:
        query = query.filter(SASRecord.record_type == record_type)
    query = _apply_report_scope(db, query, SASRecord.student_id, stage_id, class_id, section_id, student_id)

    records = query.order_by(SASRecord.record_date.desc()).all()

    if fmt == 'pdf':
        return redirect(url_for(
            'sas.admin_print',
            date_from=date_from,
            date_to=date_to,
            stage_id=stage_id or '',
            class_id=class_id or '',
            section_id=section_id or '',
            student_id=student_id or '',
            record_type=record_type,
        ))

    # CSV streaming
    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        # BOM for Excel
        yield '\ufeff'
        writer.writerow([
            'Record ID', 'Student Number', 'Student Name', 'Student Name (EN)',
            'Stage', 'Class', 'Section', 'Date', 'Type', 'Status',
            'Staff', 'Notes', 'Created At',
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for rec in records:
            student = rec.student
            section = student.section if student else None
            cls = section.sas_class if section else None
            stage = cls.stage if cls else None
            writer.writerow([
                rec.id,
                student.student_number if student else '',
                student.name if student else '',
                student.name_en if student else '',
                stage.name if stage else '',
                cls.name if cls else '',
                section.name if section else '',
                rec.record_date,
                rec.record_type,
                rec.status,
                rec.staff.name if rec.staff else '',
                rec.notes or '',
                str(rec.created_at) if rec.created_at else '',
            ])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    filename = f'sas_records_{date.today().strftime("%Y%m%d")}.csv'
    return Response(
        generate(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


# 28. Print-friendly report
@sas_bp.route('/admin/print')
@admin_required
def admin_print():
    db = get_db()
    cfg = _get_config()

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    stage_id = request.args.get('stage_id', type=int)
    class_id = request.args.get('class_id', type=int)
    section_id = request.args.get('section_id', type=int)
    student_id = request.args.get('student_id', type=int)
    record_type = request.args.get('record_type', '')
    student_q = request.args.get('student_q', '').strip()

    query = db.query(SASRecord).options(
        joinedload(SASRecord.student).joinedload(SASStudent.section)
        .joinedload(SASSection.sas_class).joinedload(SASClass.stage),
        joinedload(SASRecord.staff),
    )

    if date_from:
        query = query.filter(SASRecord.record_date >= date_from)
    if date_to:
        query = query.filter(SASRecord.record_date <= date_to)
    if record_type:
        query = query.filter(SASRecord.record_type == record_type)
    query = _apply_report_scope(db, query, SASRecord.student_id, stage_id, class_id, section_id, student_id)

    records = query.order_by(SASRecord.record_date.desc()).all()

    # Also fetch class leave records for the same date range/scope
    cl_query = db.query(SASClassLeave).options(
        joinedload(SASClassLeave.student).joinedload(SASStudent.section)
        .joinedload(SASSection.sas_class).joinedload(SASClass.stage),
        joinedload(SASClassLeave.staff),
    )
    if date_from:
        cl_query = cl_query.filter(SASClassLeave.leave_date >= date_from)
    if date_to:
        cl_query = cl_query.filter(SASClassLeave.leave_date <= date_to)
    cl_query = _apply_report_scope(db, cl_query, SASClassLeave.student_id, stage_id, class_id, section_id, student_id)
    class_leaves = cl_query.order_by(SASClassLeave.leave_date.desc()).all()

    # Data to drive the (non-printable) filter bar: stages + classes + sections
    # for cascading selects, and a student search if the admin typed a name.
    stages_list = [{'id': s.id, 'name': s.name, 'name_en': s.name_en}
                    for s in db.query(SASStage).order_by(SASStage.order_num).all()]
    classes_list = [{'id': c.id, 'name': c.name, 'name_en': c.name_en, 'stage_id': c.stage_id}
                     for c in db.query(SASClass).order_by(SASClass.order_num).all()]
    sections_list = [{'id': sec.id, 'name': sec.name, 'name_en': sec.name_en, 'class_id': sec.class_id}
                      for sec in db.query(SASSection).order_by(SASSection.order_num).all()]

    student_matches = []
    if student_q:
        student_matches = (
            db.query(SASStudent)
            .filter(or_(
                SASStudent.name.contains(student_q),
                SASStudent.name_en.contains(student_q),
                SASStudent.student_number.contains(student_q),
            ))
            .limit(20)
            .all()
        )
    selected_student = db.get(SASStudent, student_id) if student_id else None

    # Human-readable filters summary shown on the report itself
    filter_parts = []
    if selected_student:
        filter_parts.append((f'الطالب: {selected_student.name}', f'Student: {selected_student.name_en or selected_student.name}'))
    else:
        if section_id:
            sec = db.get(SASSection, section_id)
            if sec:
                filter_parts.append((f'الشعبة: {sec.name}', f'Section: {sec.name_en or sec.name}'))
        elif class_id:
            cls = db.get(SASClass, class_id)
            if cls:
                filter_parts.append((f'الصف: {cls.name}', f'Class: {cls.name_en or cls.name}'))
        elif stage_id:
            stg = db.get(SASStage, stage_id)
            if stg:
                filter_parts.append((f'المرحلة: {stg.name}', f'Stage: {stg.name_en or stg.name}'))
    if record_type:
        rt_labels = {'absent': ('غياب', 'Absent'), 'late': ('تأخر', 'Late'), 'leave': ('استئذان', 'Leave'), 'other': ('أخرى', 'Other')}
        rt = rt_labels.get(record_type, (record_type, record_type))
        filter_parts.append((f'النوع: {rt[0]}', f'Type: {rt[1]}'))
    filters_text_ar = ' | '.join(p[0] for p in filter_parts)
    filters_text_en = ' | '.join(p[1] for p in filter_parts)

    return render_template(
        'sas/admin/print_report.html',
        config=cfg,
        records=records,
        class_leaves=class_leaves,
        leave_types=CLASS_LEAVE_TYPES,
        date_from=date_from,
        date_to=date_to,
        record_type=record_type,
        stage_id=stage_id,
        class_id=class_id,
        section_id=section_id,
        student_id=student_id,
        student_q=student_q,
        stages_list=stages_list,
        classes_list=classes_list,
        sections_list=sections_list,
        student_matches=student_matches,
        selected_student=selected_student,
        filters_text_ar=filters_text_ar,
        filters_text_en=filters_text_en,
    )


# ===========================================================================
# API ROUTES (JSON)
# ===========================================================================

# 29. Filtered student JSON
@sas_bp.route('/api/students')
def api_students():
    db = get_db()

    stage_id = request.args.get('stage_id', type=int)
    class_id = request.args.get('class_id', type=int)
    section_id = request.args.get('section_id', type=int)
    q = request.args.get('q', '').strip()

    query = db.query(SASStudent).options(
        joinedload(SASStudent.section)
        .joinedload(SASSection.sas_class)
        .joinedload(SASClass.stage)
    ).filter(SASStudent.is_active == True)

    if section_id:
        query = query.filter(SASStudent.section_id == section_id)
    elif class_id:
        query = query.join(SASSection).filter(SASSection.class_id == class_id)
    elif stage_id:
        query = query.join(SASSection).join(SASClass).filter(SASClass.stage_id == stage_id)

    if q:
        query = query.filter(or_(
            SASStudent.name.contains(q),
            SASStudent.name_en.contains(q),
            SASStudent.student_number.contains(q),
        ))

    students = query.order_by(SASStudent.name).limit(50).all()

    result = []
    for s in students:
        section = s.section
        cls = section.sas_class if section else None
        stage = cls.stage if cls else None
        result.append({
            'id': s.id,
            'student_number': s.student_number,
            'name': s.name,
            'name_en': s.name_en,
            'guardian_name': s.guardian_name,
            'guardian_phone': s.guardian_phone,
            'section': section.name if section else '',
            'section_en': section.name_en if section else '',
            'class': cls.name if cls else '',
            'class_en': cls.name_en if cls else '',
            'stage': stage.name if stage else '',
            'stage_en': stage.name_en if stage else '',
        })

    return jsonify({'students': result, 'total': len(result)})


# 30. Dashboard stats JSON
@sas_bp.route('/api/stats')
def api_stats():
    db = get_db()

    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    base_filter = []
    if date_from:
        base_filter.append(SASRecord.record_date >= date_from)
    if date_to:
        base_filter.append(SASRecord.record_date <= date_to)

    total_records = db.query(func.count(SASRecord.id)).filter(*base_filter).scalar() or 0

    absent_count = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_type == 'absent', *base_filter
    ).scalar() or 0

    late_count = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_type == 'late', *base_filter
    ).scalar() or 0

    leave_count = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_type == 'leave', *base_filter
    ).scalar() or 0

    pending_count = db.query(func.count(SASRecord.id)).filter(
        SASRecord.status == 'pending', *base_filter
    ).scalar() or 0

    # By type breakdown
    type_breakdown = (
        db.query(SASRecord.record_type, func.count(SASRecord.id))
        .filter(*base_filter)
        .group_by(SASRecord.record_type)
        .all()
    )

    return jsonify({
        'total_records': total_records,
        'absent': absent_count,
        'late': late_count,
        'leave': leave_count,
        'pending': pending_count,
        'by_type': {t: c for t, c in type_breakdown},
    })


# 31. Records JSON (datatable-friendly)
@sas_bp.route('/api/records')
def api_records():
    db = get_db()

    student_id = request.args.get('student_id', type=int)
    stage_id = request.args.get('stage_id', type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    record_type = request.args.get('record_type', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    per_page = min(per_page, 100)  # Cap at 100

    query = db.query(SASRecord).options(
        joinedload(SASRecord.student),
        joinedload(SASRecord.staff),
    )

    if student_id:
        query = query.filter(SASRecord.student_id == student_id)
    if stage_id:
        query = query.filter(
            SASRecord.student_id.in_(
                db.query(SASStudent.id)
                .join(SASSection)
                .join(SASClass)
                .filter(SASClass.stage_id == stage_id)
            )
        )
    if date_from:
        query = query.filter(SASRecord.record_date >= date_from)
    if date_to:
        query = query.filter(SASRecord.record_date <= date_to)
    if record_type:
        query = query.filter(SASRecord.record_type == record_type)

    total = query.count()
    records = (
        query.order_by(SASRecord.record_date.desc(), SASRecord.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    result = []
    for r in records:
        result.append({
            'id': r.id,
            'student_id': r.student_id,
            'student_name': r.student.name if r.student else '',
            'student_name_en': r.student.name_en if r.student else '',
            'student_number': r.student.student_number if r.student else '',
            'staff_name': r.staff.name if r.staff else '',
            'record_date': r.record_date,
            'record_type': r.record_type,
            'status': r.status,
            'notes': r.notes or '',
            'has_attachment': bool(r.attachment_b64),
            'created_at': str(r.created_at) if r.created_at else '',
        })

    return jsonify({
        'records': result,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    })


# ===========================================================================
# TICKER ROUTES
# ===========================================================================

# 32. Ticker management page
@sas_bp.route('/admin/ticker')
@admin_required
def admin_ticker():
    cfg = _get_config()
    ticker_data = None
    if cfg.ticker_json:
        try:
            ticker_data = json.loads(cfg.ticker_json)
        except (json.JSONDecodeError, TypeError):
            ticker_data = None

    return render_template('sas/admin/ticker.html', config=cfg, ticker_data=ticker_data)


# 33. Save ticker config
@sas_bp.route('/admin/ticker/save', methods=['POST'])
@admin_required
def admin_ticker_save():
    db = get_db()
    cfg = _get_config()

    data = request.get_json(silent=True)
    if data is not None:
        cfg.ticker_json = json.dumps(data, ensure_ascii=False)
    else:
        ticker_json = request.form.get('ticker_json', '').strip()
        if ticker_json:
            # Validate JSON
            try:
                json.loads(ticker_json)
                cfg.ticker_json = ticker_json
            except json.JSONDecodeError:
                if request.is_json:
                    return jsonify({'success': False, 'error': 'Invalid JSON'}), 400
                flash(_t('صيغة JSON غير صالحة', 'Invalid JSON format'), 'danger')
                return redirect(url_for('sas.admin_ticker'))
        else:
            cfg.ticker_json = None

    try:
        db.commit()
        if request.is_json or request.content_type == 'application/json':
            return jsonify({'success': True})
        flash(_t('تم حفظ إعدادات الشريط', 'Ticker settings saved'), 'success')
    except Exception:
        db.rollback()
        if request.is_json or request.content_type == 'application/json':
            return jsonify({'success': False, 'error': 'Database error'}), 500
        flash(_t('حدث خطأ أثناء الحفظ', 'Error saving ticker'), 'danger')

    return redirect(url_for('sas.admin_ticker'))


# ===========================================================================
# HOLIDAY APPROVAL ROUTES
# ===========================================================================

# 34. Approve/reject a holiday (manager only)
@sas_bp.route('/portal/<code>/holiday/<int:holiday_id>/approve', methods=['POST'])
def holiday_approve(code, holiday_id):
    staff = _get_staff_or_404(code)
    if not _check_perm(staff, 'approve_holiday'):
        abort(403)
    db = get_db()
    holiday = db.get(SASHoliday, holiday_id)
    if not holiday:
        abort(404)

    action = request.form.get('action', '').strip()
    if action == 'approve':
        holiday.status = 'approved'
    elif action == 'reject':
        holiday.status = 'rejected'
    else:
        flash(_t('إجراء غير صالح', 'Invalid action'), 'danger')
        return redirect(request.referrer or url_for('sas.holidays', code=code))

    holiday.approved_by = staff.id
    holiday.approved_at = datetime.utcnow()

    try:
        db.commit()
        flash(_t('تم تحديث حالة الإجازة', 'Holiday status updated'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ', 'An error occurred'), 'danger')

    return redirect(request.referrer or url_for('sas.pending', code=code))


# ===========================================================================
# CLASS LEAVE ROUTES
# ===========================================================================

# 35. Class leave list — today's records
@sas_bp.route('/portal/<code>/class-leave')
def class_leave_list(code):
    staff = _get_staff_or_404(code)
    db = get_db()
    cfg = _get_config()
    today = _today_str()

    query = db.query(SASClassLeave).options(
        joinedload(SASClassLeave.student).joinedload(SASStudent.section)
        .joinedload(SASSection.sas_class).joinedload(SASClass.stage),
        joinedload(SASClassLeave.staff),
        joinedload(SASClassLeave.approver),
    ).filter(SASClassLeave.leave_date == today)

    # Scope to staff's stage if supervisor
    if staff.role == 'supervisor' and staff.stage_id:
        query = query.filter(
            SASClassLeave.student_id.in_(
                db.query(SASStudent.id)
                .join(SASSection)
                .join(SASClass)
                .filter(SASClass.stage_id == staff.stage_id)
            )
        )

    leaves = query.order_by(SASClassLeave.created_at.desc()).all()

    # Students for the search/add form
    stages = db.query(SASStage).filter(SASStage.config_id == cfg.id).order_by(SASStage.order_num).all()
    stages_json = [_stage_to_dict(s) for s in stages]

    return render_template(
        'sas/class_leave.html',
        config=cfg,
        staff=staff,
        leaves=leaves,
        today=today,
        stages=stages,
        stages_json=stages_json,
        leave_types=CLASS_LEAVE_TYPES,
    )


# 36. Add class leave record
@sas_bp.route('/portal/<code>/class-leave/add', methods=['POST'])
def class_leave_add(code):
    staff = _get_staff_or_404(code)
    if not _check_perm(staff, 'create_class_leave'):
        abort(403)
    db = get_db()

    student_id = request.form.get('student_id', type=int)
    leave_type = request.form.get('leave_type', '').strip()
    custom_type = request.form.get('custom_type', '').strip()
    notes = request.form.get('notes', '').strip()
    leave_date = request.form.get('leave_date', _today_str()).strip()
    leave_time = request.form.get('leave_time', datetime.now().strftime('%H:%M')).strip()
    return_time = request.form.get('return_time', '').strip() or None

    if not student_id or not leave_type:
        flash(_t('يرجى تحديد الطالب وسبب الخروج', 'Please select student and leave reason'), 'danger')
        return redirect(url_for('sas.class_leave_list', code=code))

    student = db.get(SASStudent, student_id)
    if not student:
        abort(404)
    _student_in_scope(db, staff, student)

    # Handle file attachment
    attachment_b64 = None
    attachment_name = None
    file = request.files.get('attachment')
    if file and file.filename:
        attachment_name = file.filename
        attachment_b64 = base64.b64encode(file.read()).decode('utf-8')

    cl = SASClassLeave(
        student_id=student_id,
        staff_id=staff.id,
        leave_date=leave_date,
        leave_time=leave_time,
        return_time=return_time,
        leave_type=leave_type,
        custom_type=custom_type if leave_type == 'other' else None,
        status='pending',
        notes=notes,
        attachment_b64=attachment_b64,
        attachment_name=attachment_name,
    )
    db.add(cl)

    try:
        db.commit()
        flash(_t('تم تسجيل الخروج بنجاح', 'Class leave recorded successfully'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ أثناء الحفظ', 'Error saving class leave'), 'danger')

    return redirect(url_for('sas.class_leave_list', code=code))


# 37. Approve/reject class leave (secretary + manager)
@sas_bp.route('/portal/<code>/class-leave/<int:lid>/approve', methods=['POST'])
def class_leave_approve(code, lid):
    staff = _get_staff_or_404(code)
    if not _check_perm(staff, 'approve_class_leave'):
        abort(403)
    db = get_db()

    cl = db.get(SASClassLeave, lid)
    if not cl:
        abort(404)

    VALID_TRANSITIONS = {
        'pending':  {'approve', 'reject'},
        'approved': set(),
        'rejected': {'approve'},
    }

    action = request.form.get('action', '').strip()

    current_status = cl.status or 'pending'
    allowed = VALID_TRANSITIONS.get(current_status, set())
    if action not in allowed:
        flash(_t(f'لا يمكن تغيير الحالة من {current_status}',
                  f'Cannot change status from {current_status}'), 'danger')
        return redirect(request.referrer or url_for('sas.class_leave_list', code=code))

    if action == 'approve':
        cl.status = 'approved'
    elif action == 'reject':
        cl.status = 'rejected'
    else:
        flash(_t('إجراء غير صالح', 'Invalid action'), 'danger')
        return redirect(request.referrer or url_for('sas.class_leave_list', code=code))

    cl.approved_by = staff.id
    cl.approved_at = datetime.utcnow()
    cl.updated_at = datetime.utcnow()

    try:
        db.commit()
        flash(_t('تم تحديث حالة الإذن', 'Leave status updated'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ', 'An error occurred'), 'danger')

    return redirect(request.referrer or url_for('sas.class_leave_list', code=code))


# 38. Mark student returned from class leave
@sas_bp.route('/portal/<code>/class-leave/<int:lid>/return', methods=['POST'])
def class_leave_return(code, lid):
    staff = _get_staff_or_404(code)
    db = get_db()

    cl = db.get(SASClassLeave, lid)
    if not cl:
        abort(404)

    cl.return_time = request.form.get('return_time', datetime.now().strftime('%H:%M')).strip()
    cl.updated_at = datetime.utcnow()

    try:
        db.commit()
        flash(_t('تم تسجيل العودة', 'Return recorded'), 'success')
    except Exception:
        db.rollback()
        flash(_t('حدث خطأ', 'An error occurred'), 'danger')

    return redirect(request.referrer or url_for('sas.class_leave_list', code=code))


# 39. Class leave attachment download
@sas_bp.route('/portal/<code>/class-leave/<int:lid>/attachment')
def class_leave_attachment(code, lid):
    _get_staff_or_404(code)
    db = get_db()
    cl = db.get(SASClassLeave, lid)
    if not cl or not cl.attachment_b64:
        abort(404)
    data = base64.b64decode(cl.attachment_b64)
    filename = cl.attachment_name or 'attachment'
    return Response(data, mimetype='application/octet-stream',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


# 40b. Staff JSON API — for teacher autocomplete in timetable
@sas_bp.route('/api/staff')
def api_staff():
    db = get_db()
    cfg = _get_config()
    q = request.args.get('q', '').strip()
    stage_id = request.args.get('stage_id', type=int)

    query = db.query(SASStaff).filter(
        SASStaff.config_id == cfg.id,
        SASStaff.is_active == True,
    )
    if stage_id:
        query = query.filter(
            or_(SASStaff.stage_id == stage_id, SASStaff.stage_id == None)
        )
    if q:
        query = query.filter(
            or_(
                SASStaff.name.contains(q),
                SASStaff.name_en.contains(q),
            )
        )
    staff = query.order_by(SASStaff.name).limit(30).all()
    return jsonify({'staff': [
        {'id': s.id, 'name': s.name, 'name_en': s.name_en or '',
         'role': s.role, 'email': s.email or ''}
        for s in staff
    ]})


# 40. Class leave export CSV
@sas_bp.route('/admin/class-leave/export')
@admin_required
def admin_class_leave_export():
    db = get_db()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = db.query(SASClassLeave).options(
        joinedload(SASClassLeave.student).joinedload(SASStudent.section)
        .joinedload(SASSection.sas_class).joinedload(SASClass.stage),
        joinedload(SASClassLeave.staff),
    )
    if date_from:
        query = query.filter(SASClassLeave.leave_date >= date_from)
    if date_to:
        query = query.filter(SASClassLeave.leave_date <= date_to)

    records = query.order_by(SASClassLeave.leave_date.desc()).all()

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        yield '\ufeff'
        writer.writerow([
            'ID', 'Student Name', 'Student Number', 'Stage', 'Class', 'Section',
            'Date', 'Leave Time', 'Return Time', 'Type', 'Custom Type',
            'Status', 'Staff', 'Notes',
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for cl in records:
            s = cl.student
            sec = s.section if s else None
            cls_ = sec.sas_class if sec else None
            stg = cls_.stage if cls_ else None
            writer.writerow([
                cl.id,
                s.name if s else '',
                s.student_number if s else '',
                stg.name if stg else '',
                cls_.name if cls_ else '',
                sec.name if sec else '',
                cl.leave_date,
                cl.leave_time or '',
                cl.return_time or '',
                cl.leave_type,
                cl.custom_type or '',
                cl.status,
                cl.staff.name if cl.staff else '',
                cl.notes or '',
            ])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    filename = f'sas_class_leave_{date.today().strftime("%Y%m%d")}.csv'
    return Response(generate(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})
