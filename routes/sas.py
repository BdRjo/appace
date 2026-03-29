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
from datetime import datetime, date, timedelta
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    jsonify, abort, g, flash, Response
)
from sqlalchemy import func, and_, or_, extract
from sqlalchemy.orm import joinedload

from models.database import (
    SASConfig, SASYear, SASSemester, SASStage, SASClass, SASSection,
    SASStudent, SASStaff, SASRecord, SASHoliday
)
from utils.helpers import admin_required
from utils.i18n import t, get_lang

sas_bp = Blueprint('sas', __name__, url_prefix='/sas')


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


def _today_str():
    return date.today().strftime('%Y-%m-%d')


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


# ===========================================================================
# PUBLIC PORTAL ROUTES
# ===========================================================================

# 1. Welcome page
@sas_bp.route('/')
def welcome():
    cfg = _get_config()
    return render_template('sas/welcome.html', config=cfg)


# 2. Staff login via code
@sas_bp.route('/login', methods=['POST'])
def login():
    staff_code = (request.form.get('staff_code') or '').strip()
    if not staff_code:
        flash(t('يرجى إدخال الرمز', 'Please enter a code'), 'error')
        return redirect(url_for('sas.welcome'))

    db = get_db()
    staff = db.query(SASStaff).filter(
        SASStaff.staff_code == staff_code,
        SASStaff.is_active == True,
    ).first()

    if not staff:
        flash(t('رمز الدخول غير صحيح', 'Invalid staff code'), 'error')
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

    today_total = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date == today, *stage_filter
    ).scalar() or 0

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

    pending_count = db.query(func.count(SASRecord.id)).filter(
        SASRecord.status == 'pending',
        *stage_filter,
    ).scalar() or 0

    stage = db.query(SASStage).get(staff.stage_id) if staff.stage_id else None

    return render_template(
        'sas/portal_home.html',
        config=cfg,
        staff=staff,
        stage=stage,
        today_total=today_total,
        today_absent=today_absent,
        today_late=today_late,
        pending_count=pending_count,
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
            today_records[r.student_id] = r

    return render_template(
        'sas/stage_students.html',
        config=cfg,
        staff=staff,
        stage=stage,
        section_id=section_id,
        today_records=today_records,
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

    records = (
        db.query(SASRecord)
        .filter(SASRecord.student_id == student_id)
        .order_by(SASRecord.record_date.desc(), SASRecord.created_at.desc())
        .all()
    )

    return render_template(
        'sas/student_detail.html',
        config=cfg,
        staff=staff,
        student=student,
        records=records,
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
        flash(t('يرجى تحديد الطالب', 'Please select a student'), 'error')
        return redirect(request.referrer or url_for('sas.portal_home', code=code))

    student = db.query(SASStudent).get(student_id)
    if not student:
        abort(404)

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
        flash(t('تم إضافة السجل بنجاح', 'Record added successfully'), 'success')
    except Exception:
        db.rollback()
        flash(t('حدث خطأ أثناء الحفظ', 'Error saving record'), 'error')

    return redirect(url_for('sas.student_detail', code=code, student_id=student_id))


# 7. Edit a record
@sas_bp.route('/portal/<code>/record/<int:rid>/edit', methods=['POST'])
def record_edit(code, rid):
    staff = _get_staff_or_404(code)
    db = get_db()

    record = db.query(SASRecord).get(rid)
    if not record:
        abort(404)

    # Only the owner or a manager can edit
    if record.staff_id != staff.id and staff.role != 'manager':
        abort(403)

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
        flash(t('تم تعديل السجل بنجاح', 'Record updated successfully'), 'success')
    except Exception:
        db.rollback()
        flash(t('حدث خطأ أثناء التعديل', 'Error updating record'), 'error')

    return redirect(url_for('sas.student_detail', code=code, student_id=record.student_id))


# 8. Delete a record (manager only)
@sas_bp.route('/portal/<code>/record/<int:rid>/delete', methods=['POST'])
def record_delete(code, rid):
    staff = _get_staff_or_404(code)
    db = get_db()

    if staff.role != 'manager':
        abort(403)

    record = db.query(SASRecord).get(rid)
    if not record:
        abort(404)

    student_id = record.student_id
    db.delete(record)

    try:
        db.commit()
        flash(t('تم حذف السجل', 'Record deleted'), 'success')
    except Exception:
        db.rollback()
        flash(t('حدث خطأ أثناء الحذف', 'Error deleting record'), 'error')

    return redirect(url_for('sas.student_detail', code=code, student_id=student_id))


# 8b. Download a record's attachment
@sas_bp.route('/portal/<code>/record/<int:record_id>/attachment')
def download_attachment(code, record_id):
    _get_staff_or_404(code)
    db = get_db()
    record = db.query(SASRecord).get(record_id)
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

    record = db.query(SASRecord).get(rid)
    if not record:
        abort(404)

    action = request.form.get('action', '').strip()
    if action == 'approve':
        record.status = 'approved'
    elif action == 'reject':
        record.status = 'rejected'
    else:
        flash(t('إجراء غير صالح', 'Invalid action'), 'error')
        return redirect(request.referrer or url_for('sas.portal_home', code=code))

    record.approved_by = staff.id
    record.approved_at = datetime.utcnow()
    record.updated_at = datetime.utcnow()

    try:
        db.commit()
        flash(t('تم تحديث حالة السجل', 'Record status updated'), 'success')
    except Exception:
        db.rollback()
        flash(t('حدث خطأ', 'An error occurred'), 'error')

    return redirect(request.referrer or url_for('sas.portal_home', code=code))


# 10. Bulk mark absent
@sas_bp.route('/portal/<code>/bulk-absent', methods=['POST'])
def bulk_absent(code):
    staff = _get_staff_or_404(code)
    db = get_db()

    student_ids = request.form.getlist('student_ids[]', type=int)
    record_date = request.form.get('record_date', _today_str()).strip()
    record_type = request.form.get('record_type', 'absent').strip()

    if not student_ids:
        flash(t('لم يتم تحديد طلاب', 'No students selected'), 'error')
        return redirect(request.referrer or url_for('sas.portal_home', code=code))

    created = 0
    for sid in student_ids:
        student = db.query(SASStudent).get(sid)
        if not student:
            continue
        # Avoid duplicate records for the same student/date/type
        existing = db.query(SASRecord).filter(
            SASRecord.student_id == sid,
            SASRecord.record_date == record_date,
            SASRecord.record_type == record_type,
        ).first()
        if existing:
            continue
        record = SASRecord(
            student_id=sid,
            staff_id=staff.id,
            record_date=record_date,
            record_type=record_type,
            status='pending',
        )
        db.add(record)
        created += 1

    try:
        db.commit()
        flash(
            t(f'تم تسجيل {created} حالة غياب', f'{created} absence records created'),
            'success',
        )
    except Exception:
        db.rollback()
        flash(t('حدث خطأ أثناء الحفظ', 'Error saving records'), 'error')

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

    if not title or not start_date or not end_date:
        flash(t('يرجى تعبئة جميع الحقول المطلوبة', 'Please fill all required fields'), 'error')
        return redirect(url_for('sas.holidays', code=code))

    # Normalise applies_to as JSON
    if applies_to != 'all':
        try:
            json.loads(applies_to)
        except (json.JSONDecodeError, TypeError):
            applies_to = json.dumps(applies_to)
    else:
        applies_to = json.dumps('all')

    holiday = SASHoliday(
        config_id=cfg.id,
        title=title,
        title_en=title_en,
        start_date=start_date,
        end_date=end_date,
        applies_to=applies_to,
        created_by=staff.id,
    )
    db.add(holiday)

    try:
        db.commit()
        flash(t('تمت إضافة الإجازة بنجاح', 'Holiday added successfully'), 'success')
    except Exception:
        db.rollback()
        flash(t('حدث خطأ أثناء الحفظ', 'Error saving holiday'), 'error')

    return redirect(url_for('sas.holidays', code=code))


# 11b. Delete holiday (manager/admin only)
@sas_bp.route('/portal/<code>/holiday/<int:holiday_id>/delete', methods=['POST'])
def holiday_delete(code, holiday_id):
    staff = _get_staff_or_404(code)
    if staff.role not in ('manager',):
        abort(403)
    db = get_db()
    holiday = db.query(SASHoliday).get(holiday_id)
    if holiday:
        db.delete(holiday)
        db.commit()
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

    return render_template(
        'sas/holidays.html',
        config=cfg,
        staff=staff,
        holidays=holiday_list,
    )


# 13. Pending approvals (manager only)
@sas_bp.route('/portal/<code>/pending')
def pending(code):
    staff = _get_staff_or_404(code)
    db = get_db()
    cfg = _get_config()

    if staff.role != 'manager':
        abort(403)

    # Scope to staff's stage if they have one
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

    return render_template(
        'sas/pending.html',
        config=cfg,
        staff=staff,
        records=records,
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

    total_students = db.query(func.count(SASStudent.id)).filter(
        SASStudent.is_active == True,
    ).scalar() or 0

    today_absences = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date == today,
        SASRecord.record_type == 'absent',
    ).scalar() or 0

    week_absences = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date >= week_start,
        SASRecord.record_date <= week_end,
        SASRecord.record_type == 'absent',
    ).scalar() or 0

    month_absences = db.query(func.count(SASRecord.id)).filter(
        SASRecord.record_date >= month_start,
        SASRecord.record_date <= month_end,
        SASRecord.record_type == 'absent',
    ).scalar() or 0

    # Top 10 absent students
    top_absent = (
        db.query(
            SASStudent,
            func.count(SASRecord.id).label('absence_count'),
        )
        .join(SASRecord, SASRecord.student_id == SASStudent.id)
        .filter(SASRecord.record_type == 'absent')
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
        .group_by(SASStage.id, SASStage.name, SASStage.name_en)
        .order_by(func.count(SASRecord.id).desc())
        .all()
    )

    # Monthly trend (last 6 months)
    monthly_trend = []
    for i in range(5, -1, -1):
        ref = date.today().replace(day=1) - timedelta(days=i * 30)
        m_start = ref.replace(day=1)
        if m_start.month == 12:
            m_end = m_start.replace(year=m_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            m_end = m_start.replace(month=m_start.month + 1, day=1) - timedelta(days=1)

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

    return render_template(
        'sas/admin/dashboard.html',
        config=cfg,
        total_students=total_students,
        today_absences=today_absences,
        week_absences=week_absences,
        month_absences=month_absences,
        top_absent=top_absent,
        stage_dist=stage_dist,
        monthly_trend=monthly_trend,
    )


# 15. Module settings form
@sas_bp.route('/admin/config')
@admin_required
def admin_config():
    cfg = _get_config()
    return render_template('sas/admin/config.html', config=cfg)


# 16. Save config
@sas_bp.route('/admin/config/save', methods=['POST'])
@admin_required
def admin_config_save():
    db = get_db()
    cfg = _get_config()

    cfg.school_name = request.form.get('school_name', cfg.school_name).strip()
    cfg.school_name_en = request.form.get('school_name_en', cfg.school_name_en).strip()
    cfg.academic_year = request.form.get('academic_year', cfg.academic_year).strip()

    logo_file = request.files.get('school_logo')
    if logo_file and logo_file.filename:
        cfg.school_logo_b64 = base64.b64encode(logo_file.read()).decode('utf-8')

    # Ticker JSON saved separately if provided
    ticker_json = request.form.get('ticker_json')
    if ticker_json is not None:
        cfg.ticker_json = ticker_json.strip()

    try:
        db.commit()
        flash(t('تم حفظ الإعدادات', 'Settings saved'), 'success')
    except Exception:
        db.rollback()
        flash(t('حدث خطأ أثناء الحفظ', 'Error saving settings'), 'error')

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

    return render_template(
        'sas/admin/staff.html',
        config=cfg,
        staff_list=staff_list,
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
        flash(t('يرجى إدخال اسم الموظف', 'Please enter staff name'), 'error')
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
        flash(t(f'تمت الإضافة بنجاح. الرمز: {code}', f'Staff added. Code: {code}'), 'success')
    except Exception:
        db.rollback()
        flash(t('حدث خطأ أثناء الحفظ', 'Error saving staff'), 'error')

    return redirect(url_for('sas.admin_staff'))


# 19. Edit staff
@sas_bp.route('/admin/staff/<int:sid>/edit', methods=['POST'])
@admin_required
def admin_staff_edit(sid):
    db = get_db()
    staff = db.query(SASStaff).get(sid)
    if not staff:
        abort(404)

    staff.name = request.form.get('name', staff.name).strip()
    staff.name_en = request.form.get('name_en', staff.name_en).strip()
    staff.email = request.form.get('email', staff.email or '').strip()
    staff.phone = request.form.get('phone', staff.phone or '').strip()
    staff.role = request.form.get('role', staff.role).strip()
    staff.stage_id = request.form.get('stage_id', type=int) or staff.stage_id
    staff.is_active = request.form.get('is_active', '1') == '1'

    try:
        db.commit()
        flash(t('تم تعديل بيانات الموظف', 'Staff updated'), 'success')
    except Exception:
        db.rollback()
        flash(t('حدث خطأ أثناء التعديل', 'Error updating staff'), 'error')

    return redirect(url_for('sas.admin_staff'))


# 20. Delete staff
@sas_bp.route('/admin/staff/<int:sid>/delete', methods=['POST'])
@admin_required
def admin_staff_delete(sid):
    db = get_db()
    staff = db.query(SASStaff).get(sid)
    if not staff:
        abort(404)

    db.delete(staff)

    try:
        db.commit()
        flash(t('تم حذف الموظف', 'Staff deleted'), 'success')
    except Exception:
        db.rollback()
        flash(t('حدث خطأ أثناء الحذف', 'Error deleting staff'), 'error')

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
    db.commit()
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
    staff = db.query(SASStaff).get(sid)
    if not staff:
        return jsonify({'error': 'not found'}), 404
    code = _gen_staff_code()
    while db.query(SASStaff).filter(SASStaff.staff_code == code).first():
        code = _gen_staff_code()
    staff.staff_code = code
    db.commit()
    return jsonify({'ok': True, 'new_code': code})


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

    return render_template(
        'sas/admin/students.html',
        config=cfg,
        students=students,
        stages=stages,
        stage_id=stage_id,
        class_id=class_id,
        section_id=section_id,
    )


# 21b. Delete a student (admin only)
@sas_bp.route('/admin/student/<int:student_id>/delete', methods=['POST'])
@admin_required
def admin_student_delete(student_id):
    db = get_db()
    student = db.query(SASStudent).get(student_id)
    if student:
        db.delete(student)
        db.commit()
        return jsonify({'ok': True})
    return jsonify({'error': 'not found'}), 404


# 22. CSV import students
@sas_bp.route('/admin/students/import', methods=['POST'])
@admin_required
def admin_students_import():
    db = get_db()
    cfg = _get_config()

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': t('لم يتم تحديد ملف', 'No file selected')}), 400

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
        return jsonify({'success': False, 'error': t('تعذر قراءة الملف', 'Could not read file')}), 400

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
                    'error': t('حقول مطلوبة مفقودة', 'Missing required fields'),
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
                        'error': t(
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
        flash(t('\u064a\u0631\u062c\u0649 \u0627\u062e\u062a\u064a\u0627\u0631 \u0627\u0644\u0634\u0639\u0628\u0629', 'Please select a section'), 'error')
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
    flash(t('\u062a\u0645 \u0625\u0636\u0627\u0641\u0629 \u0627\u0644\u0637\u0627\u0644\u0628', 'Student added'), 'success')
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
                year = db.query(SASYear).get(year_id)
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
                    semester = db.query(SASSemester).get(semester_id)
                    if not semester:
                        continue
                    semester.name = sem_data.get('name', semester.name)
                    semester.name_en = sem_data.get('name_en', semester.name_en)
                    semester.order_num = sem_idx
                    semester.year_id = year.id
                    incoming_semester_ids.add(semester.id)
                else:
                    semester = SASSemester(
                        year_id=year.id,
                        name=sem_data.get('name', ''),
                        name_en=sem_data.get('name_en', ''),
                        order_num=sem_idx,
                    )
                    db.add(semester)
                    db.flush()
                    incoming_semester_ids.add(semester.id)

                for s_idx, s_data in enumerate(sem_data.get('stages', [])):
                    stage_id = s_data.get('id')
                    if stage_id:
                        stage = db.query(SASStage).get(stage_id)
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
                            cls = db.query(SASClass).get(class_id)
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
                                sec = db.query(SASSection).get(section_id)
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
            sec = db.query(SASSection).get(sec_id)
            if sec:
                db.delete(sec)
        for cls_id in existing_class_ids - incoming_class_ids:
            cls = db.query(SASClass).get(cls_id)
            if cls:
                db.delete(cls)
        for stage_id in existing_stage_ids - incoming_stage_ids:
            stg = db.query(SASStage).get(stage_id)
            if stg:
                db.delete(stg)
        for sem_id in existing_semester_ids - incoming_semester_ids:
            sem = db.query(SASSemester).get(sem_id)
            if sem:
                db.delete(sem)
        for year_id in existing_year_ids - incoming_year_ids:
            yr = db.query(SASYear).get(year_id)
            if yr:
                db.delete(yr)

        db.commit()
        return jsonify({'success': True})

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


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

    results = None

    if field1 and value1:
        def _build_compare_query(field, value):
            """Build a count query filtered by field=value and optional date range."""
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

    today = date.today()
    now_month = str(today.month)
    prev_month = str(today.month - 1 if today.month > 1 else 12)

    return render_template(
        'sas/admin/compare.html',
        config=cfg,
        results=results,
        stages=stages,
        staff_list=staff_list,
        field1=field1, field2=field2, field3=field3,
        value1=value1, value2=value2, value3=value3,
        date_from=date_from, date_to=date_to,
        now_month=now_month, prev_month=prev_month,
    )


# 27. Export records (CSV stream or PDF redirect)
@sas_bp.route('/admin/export')
@admin_required
def admin_export():
    db = get_db()
    fmt = request.args.get('format', 'csv')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    stage_id = request.args.get('stage_id', type=int)
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
    if stage_id:
        query = query.filter(
            SASRecord.student_id.in_(
                db.query(SASStudent.id)
                .join(SASSection)
                .join(SASClass)
                .filter(SASClass.stage_id == stage_id)
            )
        )

    records = query.order_by(SASRecord.record_date.desc()).all()

    if fmt == 'pdf':
        return redirect(url_for(
            'sas.admin_print',
            date_from=date_from,
            date_to=date_to,
            stage_id=stage_id or '',
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
    if stage_id:
        query = query.filter(
            SASRecord.student_id.in_(
                db.query(SASStudent.id)
                .join(SASSection)
                .join(SASClass)
                .filter(SASClass.stage_id == stage_id)
            )
        )

    records = query.order_by(SASRecord.record_date.desc()).all()

    return render_template(
        'sas/admin/print_report.html',
        config=cfg,
        records=records,
        date_from=date_from,
        date_to=date_to,
        record_type=record_type,
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

    students = query.order_by(SASStudent.name).all()

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
                flash(t('صيغة JSON غير صالحة', 'Invalid JSON format'), 'error')
                return redirect(url_for('sas.admin_ticker'))
        else:
            cfg.ticker_json = None

    try:
        db.commit()
        if request.is_json or request.content_type == 'application/json':
            return jsonify({'success': True})
        flash(t('تم حفظ إعدادات الشريط', 'Ticker settings saved'), 'success')
    except Exception:
        db.rollback()
        if request.is_json or request.content_type == 'application/json':
            return jsonify({'success': False, 'error': 'Database error'}), 500
        flash(t('حدث خطأ أثناء الحفظ', 'Error saving ticker'), 'error')

    return redirect(url_for('sas.admin_ticker'))
