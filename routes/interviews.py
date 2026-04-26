"""
routes/interviews.py — Parent Interviews System
All features matching parentinterviews.co.nz
"""
import csv, io, json, random, string, base64
from datetime import datetime, timedelta
from flask import (current_app, Blueprint, render_template, redirect, url_for,
                   request, flash, jsonify, abort, Response, session, g)
from flask_login import login_required, current_user
from utils.helpers import get_db, get_permissions, syslog
from models.database import (PIEvent, PITeacher, PISlot, PIBooking, PIAppointmentRequest,
                              PICalendarSlot, PICalendarBooking,
                              PISchoolStage, PISchoolClass, PISection, PITeacherAssignment)

interviews_bp = Blueprint('interviews', __name__, url_prefix='/interviews')


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _ajax_or_redirect(event_id):
    """Return JSON for AJAX requests, redirect for normal form posts."""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})
    return redirect(url_for('interviews.admin_hierarchy', event_id=event_id))

def _gen_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def _gen_ref():
    return 'PI-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def _gen_teacher_code():
    return 'T-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def _gen_assignment_code(class_name='', section_name=''):
    """Generate section-based code like '1A-K7M2' or 'G3B-X9P1'"""
    cls = ''.join(c for c in class_name if c.isalnum())[:4] if class_name else ''
    sec = ''.join(c for c in section_name if c.isalnum())[:2] if section_name else ''
    prefix = (cls + sec).upper() or 'ASG'
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f'{prefix}-{suffix}'

def _generate_slots(db, teacher, date_str, start_hhmm, end_hhmm, duration, break_dur, breaks):
    """
    Generate time slots for a teacher on a given date.
    breaks: list of {"start":"HH:MM","end":"HH:MM"}
    Deletes existing non-booked slots for that teacher/date first.
    """
    # delete unbooked existing slots
    for s in db.query(PISlot).filter(
        PISlot.teacher_id == teacher.id,
        PISlot.slot_date == date_str,
        PISlot.is_booked == False
    ).all():
        db.delete(s)
    db.flush()

    def t2m(t):
        h, m = map(int, t.split(':'))
        return h * 60 + m

    def m2t(m):
        return f"{m//60:02d}:{m%60:02d}"

    current = t2m(start_hhmm)
    end     = t2m(end_hhmm)
    created = 0

    while current + duration <= end:
        slot_start = m2t(current)
        slot_end   = m2t(current + duration)

        # check if this slot overlaps a break
        is_break = False
        for brk in breaks:
            bs = t2m(brk['start'])
            be = t2m(brk['end'])
            if current >= bs and current < be:
                is_break = True
                break

        db.add(PISlot(
            teacher_id = teacher.id,
            event_id   = teacher.event_id,
            slot_date  = date_str,
            start_time = slot_start,
            end_time   = slot_end,
            is_break   = is_break,
        ))
        created += 1
        current += duration + break_dur

    db.commit()
    return created


def _send_confirmation(booking, event, teacher, slot):
    """Send bilingual email confirmation to parent"""
    try:
        from utils.email_helper import send_email
        from utils.i18n import get_lang
        ar = get_lang() == 'ar'
        d = 'rtl' if ar else 'ltr'
        subject = f"تأكيد حجز المقابلة — {event.name}" if ar else f"Interview Booking Confirmation — {event.name}"
        greeting = f"عزيزي {booking.parent_name}،" if ar else f"Dear {booking.parent_name},"
        msg = "تم تأكيد حجز المقابلة الخاص بك بنجاح." if ar else "Your interview booking has been confirmed."
        lbl_teacher = "المعلم" if ar else "Teacher"
        lbl_subject = "المادة" if ar else "Subject"
        lbl_room = "الغرفة" if ar else "Room"
        lbl_date = "التاريخ" if ar else "Date"
        lbl_time = "الوقت" if ar else "Time"
        lbl_child = "الطالب" if ar else "Child"
        lbl_ref = "رقم الحجز" if ar else "Booking Ref"
        lbl_auto = "هذه رسالة آلية. يرجى عدم الرد عليها." if ar else "This is an automated message. Please do not reply."
        logo_html = ''
        if event.school_logo_url:
            logo_html = f'<img src="{event.school_logo_url}" alt="logo" style="height:48px;max-width:160px;object-fit:contain;margin-bottom:8px;display:block">'
        body = f"""
<div style="font-family:sans-serif;max-width:600px;margin:auto;direction:{d}">
<div style="background:{event.brand_color};color:white;padding:20px;border-radius:8px 8px 0 0;text-align:center">
  {logo_html}
  <h2 style="margin:0">{event.school_name or 'School'}</h2>
  <p style="margin:5px 0 0;opacity:.9">{event.name}</p>
</div>
<div style="padding:24px;border:1px solid #dee2e6;border-top:none;border-radius:0 0 8px 8px">
  <p>{greeting}</p>
  <p>{msg}</p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0">
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_teacher}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{teacher.name}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_subject}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{teacher.subjects or '—'}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_room}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{teacher.room or '—'}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_date}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{slot.slot_date}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_time}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{slot.start_time} – {slot.end_time}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_child}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{booking.child_name}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_ref}</td>
        <td style="padding:8px">{booking.booking_ref}</td></tr>
  </table>
  <p style="color:#6c757d;font-size:0.9em">{lbl_auto}</p>
</div>
</div>
"""
        text_body = f"{greeting} {msg} {lbl_ref}: {booking.booking_ref}"
        send_email(to_email=booking.parent_email, to_name=booking.parent_name,
                   subject=subject, html_body=body, text_body=text_body,
                   email_type='interview_confirmation')
    except Exception as e:
        current_app.logger.warning(f"Email error: {e}")


def _send_reminder(booking, event, teacher, slot):
    """Send bilingual reminder email to parent"""
    try:
        from utils.email_helper import send_email
        from utils.i18n import get_lang
        ar = get_lang() == 'ar'
        d = 'rtl' if ar else 'ltr'
        subject = f"تذكير: المقابلة غداً — {event.name}" if ar else f"Reminder: Interview Tomorrow — {event.name}"
        greeting = f"عزيزي {booking.parent_name}،" if ar else f"Dear {booking.parent_name},"
        msg = "هذا تذكير بموعد المقابلة القادمة:" if ar else "This is a reminder about your upcoming interview:"
        lbl_teacher = "المعلم" if ar else "Teacher"
        lbl_datetime = "التاريخ والوقت" if ar else "Date & Time"
        lbl_room = "الغرفة" if ar else "Room"
        lbl_ref = "رقم الحجز" if ar else "Booking Reference"
        time_sep = " الساعة " if ar else " at "
        logo_html = ''
        if event.school_logo_url:
            logo_html = f'<img src="{event.school_logo_url}" alt="logo" style="height:48px;max-width:160px;object-fit:contain;margin-bottom:8px;display:block">'
        body = f"""
<div style="font-family:sans-serif;max-width:600px;margin:auto;direction:{d}">
<div style="background:{event.brand_color};color:white;padding:20px;border-radius:8px 8px 0 0;text-align:center">
  {logo_html}
  <h2 style="margin:0">{event.school_name or 'School'} — {'تذكير' if ar else 'Reminder'}</h2>
</div>
<div style="padding:24px;border:1px solid #dee2e6;border-top:none;border-radius:0 0 8px 8px">
  <p>{greeting}</p>
  <p>{msg}</p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0">
    <tr><td style="padding:8px;background:#fff3cd;font-weight:bold">{lbl_teacher}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{teacher.name}</td></tr>
    <tr><td style="padding:8px;background:#fff3cd;font-weight:bold">{lbl_datetime}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{slot.slot_date}{time_sep}{slot.start_time}</td></tr>
    <tr><td style="padding:8px;background:#fff3cd;font-weight:bold">{lbl_room}</td>
        <td style="padding:8px">{teacher.room or '—'}</td></tr>
  </table>
  <p style="color:#6c757d;font-size:0.9em">{lbl_ref}: {booking.booking_ref}</p>
</div>
</div>
"""
        text_body = f"{greeting} {msg} {lbl_ref}: {booking.booking_ref}"
        send_email(to_email=booking.parent_email, to_name=booking.parent_name,
                   subject=subject, html_body=body, text_body=text_body,
                   email_type='interview_reminder')
    except Exception as e:
        current_app.logger.warning(f"Reminder email error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — Events Management
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/')
@interviews_bp.route('')
def root():
    """Redirect /interviews and /interviews/ to admin index"""
    from flask import redirect, url_for, request as _req
    target = url_for('interviews.admin_index')
    # For HTMX requests, use HX-Redirect header so HTMX handles it properly
    if _req.headers.get('HX-Request'):
        from flask import Response
        resp = Response('', status=200)
        resp.headers['HX-Redirect'] = target
        return resp
    return redirect(target)


@interviews_bp.route('/admin/')
@login_required
def admin_index():
    """Admin landing — go straight to data entry. Auto-create event if none exist."""
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).order_by(PIEvent.created_at.desc()).first()
    if not ev:
        # Auto-create a default event so admin lands directly on data entry
        ev = PIEvent(
            name='Parent-Teacher Interviews',
            event_code=_gen_code(),
            is_open=True,
            is_active=True,
            slot_duration=5,
            created_by=current_user.id,
        )
        db.add(ev)
        db.commit()
    return redirect(url_for('interviews.admin_data_entry', event_id=ev.id))


@interviews_bp.route('/admin/events/new', methods=['GET', 'POST'])
@login_required
def admin_event_new():
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    if request.method == 'POST':
        code = request.form.get('event_code', '').strip().upper() or _gen_code()
        ev = PIEvent(
            name             = request.form['name'].strip(),
            event_code       = code,
            school_name      = request.form.get('school_name', '').strip(),
            school_logo_url  = request.form.get('school_logo_url', '').strip(),
            brand_color      = request.form.get('brand_color', '#0d6efd').strip(),
            description      = request.form.get('description', '').strip(),
            event_date       = request.form.get('event_dates', '[]'),
            slot_duration    = int(request.form.get('slot_duration', 5)),
            break_duration   = int(request.form.get('break_duration', 0)),
            allow_comments   = 'allow_comments' in request.form,
            send_reminders   = 'send_reminders' in request.form,
            reminder_hours   = int(request.form.get('reminder_hours', 24)),
            is_open          = 'is_open' in request.form,
            use_hierarchy    = 'use_hierarchy' in request.form,
            is_active        = True,
            created_by       = current_user.id,
        )
        db.add(ev)
        db.commit()
        flash('تم إنشاء الفعالية — أضف البيانات الآن' if get_lang()=='ar' else 'Event created — add data now.', 'success')
        syslog('PI_EVENT_CREATE', f'Created interview event: {ev.name} [{ev.event_code}]')
        return redirect(url_for('interviews.admin_data_entry', event_id=ev.id))
    return render_template('interviews/admin/event_form.html', ev=None, gen_code=_gen_code())


@interviews_bp.route('/admin/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_event_edit(event_id):
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db  = get_db()
    ev  = db.query(PIEvent).get(event_id) or abort(404)
    if request.method == 'POST':
        ev.name            = request.form['name'].strip()
        ev.event_code      = request.form.get('event_code', ev.event_code).strip().upper()
        ev.school_name     = request.form.get('school_name', '').strip()
        ev.school_logo_url = request.form.get('school_logo_url', '').strip()
        ev.brand_color     = request.form.get('brand_color', '#0d6efd').strip()
        ev.description     = request.form.get('description', '').strip()
        ev.event_date      = request.form.get('event_dates', '[]')
        ev.slot_duration   = int(request.form.get('slot_duration', 5))
        ev.break_duration  = int(request.form.get('break_duration', 0))
        ev.allow_comments  = 'allow_comments' in request.form
        ev.send_reminders  = 'send_reminders' in request.form
        ev.reminder_hours  = int(request.form.get('reminder_hours', 24))
        ev.is_open         = 'is_open' in request.form
        ev.use_hierarchy   = 'use_hierarchy' in request.form
        db.commit()
        flash('تم تحديث الفعالية' if get_lang()=='ar' else 'Event updated.', 'success')
        return redirect(url_for('interviews.admin_index'))
    return render_template('interviews/admin/event_form.html', ev=ev)


@interviews_bp.route('/admin/events/<int:event_id>/delete', methods=['POST'])
@login_required
def admin_event_delete(event_id):
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    name = ev.name
    db.delete(ev)
    db.commit()
    flash(f'تم حذف الفعالية "{name}"' if get_lang()=='ar' else f'Event "{name}" deleted.', 'success')
    syslog('PI_EVENT_DELETE', f'Deleted interview event: {name}')
    return redirect(url_for('interviews.admin_index'))


@interviews_bp.route('/admin/events/<int:event_id>/toggle-open', methods=['POST'])
@login_required
def admin_event_toggle(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    ev.is_open = not ev.is_open
    db.commit()
    return jsonify({'is_open': ev.is_open})


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — Teachers Management
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/admin/events/<int:event_id>/teachers')
@login_required
def admin_teachers(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev       = db.query(PIEvent).get(event_id) or abort(404)
    teachers = db.query(PITeacher).filter(PITeacher.event_id == event_id).all()
    dates    = json.loads(ev.event_date or '[]')
    # slot counts per teacher
    slot_stats = {}
    for t in teachers:
        total  = db.query(PISlot).filter(PISlot.teacher_id == t.id, PISlot.is_break == False).count()
        booked = db.query(PISlot).filter(PISlot.teacher_id == t.id, PISlot.is_booked == True).count()
        slot_stats[t.id] = {'total': total, 'booked': booked}
    return render_template('interviews/admin/teachers.html',
                           ev=ev, teachers=teachers, dates=dates, slot_stats=slot_stats)


@interviews_bp.route('/admin/events/<int:event_id>/teachers/add', methods=['POST'])
@login_required
def admin_teacher_add(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    db.query(PIEvent).get(event_id) or abort(404)
    t = PITeacher(
        event_id     = event_id,
        name         = request.form['name'].strip(),
        email        = request.form.get('email', '').strip(),
        subjects     = request.form.get('subjects', '').strip(),
        room         = request.form.get('room', '').strip(),
        teacher_code = _gen_teacher_code(),
    )
    db.add(t)
    db.commit()
    # Send teacher their unique portal link by email
    if t.email:
        try:
            from utils.email_helper import send_email
            from utils.i18n import get_lang
            ar = get_lang() == 'ar'
            d = 'rtl' if ar else 'ltr'
            ev = db.query(PIEvent).get(event_id)
            portal_url = request.host_url.rstrip('/') + url_for('interviews.teacher_timetable', teacher_code=t.teacher_code)
            subject = f"رابط بوابة المقابلات — {ev.name if ev else ''}" if ar else f"Your Interview Portal Access — {ev.name if ev else ''}"
            greeting = f"عزيزي {t.name}،" if ar else f"Dear {t.name},"
            msg = "تمت إضافتك إلى فعالية مقابلات. استخدم الرابط أدناه لعرض جدولك وإدارة الحجوزات:" if ar else "You have been added to an interview event. Use the link below to view your schedule and manage bookings:"
            lbl_code = "رمز الدخول الخاص بك" if ar else "Your Access Code"
            lbl_btn = "فتح البوابة" if ar else "Open My Portal"
            lbl_private = "هذا رابط خاص. يرجى عدم مشاركته." if ar else "This is a private link. Please do not share it publicly."
            body = f"""
<div style="font-family:sans-serif;max-width:600px;margin:auto;direction:{d}">
<div style="background:{ev.brand_color if ev else '#0d6efd'};color:white;padding:20px;border-radius:8px 8px 0 0">
  <h2 style="margin:0">{ev.school_name if ev else 'School'}</h2>
  <p style="margin:5px 0 0">{ev.name if ev else 'Interview Event'}</p>
</div>
<div style="padding:24px;border:1px solid #dee2e6;border-top:none;border-radius:0 0 8px 8px">
  <p>{greeting}</p>
  <p>{msg}</p>
  <div style="background:#f8f9fa;border-radius:8px;padding:16px;margin:16px 0;text-align:center">
    <div style="font-size:.85rem;color:#6c757d;margin-bottom:8px">{lbl_code}</div>
    <div style="font-size:1.4rem;font-weight:800;letter-spacing:4px;color:#0f172a">{t.teacher_code}</div>
  </div>
  <a href="{portal_url}" style="display:inline-block;background:{ev.brand_color if ev else '#0d6efd'};color:white;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:700">{lbl_btn}</a>
  <p style="color:#6c757d;font-size:0.9em;margin-top:16px">{lbl_private}</p>
</div>
</div>"""
            text_body = f"{greeting} {msg} {lbl_code}: {t.teacher_code}"
            send_email(to_email=t.email, to_name=t.name, subject=subject, html_body=body, text_body=text_body)
        except Exception as e:
            current_app.logger.warning(f"Teacher email error: {e}")
    flash(f'تمت إضافة المعلم {t.name}' if get_lang()=='ar' else f'Teacher {t.name} added.', 'success')
    return redirect(url_for('interviews.admin_teachers', event_id=event_id))


@interviews_bp.route('/admin/teachers/<int:tid>/edit', methods=['POST'])
@login_required
def admin_teacher_edit(tid):
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    t = db.query(PITeacher).get(tid) or abort(404)
    t.name     = request.form['name'].strip()
    t.email    = request.form.get('email', '').strip()
    t.subjects = request.form.get('subjects', '').strip()
    t.room     = request.form.get('room', '').strip()
    db.commit()
    flash('تم تحديث بيانات المعلم' if get_lang()=='ar' else 'Teacher updated.', 'success')
    return redirect(url_for('interviews.admin_teachers', event_id=t.event_id))


@interviews_bp.route('/admin/teachers/<int:tid>/delete', methods=['POST'])
@login_required
def admin_teacher_delete(tid):
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    t = db.query(PITeacher).get(tid) or abort(404)
    eid = t.event_id
    # check if any slots are booked
    booked = db.query(PISlot).filter(PISlot.teacher_id == tid, PISlot.is_booked == True).count()
    if booked:
        flash(f'لا يمكن حذف المعلم مع وجود {booked} حجز نشط' if get_lang()=='ar' else f'Cannot delete teacher with {booked} active booking(s).', 'danger')
    else:
        db.delete(t)
        db.commit()
        flash('تم حذف المعلم' if get_lang()=='ar' else 'Teacher removed.', 'success')
    return redirect(url_for('interviews.admin_teachers', event_id=eid))


@interviews_bp.route('/admin/teachers/<int:tid>/generate-slots', methods=['POST'])
@login_required
def admin_generate_slots(tid):
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db      = get_db()
    teacher = db.query(PITeacher).get(tid) or abort(404)
    ev      = db.query(PIEvent).get(teacher.event_id)

    date_str   = request.form.get('slot_date', '').strip()
    start_time = request.form.get('start_time', '').strip()
    end_time   = request.form.get('end_time', '').strip()
    duration   = int(request.form.get('duration', ev.slot_duration))
    break_dur  = int(request.form.get('break_duration', ev.break_duration))

    # parse breaks JSON
    breaks_raw = request.form.get('breaks', '[]')
    try:
        breaks = json.loads(breaks_raw)
    except Exception:
        breaks = []

    if not all([date_str, start_time, end_time]):
        flash('يرجى تحديد التاريخ ووقت البدء والانتهاء' if get_lang()=='ar' else 'Please provide date, start time and end time.', 'danger')
        return redirect(url_for('interviews.admin_teachers', event_id=teacher.event_id))

    n = _generate_slots(db, teacher, date_str, start_time, end_time, duration, break_dur, breaks)
    flash(f'تم إنشاء {n} فترة لـ {teacher.name} في {date_str}' if get_lang()=='ar' else f'{n} slots generated for {teacher.name} on {date_str}.', 'success')
    syslog('PI_SLOTS_GEN', f'Generated {n} slots for teacher {tid}')
    return redirect(url_for('interviews.admin_teachers', event_id=teacher.event_id))


@interviews_bp.route('/admin/teachers/import', methods=['POST'])
@login_required
def admin_teacher_import(event_id=None):
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    event_id = request.form.get('event_id') or event_id
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    f  = request.files.get('csv_file')
    if not f:
        flash('لم يتم رفع ملف' if get_lang()=='ar' else 'No file uploaded.', 'danger')
        return redirect(url_for('interviews.admin_teachers', event_id=event_id))
    stream  = io.StringIO(f.stream.read().decode('utf-8-sig'))
    reader  = csv.DictReader(stream)
    count   = 0
    for row in reader:
        name = (row.get('name') or row.get('Name') or '').strip()
        if not name:
            continue
        t = PITeacher(
            event_id     = ev.id,
            name         = name,
            email        = (row.get('email') or row.get('Email') or '').strip(),
            subjects     = (row.get('subjects') or row.get('Subjects') or '').strip(),
            room         = (row.get('room') or row.get('Room') or '').strip(),
            teacher_code = _gen_teacher_code(),
        )
        db.add(t)
        count += 1
    db.commit()
    flash(f'تم استيراد {count} معلم' if get_lang()=='ar' else f'{count} teachers imported.', 'success')
    return redirect(url_for('interviews.admin_teachers', event_id=event_id))


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — Bookings Overview
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/admin/events/<int:event_id>/bookings')
@login_required
def admin_bookings(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db       = get_db()
    ev       = db.query(PIEvent).get(event_id) or abort(404)
    teachers = db.query(PITeacher).filter(PITeacher.event_id == event_id).all()
    # filter params
    sel_teacher = request.args.get('teacher_id', type=int)  # None if missing/invalid
    sel_date    = request.args.get('date', '')
    sel_status  = request.args.get('status', '')

    q = db.query(PIBooking).filter(PIBooking.event_id == event_id)
    # join PISlot once if either teacher or date filter is active (avoids double-join crash)
    if sel_teacher or sel_date:
        q = q.join(PISlot)
    if sel_teacher:
        q = q.filter(PISlot.teacher_id == sel_teacher)
    if sel_date:
        q = q.filter(PISlot.slot_date == sel_date)
    if sel_status:
        q = q.filter(PIBooking.status == sel_status)

    bookings = q.order_by(PIBooking.created_at.desc()).all()
    dates    = sorted(set(b.slot.slot_date for b in bookings if b.slot))
    total    = db.query(PIBooking).filter(PIBooking.event_id == event_id,
                                          PIBooking.status == 'confirmed').count()

    # Build per-teacher booking data for teacher summary cards
    teacher_bookings = {}
    for b in bookings:
        if b.slot and b.slot.teacher_id:
            teacher_bookings.setdefault(b.slot.teacher_id, []).append(b)

    return render_template('interviews/admin/bookings.html',
                           ev=ev, bookings=bookings, teachers=teachers,
                           dates=dates, total=total,
                           teacher_bookings=teacher_bookings,
                           sel_teacher=sel_teacher, sel_date=sel_date, sel_status=sel_status)


@interviews_bp.route('/admin/events/<int:event_id>/bookings/export')
@login_required
def admin_export(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    bookings = db.query(PIBooking).filter(PIBooking.event_id == event_id).all()

    from utils.i18n import get_lang
    _ar = get_lang() == 'ar'
    out = io.StringIO()
    w   = csv.writer(out)
    if _ar:
        w.writerow(['رقم الحجز', 'اسم ولي الأمر', 'البريد الإلكتروني', 'رقم الهاتف',
                    'اسم الطالب', 'ملاحظات', 'المعلم', 'المادة', 'الغرفة',
                    'التاريخ', 'وقت البدء', 'وقت الانتهاء', 'الحالة', 'تاريخ الحجز'])
    else:
        w.writerow(['Ref', 'Parent Name', 'Parent Email', 'Parent Phone',
                    'Child Name', 'Comment', 'Teacher', 'Subject', 'Room',
                    'Date', 'Start', 'End', 'Status', 'Booked At'])
    for b in bookings:
        sl = b.slot
        te = sl.teacher if sl else None
        w.writerow([
            b.booking_ref, b.parent_name, b.parent_email, b.parent_phone,
            b.child_name, b.comment or '',
            te.name if te else '', te.subjects if te else '', te.room if te else '',
            sl.slot_date if sl else '', sl.start_time if sl else '', sl.end_time if sl else '',
            b.status, b.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    output = out.getvalue()
    return Response(output, mimetype='text/csv',
                    headers={'Content-Disposition':
                             f'attachment; filename=bookings_{ev.event_code}.csv'})


@interviews_bp.route('/admin/bookings/<int:bid>/cancel', methods=['POST'])
@login_required
def admin_booking_cancel(bid):
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    b  = db.query(PIBooking).get(bid) or abort(404)
    b.status       = 'cancelled'
    b.cancelled_at = datetime.now()
    if b.slot:
        b.slot.is_booked = False
    db.commit()
    flash('تم إلغاء الحجز' if get_lang()=='ar' else 'Booking cancelled.', 'success')
    return redirect(url_for('interviews.admin_bookings', event_id=b.event_id))


@interviews_bp.route('/admin/events/<int:event_id>/send-reminders', methods=['POST'])
@login_required
def admin_send_reminders(event_id):
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    bookings = db.query(PIBooking).filter(
        PIBooking.event_id == event_id,
        PIBooking.status == 'confirmed',
        PIBooking.reminder_sent == False,
        PIBooking.parent_email != None,
        PIBooking.parent_email != '',
    ).all()
    sent = 0
    for b in bookings:
        sl = b.slot
        te = sl.teacher if sl else None
        if sl and te:
            _send_reminder(b, ev, te, sl)
            b.reminder_sent = True
            sent += 1
    db.commit()
    flash(f'تم إرسال {sent} تذكير' if get_lang()=='ar' else f'{sent} reminder emails sent.', 'success')
    syslog('PI_REMINDERS', f'Sent {sent} reminders for event {event_id}')
    return redirect(url_for('interviews.admin_bookings', event_id=event_id))


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — Timetable View (print-ready)
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/admin/events/<int:event_id>/timetable')
@login_required
def admin_timetable(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    all_teachers = db.query(PITeacher).filter(PITeacher.event_id == event_id,
                                              PITeacher.is_active == True).all()
    # Filter by teacher_ids if provided (multi-select)
    sel_ids = request.args.getlist('tid', type=int)
    if sel_ids:
        teachers = [t for t in all_teachers if t.id in sel_ids]
    else:
        teachers = all_teachers
    # Build timetable: {date: {teacher_id: [slots]}}
    timetable = {}
    dates = set()
    for t in teachers:
        for s in t.slots:
            dates.add(s.slot_date)
            if s.slot_date not in timetable:
                timetable[s.slot_date] = {}
            if t.id not in timetable[s.slot_date]:
                timetable[s.slot_date][t.id] = []
            timetable[s.slot_date][t.id].append(s)
    dates = sorted(dates)
    for d in timetable:
        for tid in timetable[d]:
            timetable[d][tid].sort(key=lambda s: s.start_time)
    return render_template('interviews/admin/timetable.html',
                           ev=ev, teachers=teachers, all_teachers=all_teachers,
                           timetable=timetable, dates=dates, sel_ids=sel_ids)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — Code Management
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/admin/events/<int:event_id>/codes')
@login_required
def admin_codes(event_id):
    """Code management — view all codes for an event"""
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    teachers = db.query(PITeacher).filter(PITeacher.event_id == event_id).all()
    bookings = db.query(PIBooking).filter(PIBooking.event_id == event_id).all()
    return render_template('interviews/admin/codes.html', ev=ev, teachers=teachers, bookings=bookings)


@interviews_bp.route('/admin/events/<int:event_id>/codes/export')
@login_required
def admin_codes_export(event_id):
    """Export codes as CSV for parent distribution"""
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    teachers = db.query(PITeacher).filter(PITeacher.event_id == event_id).all()
    bookings = db.query(PIBooking).filter(PIBooking.event_id == event_id).all()

    from utils.i18n import get_lang
    _ar = get_lang() == 'ar'
    out = io.StringIO()
    w = csv.writer(out)
    if _ar:
        w.writerow(['النوع', 'الرمز', 'الاسم', 'البريد', 'الملاحظات'])
    else:
        w.writerow(['Type', 'Code', 'Name', 'Email', 'Notes'])
    # Event code
    w.writerow([('رمز الفعالية' if _ar else 'Event Code'), ev.event_code, ev.name, '', ev.school_name or ''])
    # Teacher codes
    for t in teachers:
        w.writerow([('رمز المعلم' if _ar else 'Teacher Code'), t.teacher_code, t.name, t.email or '', t.subjects or ''])
    # Booking refs
    for b in bookings:
        w.writerow([('رمز الحجز' if _ar else 'Booking Ref'), b.booking_ref, b.parent_name, b.parent_email or '', b.child_name])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=codes_{ev.event_code}.csv'})


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — CSV Slot Import
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/admin/events/<int:event_id>/slots/import', methods=['POST'])
@login_required
def admin_slots_import(event_id):
    """Import time slots from CSV"""
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    f = request.files.get('csv_file')
    if not f:
        flash('Please upload a CSV file.', 'danger')
        return redirect(url_for('interviews.admin_teachers', event_id=event_id))

    stream = io.StringIO(f.stream.read().decode('utf-8-sig'))
    reader = csv.DictReader(stream)
    count = 0
    errors = []
    for i, row in enumerate(reader, 2):
        teacher_code = (row.get('teacher_code') or row.get('Teacher Code') or '').strip()
        slot_date = (row.get('date') or row.get('Date') or '').strip()
        start = (row.get('start_time') or row.get('Start Time') or '').strip()
        end = (row.get('end_time') or row.get('End Time') or '').strip()
        status = (row.get('status') or row.get('Status') or 'available').strip().lower()

        if not all([teacher_code, slot_date, start, end]):
            errors.append(f'Row {i}: missing required fields')
            continue

        teacher = db.query(PITeacher).filter(PITeacher.teacher_code == teacher_code, PITeacher.event_id == event_id).first()
        if not teacher:
            errors.append(f'Row {i}: teacher code {teacher_code} not found')
            continue

        is_break = status in ('blocked', 'break', 'unavailable')
        slot = PISlot(
            teacher_id=teacher.id,
            event_id=event_id,
            slot_date=slot_date,
            start_time=start,
            end_time=end,
            is_break=is_break,
        )
        db.add(slot)
        count += 1

    db.commit()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    if count:
        flash((f'تم استيراد {count} فترة زمنية' if ar else f'{count} time slots imported'), 'success')
    if errors:
        flash((f'{len(errors)} أخطاء' if ar else f'{len(errors)} errors: ') + '; '.join(errors[:3]), 'warning')
    return redirect(url_for('interviews.admin_teachers', event_id=event_id))


@interviews_bp.route('/admin/events/<int:event_id>/slots/template')
@login_required
def admin_slots_template(event_id):
    """Download CSV template with full work day (08:00-16:00), available + blocked slots"""
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    teachers = db.query(PITeacher).filter(PITeacher.event_id == event_id).all()
    dur = ev.slot_duration or 10
    brk = ev.break_duration or 0

    # Get event dates or use a sample date
    try:
        dates = json.loads(ev.event_date or '[]')
    except Exception:
        dates = []
    if not dates:
        dates = ['2026-04-01']

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['teacher_code', 'date', 'start_time', 'end_time', 'status'])

    # Generate full day slots for each teacher on each date
    for t in teachers:
        for d in dates[:2]:  # limit to first 2 dates for template size
            current = 8 * 60  # 08:00
            end_day = 16 * 60  # 16:00
            while current + dur <= end_day:
                sh = current // 60
                sm = current % 60
                eh = (current + dur) // 60
                em = (current + dur) % 60
                start_str = f'{sh:02d}:{sm:02d}'
                end_str = f'{eh:02d}:{em:02d}'
                # Mark 12:00-13:00 as blocked (lunch break)
                if sh == 12:
                    status = 'blocked'
                else:
                    status = 'available'
                w.writerow([t.teacher_code, d, start_str, end_str, status])
                current += dur + brk

    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=slots_template_{ev.event_code}.csv'})


# ─────────────────────────────────────────────────────────────────────────────
# HIERARCHY Management (admin) + JSON API (public, for cascading dropdowns)
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/admin/events/<int:event_id>/hierarchy')
@login_required
def admin_hierarchy(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    stages = db.query(PISchoolStage).filter_by(event_id=event_id).order_by(PISchoolStage.sort_order).all()
    teachers = db.query(PITeacher).filter_by(event_id=event_id, is_active=True).order_by(PITeacher.name).all()
    # JSON mode for inline AJAX hierarchy builder in event_form.html
    if request.args.get('json'):
        tree = []
        for st in stages:
            classes_list = []
            for cl in sorted(st.classes, key=lambda c: c.sort_order):
                sections_list = []
                for sec in sorted(cl.sections, key=lambda s: s.sort_order):
                    assignments_list = []
                    for asg in sec.assignments:
                        assignments_list.append({
                            'id': asg.id, 'teacher_id': asg.teacher_id,
                            'teacher_name': asg.teacher.name if asg.teacher else '',
                            'course': asg.course_name or '', 'course_ar': asg.course_name_ar or '',
                            'room': asg.room or '', 'code': asg.assignment_code or '',
                            'is_active': asg.is_active
                        })
                    sections_list.append({'id': sec.id, 'name': sec.name, 'assignments': assignments_list})
                classes_list.append({'id': cl.id, 'name': cl.name, 'name_ar': cl.name_ar or '', 'sections': sections_list})
            tree.append({'id': st.id, 'name': st.name, 'name_ar': st.name_ar or '', 'classes': classes_list})
        teachers_list = [{'id': t.id, 'name': t.name, 'room': t.room or ''} for t in teachers]
        return jsonify({'stages': tree, 'teachers': teachers_list})
    return render_template('interviews/admin/hierarchy.html', ev=ev, stages=stages, teachers=teachers)

# ── Stage CRUD ──
@interviews_bp.route('/admin/events/<int:event_id>/stages/add', methods=['POST'])
@login_required
def admin_stage_add(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    name = request.form.get('name','').strip()
    name_ar = request.form.get('name_ar','').strip()
    if name:
        mx = db.query(PISchoolStage).filter_by(event_id=event_id).count()
        db.add(PISchoolStage(event_id=event_id, name=name, name_ar=name_ar, sort_order=mx))
        db.commit()
    return _ajax_or_redirect(event_id)

@interviews_bp.route('/admin/stages/<int:sid>/edit', methods=['POST'])
@login_required
def admin_stage_edit(sid):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    st = db.query(PISchoolStage).get(sid) or abort(404)
    st.name = request.form.get('name', st.name).strip()
    st.name_ar = request.form.get('name_ar', st.name_ar or '').strip()
    db.commit()
    return _ajax_or_redirect(st.event_id)

@interviews_bp.route('/admin/stages/<int:sid>/delete', methods=['POST'])
@login_required
def admin_stage_delete(sid):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    st = db.query(PISchoolStage).get(sid) or abort(404)
    eid = st.event_id
    db.delete(st); db.commit()
    return _ajax_or_redirect(eid)

# ── Class CRUD ──
@interviews_bp.route('/admin/events/<int:event_id>/classes/add', methods=['POST'])
@login_required
def admin_class_add(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    stage_id = int(request.form.get('stage_id', 0))
    name = request.form.get('name','').strip()
    name_ar = request.form.get('name_ar','').strip()
    if name and stage_id:
        mx = db.query(PISchoolClass).filter_by(stage_id=stage_id).count()
        db.add(PISchoolClass(stage_id=stage_id, event_id=event_id, name=name, name_ar=name_ar, sort_order=mx))
        db.commit()
    return _ajax_or_redirect(event_id)

@interviews_bp.route('/admin/classes/<int:cid>/edit', methods=['POST'])
@login_required
def admin_class_edit(cid):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    cl = db.query(PISchoolClass).get(cid) or abort(404)
    cl.name = request.form.get('name', cl.name).strip()
    cl.name_ar = request.form.get('name_ar', cl.name_ar or '').strip()
    db.commit()
    return _ajax_or_redirect(cl.event_id)

@interviews_bp.route('/admin/classes/<int:cid>/delete', methods=['POST'])
@login_required
def admin_class_delete(cid):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    cl = db.query(PISchoolClass).get(cid) or abort(404)
    eid = cl.event_id
    db.delete(cl); db.commit()
    return _ajax_or_redirect(eid)

# ── Section CRUD ──
@interviews_bp.route('/admin/events/<int:event_id>/sections/add', methods=['POST'])
@login_required
def admin_section_add(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    class_id = int(request.form.get('class_id', 0))
    name = request.form.get('name','').strip()
    if name and class_id:
        mx = db.query(PISection).filter_by(class_id=class_id).count()
        db.add(PISection(class_id=class_id, event_id=event_id, name=name, sort_order=mx))
        db.commit()
    return _ajax_or_redirect(event_id)

@interviews_bp.route('/admin/sections/<int:sid>/delete', methods=['POST'])
@login_required
def admin_section_delete(sid):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    sec = db.query(PISection).get(sid) or abort(404)
    eid = sec.event_id
    db.delete(sec); db.commit()
    return _ajax_or_redirect(eid)

# ── Assignment CRUD ──
@interviews_bp.route('/admin/events/<int:event_id>/assignments/add', methods=['POST'])
@login_required
def admin_assignment_add(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    teacher_id = int(request.form.get('teacher_id', 0))
    section_id = int(request.form.get('section_id', 0))
    course = request.form.get('course_name','').strip()
    course_ar = request.form.get('course_name_ar','').strip()
    room = request.form.get('room','').strip()
    if teacher_id and section_id and course:
        # Build section-based code: get class name + section name for prefix
        sec_obj = db.query(PISection).get(section_id)
        cls_name = sec_obj.school_class.name if sec_obj and sec_obj.school_class else ''
        sec_name = sec_obj.name if sec_obj else ''
        code = _gen_assignment_code(cls_name, sec_name)
        while db.query(PITeacherAssignment).filter_by(assignment_code=code).first():
            code = _gen_assignment_code(cls_name, sec_name)
        db.add(PITeacherAssignment(
            event_id=event_id, teacher_id=teacher_id, section_id=section_id,
            course_name=course, course_name_ar=course_ar, room=room,
            assignment_code=code
        ))
        db.commit()
    return _ajax_or_redirect(event_id)

@interviews_bp.route('/admin/assignments/<int:aid>/edit', methods=['POST'])
@login_required
def admin_assignment_edit(aid):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    a = db.query(PITeacherAssignment).get(aid) or abort(404)
    a.teacher_id = int(request.form.get('teacher_id', a.teacher_id))
    a.course_name = request.form.get('course_name', a.course_name).strip()
    a.course_name_ar = request.form.get('course_name_ar', a.course_name_ar or '').strip()
    a.room = request.form.get('room', a.room or '').strip()
    db.commit()
    return _ajax_or_redirect(a.event_id)

@interviews_bp.route('/admin/assignments/<int:aid>/delete', methods=['POST'])
@login_required
def admin_assignment_delete(aid):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    a = db.query(PITeacherAssignment).get(aid) or abort(404)
    eid = a.event_id
    db.delete(a); db.commit()
    return _ajax_or_redirect(eid)

@interviews_bp.route('/admin/assignments/<int:aid>/generate-slots', methods=['POST'])
@login_required
def admin_assignment_gen_slots(aid):
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    a = db.query(PITeacherAssignment).get(aid) or abort(404)
    teacher = db.query(PITeacher).get(a.teacher_id) or abort(404)
    ev = db.query(PIEvent).get(a.event_id) or abort(404)
    dates_json = ev.event_date or '[]'
    try: dates = json.loads(dates_json)
    except Exception: dates = []
    if not dates:
        from datetime import date as _date
        dates = [_date.today().isoformat()]
    start_t = request.form.get('start_time', '08:00')
    end_t = request.form.get('end_time', '14:00')
    breaks_raw = request.form.get('breaks', '[]')
    try: breaks = json.loads(breaks_raw)
    except Exception: breaks = []
    blocked_raw = request.form.get('blocked', '[]')
    try: blocked = json.loads(blocked_raw)
    except Exception: blocked = []
    # Per-record duration from form or from assignment
    form_dur = request.form.get('slot_duration')
    try: form_dur = int(form_dur) if form_dur else None
    except Exception: form_dur = None
    if form_dur:
        a.slot_duration = form_dur
    total = 0
    def t2m(t):
        h, m = map(int, t.split(':'))
        return h * 60 + m
    def m2t(m):
        return f"{m//60:02d}:{m%60:02d}"
    for d in dates:
        # Delete existing unbooked slots for this assignment+date
        for s in db.query(PISlot).filter(
            PISlot.assignment_id == aid, PISlot.slot_date == d, PISlot.is_booked == False
        ).all():
            db.delete(s)
        db.flush()
        cur = t2m(start_t)
        end = t2m(end_t)
        dur = a.slot_duration or ev.slot_duration or 5
        brk_dur = ev.break_duration or 0
        while cur + dur <= end:
            ss, se = m2t(cur), m2t(cur + dur)
            # Check if in blocked period — skip entirely
            is_blocked = False
            for bp in blocked:
                bs, be = t2m(bp.get('start','00:00')), t2m(bp.get('end','00:00'))
                if cur >= bs and cur < be: is_blocked = True; break
            if is_blocked:
                cur += dur
                continue
            # Check if in break period
            is_brk = False
            for b in breaks:
                bs, be = t2m(b.get('start','00:00')), t2m(b.get('end','00:00'))
                if cur >= bs and cur < be: is_brk = True; break
            db.add(PISlot(teacher_id=teacher.id, event_id=ev.id, assignment_id=aid,
                          slot_date=d, start_time=ss, end_time=se, is_break=is_brk))
            total += 1
            cur += dur + brk_dur
    db.commit()
    flash(f'تم إنشاء {total} فترة زمنية' if get_lang()=='ar' else f'Created {total} time slots', 'success')
    return _ajax_or_redirect(a.event_id)

# ── Event Date Management ──
@interviews_bp.route('/admin/events/<int:event_id>/add-date', methods=['POST'])
@login_required
def admin_event_add_date(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    data = request.get_json(silent=True) or {}
    new_date = data.get('date', '').strip()
    if not new_date:
        return jsonify({'ok': False, 'error': 'No date provided'})
    try: dates = json.loads(ev.event_date or '[]')
    except Exception: dates = []
    if new_date not in dates:
        dates.append(new_date)
        dates.sort()
        ev.event_date = json.dumps(dates)
        db.commit()
    return jsonify({'ok': True, 'dates': dates})


@interviews_bp.route('/admin/events/<int:event_id>/remove-date', methods=['POST'])
@login_required
def admin_event_remove_date(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    data = request.get_json(silent=True) or {}
    rm_date = data.get('date', '').strip()
    try: dates = json.loads(ev.event_date or '[]')
    except Exception: dates = []
    if rm_date in dates:
        dates.remove(rm_date)
        ev.event_date = json.dumps(dates)
        db.commit()
    return jsonify({'ok': True, 'dates': dates})


@interviews_bp.route('/admin/events/<int:event_id>/update-settings', methods=['POST'])
@login_required
def admin_event_update_settings(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    data = request.get_json(silent=True) or {}
    if 'school_name' in data:
        ev.school_name = (data['school_name'] or '').strip()
    if 'school_logo_url' in data:
        ev.school_logo_url = (data['school_logo_url'] or '').strip()
    db.commit()
    return jsonify({'ok': True})


@interviews_bp.route('/admin/events/<int:event_id>/send-teacher-emails', methods=['POST'])
@login_required
def admin_send_teacher_emails(event_id):
    """Send access code emails to all teachers with an email address."""
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    from utils.email_helper import send_email
    from utils.i18n import get_lang
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    teachers = db.query(PITeacher).filter_by(event_id=event_id, is_active=True).all()
    ar = get_lang() == 'ar'
    d = 'rtl' if ar else 'ltr'
    sent = 0
    logo_html = ''
    if ev.school_logo_url:
        logo_html = f'<img src="{ev.school_logo_url}" alt="logo" style="height:48px;max-width:160px;object-fit:contain;margin-bottom:8px;display:block">'
    for t in teachers:
        if not t.email or not t.teacher_code:
            continue
        portal_url = request.host_url.rstrip('/') + url_for('interviews.teacher_timetable', teacher_code=t.teacher_code)
        subject = f"رابط بوابة المقابلات — {ev.name}" if ar else f"Your Interview Portal Access — {ev.name}"
        greeting = f"عزيزي {t.name}،" if ar else f"Dear {t.name},"
        msg = "تمت إضافتك إلى فعالية مقابلات. استخدم الرابط أدناه لعرض جدولك:" if ar else "You have been added to an interview event. Use the link below to view your schedule:"
        lbl_code = "رمز الدخول الخاص بك" if ar else "Your Access Code"
        lbl_btn = "فتح البوابة" if ar else "Open My Portal"
        body = f"""
<div style="font-family:sans-serif;max-width:600px;margin:auto;direction:{d}">
<div style="background:{ev.brand_color or '#0d6efd'};color:white;padding:20px;border-radius:8px 8px 0 0;text-align:center">
  {logo_html}
  <h2 style="margin:0">{ev.school_name or 'School'}</h2>
  <p style="margin:5px 0 0;opacity:.9">{ev.name}</p>
</div>
<div style="padding:24px;border:1px solid #dee2e6;border-top:none;border-radius:0 0 8px 8px">
  <p>{greeting}</p>
  <p>{msg}</p>
  <div style="background:#f8f9fa;border-radius:8px;padding:16px;margin:16px 0;text-align:center">
    <div style="font-size:.85rem;color:#6c757d;margin-bottom:8px">{lbl_code}</div>
    <div style="font-size:1.4rem;font-weight:800;letter-spacing:4px;color:#0f172a">{t.teacher_code}</div>
  </div>
  <div style="text-align:center">
    <a href="{portal_url}" style="display:inline-block;background:{ev.brand_color or '#0d6efd'};color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700">{lbl_btn}</a>
  </div>
</div>
</div>"""
        send_email(to_email=t.email, to_name=t.name, subject=subject, html_body=body,
                   email_type='teacher_access_code')
        sent += 1
    return jsonify({'ok': True, 'sent': sent})


@interviews_bp.route('/admin/events/<int:event_id>/print-teacher-codes')
@login_required
def admin_print_teacher_codes(event_id):
    """Printable page with all teacher codes."""
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    teachers = db.query(PITeacher).filter_by(event_id=event_id, is_active=True).order_by(PITeacher.name).all()
    return render_template('interviews/admin/print_teacher_codes.html', ev=ev, teachers=teachers)


@interviews_bp.route('/admin/teachers/<int:tid>/upload-photo', methods=['POST'])
@login_required
def admin_teacher_upload_photo(tid):
    """Upload teacher photo — stored as base64 data URI in photo_url."""
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    t = db.query(PITeacher).get(tid) or abort(404)
    f = request.files.get('photo')
    if not f:
        return jsonify({'ok': False, 'error': 'No file'})
    data = f.read()
    if len(data) > 2 * 1024 * 1024:  # 2MB limit
        return jsonify({'ok': False, 'error': 'File too large (max 2MB)'})
    mime = f.content_type or 'image/jpeg'
    b64 = base64.b64encode(data).decode('ascii')
    t.photo_url = f'data:{mime};base64,{b64}'
    db.commit()
    return jsonify({'ok': True, 'photo_url': t.photo_url})


@interviews_bp.route('/admin/teachers/<int:tid>/upload-attachment', methods=['POST'])
@login_required
def admin_teacher_upload_attachment(tid):
    """Upload attachment (PDF, DOCX, XLSX, PPTX) — stored as base64 in attachments_json."""
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    t = db.query(PITeacher).get(tid) or abort(404)
    f = request.files.get('file')
    if not f:
        return jsonify({'ok': False, 'error': 'No file'})
    allowed = {'pdf', 'docx', 'xlsx', 'pptx', 'doc', 'xls', 'ppt'}
    ext = (f.filename or '').rsplit('.', 1)[-1].lower()
    if ext not in allowed:
        return jsonify({'ok': False, 'error': f'File type .{ext} not allowed. Allowed: {", ".join(allowed)}'})
    data = f.read()
    if len(data) > 5 * 1024 * 1024:  # 5MB limit
        return jsonify({'ok': False, 'error': 'File too large (max 5MB)'})
    mime = f.content_type or 'application/octet-stream'
    b64 = base64.b64encode(data).decode('ascii')
    try:
        attachments = json.loads(t.attachments_json or '[]')
    except Exception as e:
        current_app.logger.warning(f"{__name__} error: {e}")
        attachments = []
    attachments.append({
        'name': f.filename,
        'ext': ext,
        'mime': mime,
        'size': len(data),
        'data': b64,
        'uploaded_at': datetime.now().isoformat()
    })
    t.attachments_json = json.dumps(attachments)
    db.commit()
    return jsonify({'ok': True, 'count': len(attachments)})


@interviews_bp.route('/admin/teachers/<int:tid>/delete-attachment/<int:idx>', methods=['POST'])
@login_required
def admin_teacher_delete_attachment(tid, idx):
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    t = db.query(PITeacher).get(tid) or abort(404)
    try:
        attachments = json.loads(t.attachments_json or '[]')
    except Exception as e:
        current_app.logger.warning(f"{__name__} error: {e}")
        attachments = []
    if 0 <= idx < len(attachments):
        attachments.pop(idx)
        t.attachments_json = json.dumps(attachments)
        db.commit()
    return jsonify({'ok': True})


@interviews_bp.route('/admin/teachers/<int:tid>/attachment/<int:idx>')
@login_required
def admin_teacher_download_attachment(tid, idx):
    """Download a teacher's attachment by index."""
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    t = db.query(PITeacher).get(tid) or abort(404)
    try:
        attachments = json.loads(t.attachments_json or '[]')
    except Exception as e:
        current_app.logger.warning(f"{__name__} error: {e}")
        attachments = []
    if idx < 0 or idx >= len(attachments):
        abort(404)
    att = attachments[idx]
    data = base64.b64decode(att['data'])
    return Response(data, mimetype=att.get('mime', 'application/octet-stream'),
                    headers={'Content-Disposition': f'attachment; filename="{att["name"]}"'})


# ── Hierarchy CSV Import ──
@interviews_bp.route('/admin/events/<int:event_id>/hierarchy/import', methods=['POST'])
@login_required
def admin_hierarchy_import(event_id):
    from utils.i18n import get_lang
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    f = request.files.get('csv_file')
    if not f:
        flash('No file uploaded', 'danger')
        return _ajax_or_redirect(event_id)
    content = f.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    count = 0
    for row in reader:
        stage_name = (row.get('stage') or row.get('المرحلة') or '').strip()
        class_name = (row.get('class') or row.get('الصف') or '').strip()
        section_name = (row.get('section') or row.get('الشعبة') or '').strip()
        teacher_name = (row.get('teacher') or row.get('المعلم') or '').strip()
        teacher_email = (row.get('email') or row.get('البريد') or '').strip()
        course = (row.get('course') or row.get('المادة') or '').strip()
        room = (row.get('room') or row.get('الغرفة') or '').strip()
        if not (stage_name and class_name and section_name and teacher_name and course):
            continue
        # Find or create stage
        stage = db.query(PISchoolStage).filter_by(event_id=event_id, name=stage_name).first()
        if not stage:
            stage = PISchoolStage(event_id=event_id, name=stage_name, sort_order=0)
            db.add(stage); db.flush()
        # Find or create class
        cls = db.query(PISchoolClass).filter_by(stage_id=stage.id, name=class_name).first()
        if not cls:
            cls = PISchoolClass(stage_id=stage.id, event_id=event_id, name=class_name, sort_order=0)
            db.add(cls); db.flush()
        # Find or create section
        sec = db.query(PISection).filter_by(class_id=cls.id, name=section_name).first()
        if not sec:
            sec = PISection(class_id=cls.id, event_id=event_id, name=section_name, sort_order=0)
            db.add(sec); db.flush()
        # Find or create teacher
        teacher = db.query(PITeacher).filter_by(event_id=event_id, name=teacher_name).first()
        if not teacher:
            teacher = PITeacher(event_id=event_id, name=teacher_name, email=teacher_email,
                                room=room, teacher_code=_gen_teacher_code(), is_active=True)
            db.add(teacher); db.flush()
        # Create assignment with section-based code (e.g. 1A-K7M2)
        code = _gen_assignment_code(class_name, section_name)
        while db.query(PITeacherAssignment).filter_by(assignment_code=code).first():
            code = _gen_assignment_code(class_name, section_name)
        db.add(PITeacherAssignment(
            event_id=event_id, teacher_id=teacher.id, section_id=sec.id,
            course_name=course, room=room, assignment_code=code
        ))
        count += 1
    db.commit()
    flash(f'تم استيراد {count} تعيين' if get_lang()=='ar' else f'Imported {count} assignments', 'success')
    return _ajax_or_redirect(event_id)


# ─────────────────────────────────────────────────────────────────────────────
# DATA ENTRY Screen (new unified admin view)
# ─────────────────────────────────────────────────────────────────────────────

def _flatten_assignments(db, event_id):
    """Return flat list of assignment rows for the data entry table."""
    assignments = db.query(PITeacherAssignment).filter_by(
        event_id=event_id, is_active=True
    ).order_by(PITeacherAssignment.id).all()
    rows = []
    for a in assignments:
        sec = a.section
        cls = sec.school_class if sec else None
        stage = cls.stage if cls else None
        teacher = a.teacher
        slot_count = db.query(PISlot).filter(
            PISlot.assignment_id == a.id, PISlot.is_break == False
        ).count()
        try:
            att_list = json.loads(teacher.attachments_json or '[]') if teacher else []
        except Exception as e:
            current_app.logger.warning(f"{__name__} error: {e}")
            att_list = []
        rows.append({
            'aid': a.id,
            'tid': teacher.id if teacher else 0,
            'stage': stage.name if stage else '',
            'cls': cls.name if cls else '',
            'section': sec.name if sec else '',
            'course': a.course_name or '',
            'teacher': teacher.name if teacher else '',
            'email': teacher.email if teacher else '',
            'room': a.room or '',
            'code': a.assignment_code or '',
            'slot_count': slot_count,
            'section_id': sec.id if sec else 0,
            'photo_url': (teacher.photo_url or '') if teacher else '',
            'attachments': att_list,
            'slot_duration': a.slot_duration,
        })
    return rows


@interviews_bp.route('/admin/events/<int:event_id>/data-entry')
@login_required
def admin_data_entry(event_id):
    """Unified data entry table for an event."""
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    rows = _flatten_assignments(db, event_id)
    try: event_dates = json.loads(ev.event_date or '[]')
    except Exception: event_dates = []
    return render_template('interviews/admin/data_entry.html', ev=ev, rows=rows, event_dates=event_dates)


@interviews_bp.route('/admin/events/<int:event_id>/data-entry/save', methods=['POST'])
@login_required
def admin_data_entry_save(event_id):
    """Bulk save rows — find-or-create stages/classes/sections/teachers/assignments."""
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    data = request.get_json(force=True)
    rows = data.get('rows', [])
    saved = []
    for row in rows:
        stage_name = (row.get('stage') or '').strip()
        class_name = (row.get('class') or '').strip()
        section_name = (row.get('section') or '').strip()
        course = (row.get('course') or '').strip()
        teacher_name = (row.get('teacher') or '').strip()
        teacher_email = (row.get('email') or '').strip()
        room = (row.get('room') or '').strip()
        aid = int(row.get('aid') or 0)
        if not (stage_name and class_name and section_name and teacher_name and course):
            continue
        # Find or create stage
        stage = db.query(PISchoolStage).filter_by(event_id=event_id, name=stage_name).first()
        if not stage:
            stage = PISchoolStage(event_id=event_id, name=stage_name, sort_order=0)
            db.add(stage); db.flush()
        # Find or create class
        cls = db.query(PISchoolClass).filter_by(stage_id=stage.id, name=class_name).first()
        if not cls:
            cls = PISchoolClass(stage_id=stage.id, event_id=event_id, name=class_name, sort_order=0)
            db.add(cls); db.flush()
        # Find or create section
        sec = db.query(PISection).filter_by(class_id=cls.id, name=section_name).first()
        if not sec:
            sec = PISection(class_id=cls.id, event_id=event_id, name=section_name, sort_order=0)
            db.add(sec); db.flush()
        # Find or create teacher
        teacher = db.query(PITeacher).filter_by(event_id=event_id, name=teacher_name).first()
        if not teacher:
            teacher = PITeacher(event_id=event_id, name=teacher_name, email=teacher_email,
                                room=room, teacher_code=_gen_teacher_code(), is_active=True)
            db.add(teacher); db.flush()
        elif teacher_email and not teacher.email:
            teacher.email = teacher_email
        # Update or create assignment
        if aid:
            a = db.query(PITeacherAssignment).get(aid)
            if a and a.event_id == event_id:
                a.teacher_id = teacher.id; a.section_id = sec.id
                a.course_name = course; a.room = room
                saved.append({'aid': a.id, 'code': a.assignment_code})
                continue
        # Check duplicate
        existing = db.query(PITeacherAssignment).filter_by(
            event_id=event_id, teacher_id=teacher.id, section_id=sec.id, course_name=course
        ).first()
        if existing:
            saved.append({'aid': existing.id, 'code': existing.assignment_code})
            continue
        code = _gen_assignment_code(class_name, section_name)
        while db.query(PITeacherAssignment).filter_by(assignment_code=code).first():
            code = _gen_assignment_code(class_name, section_name)
        # Per-record slot duration
        row_dur = row.get('slot_duration')
        try: row_dur = int(row_dur) if row_dur else None
        except Exception: row_dur = None
        a = PITeacherAssignment(
            event_id=event_id, teacher_id=teacher.id, section_id=sec.id,
            course_name=course, room=room, assignment_code=code,
            slot_duration=row_dur
        )
        db.add(a); db.flush()
        saved.append({'aid': a.id, 'code': a.assignment_code})
        # Generate time slots if slot_start/slot_end provided
        slot_start = (row.get('slot_start') or '').strip()
        slot_end = (row.get('slot_end') or '').strip()
        if slot_start and slot_end:
            try:
                dates = json.loads(ev.event_date or '[]')
                if not dates:
                    from datetime import date as _date
                    dates = [_date.today().isoformat()]
                breaks = []
                brk_s = (row.get('break_start') or '').strip()
                brk_e = (row.get('break_end') or '').strip()
                if brk_s and brk_e: breaks.append({'start': brk_s, 'end': brk_e})
                blocked = []
                blk_s = (row.get('blocked_start') or '').strip()
                blk_e = (row.get('blocked_end') or '').strip()
                if blk_s and blk_e: blocked.append({'start': blk_s, 'end': blk_e})
                def t2m(t):
                    h, m = map(int, t.split(':'))
                    return h * 60 + m
                def m2t(m):
                    return f"{m//60:02d}:{m%60:02d}"
                dur = a.slot_duration or ev.slot_duration or 5
                brk_dur = ev.break_duration or 0
                for d_str in dates:
                    cur = t2m(slot_start)
                    end_m = t2m(slot_end)
                    while cur + dur <= end_m:
                        ss, se = m2t(cur), m2t(cur + dur)
                        is_blocked = any(cur >= t2m(bp['start']) and cur < t2m(bp['end']) for bp in blocked)
                        if is_blocked: cur += dur; continue
                        is_brk = any(cur >= t2m(b['start']) and cur < t2m(b['end']) for b in breaks)
                        db.add(PISlot(teacher_id=teacher.id, event_id=ev.id, assignment_id=a.id,
                                      slot_date=d_str, start_time=ss, end_time=se, is_break=is_brk))
                        cur += dur + brk_dur
            except Exception as e:
                current_app.logger.warning(f"Inline slot generation error: {e}")
    db.commit()
    return jsonify({'ok': True, 'saved': saved, 'count': len(saved)})


@interviews_bp.route('/admin/events/<int:event_id>/data-entry/import', methods=['POST'])
@login_required
def admin_data_entry_import(event_id):
    """CSV import for data entry — returns JSON for AJAX."""
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    f = request.files.get('csv_file')
    if not f:
        return jsonify({'ok': False, 'error': 'No file uploaded'})
    content = f.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    count = 0
    for row in reader:
        stage_name = (row.get('stage') or row.get('المرحلة') or '').strip()
        class_name = (row.get('class') or row.get('الصف') or '').strip()
        section_name = (row.get('section') or row.get('الشعبة') or '').strip()
        teacher_name = (row.get('teacher') or row.get('المعلم') or '').strip()
        teacher_email = (row.get('email') or row.get('البريد') or '').strip()
        course = (row.get('course') or row.get('المادة') or '').strip()
        room = (row.get('room') or row.get('الغرفة') or '').strip()
        if not (stage_name and class_name and section_name and teacher_name and course):
            continue
        stage = db.query(PISchoolStage).filter_by(event_id=event_id, name=stage_name).first()
        if not stage:
            stage = PISchoolStage(event_id=event_id, name=stage_name, sort_order=0)
            db.add(stage); db.flush()
        cls = db.query(PISchoolClass).filter_by(stage_id=stage.id, name=class_name).first()
        if not cls:
            cls = PISchoolClass(stage_id=stage.id, event_id=event_id, name=class_name, sort_order=0)
            db.add(cls); db.flush()
        sec = db.query(PISection).filter_by(class_id=cls.id, name=section_name).first()
        if not sec:
            sec = PISection(class_id=cls.id, event_id=event_id, name=section_name, sort_order=0)
            db.add(sec); db.flush()
        teacher = db.query(PITeacher).filter_by(event_id=event_id, name=teacher_name).first()
        if not teacher:
            teacher = PITeacher(event_id=event_id, name=teacher_name, email=teacher_email,
                                room=room, teacher_code=_gen_teacher_code(), is_active=True)
            db.add(teacher); db.flush()
        existing = db.query(PITeacherAssignment).filter_by(
            event_id=event_id, teacher_id=teacher.id, section_id=sec.id, course_name=course
        ).first()
        if existing: continue
        code = _gen_assignment_code(class_name, section_name)
        while db.query(PITeacherAssignment).filter_by(assignment_code=code).first():
            code = _gen_assignment_code(class_name, section_name)
        # Per-record slot duration from CSV
        csv_dur = (row.get('slot_duration') or row.get('مدة_المقابلة') or '').strip()
        try: csv_dur = int(csv_dur) if csv_dur else None
        except Exception: csv_dur = None
        a = PITeacherAssignment(
            event_id=event_id, teacher_id=teacher.id, section_id=sec.id,
            course_name=course, room=room, assignment_code=code,
            slot_duration=csv_dur
        )
        db.add(a); db.flush()
        count += 1
        # Generate slots from CSV columns if provided
        slot_start = (row.get('slot_start') or '').strip()
        slot_end = (row.get('slot_end') or '').strip()
        if slot_start and slot_end:
            try:
                dates_json = ev.event_date or '[]'
                dates = json.loads(dates_json) if dates_json else []
                if not dates:
                    from datetime import date as _date
                    dates = [_date.today().isoformat()]
                breaks = []
                brk_s = (row.get('break_start') or '').strip()
                brk_e = (row.get('break_end') or '').strip()
                if brk_s and brk_e:
                    breaks.append({'start': brk_s, 'end': brk_e})
                blocked = []
                blk_s = (row.get('blocked_start') or '').strip()
                blk_e = (row.get('blocked_end') or '').strip()
                if blk_s and blk_e:
                    blocked.append({'start': blk_s, 'end': blk_e})
                def t2m(t):
                    h, m = map(int, t.split(':'))
                    return h * 60 + m
                def m2t(m):
                    return f"{m//60:02d}:{m%60:02d}"
                dur = a.slot_duration or ev.slot_duration or 5
                brk_dur = ev.break_duration or 0
                for d_str in dates:
                    cur = t2m(slot_start)
                    end_m = t2m(slot_end)
                    while cur + dur <= end_m:
                        ss, se = m2t(cur), m2t(cur + dur)
                        is_blocked = False
                        for bp in blocked:
                            bs, be = t2m(bp['start']), t2m(bp['end'])
                            if cur >= bs and cur < be: is_blocked = True; break
                        if is_blocked:
                            cur += dur; continue
                        is_brk = False
                        for b in breaks:
                            bs, be = t2m(b['start']), t2m(b['end'])
                            if cur >= bs and cur < be: is_brk = True; break
                        db.add(PISlot(teacher_id=teacher.id, event_id=ev.id, assignment_id=a.id,
                                      slot_date=d_str, start_time=ss, end_time=se, is_break=is_brk))
                        cur += dur + brk_dur
            except Exception as e:
                current_app.logger.warning(f"Slot generation from CSV error: {e}")
    db.commit()
    return jsonify({'ok': True, 'count': count})


@interviews_bp.route('/admin/events/<int:event_id>/data-entry/template')
@login_required
def admin_data_entry_template(event_id):
    """Download CSV template for data entry with instructions."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['stage', 'class', 'section', 'course', 'teacher', 'email', 'room',
                      'slot_duration', 'slot_start', 'slot_end', 'break_start', 'break_end', 'blocked_start', 'blocked_end'])
    writer.writerow(['Primary', 'Grade 1', 'A', 'Mathematics', 'Ahmed Ali', 'ahmed@school.com', '101',
                      '10', '08:00', '14:00', '10:00', '10:30', '12:00', '13:00'])
    writer.writerow(['Primary', 'Grade 1', 'A', 'Science', 'Sara Mohammed', 'sara@school.com', '102',
                      '5', '08:00', '14:00', '', '', '', ''])
    writer.writerow([])
    writer.writerow(['# INSTRUCTIONS / تعليمات:'])
    writer.writerow(['# stage: School stage (e.g. Primary, Secondary) / المرحلة الدراسية'])
    writer.writerow(['# class: Class name (e.g. Grade 1) / اسم الصف'])
    writer.writerow(['# section: Section letter (e.g. A, B) / رمز الشعبة'])
    writer.writerow(['# course: Subject/course name / اسم المبحث'])
    writer.writerow(['# teacher: Teacher full name / اسم المعلم'])
    writer.writerow(['# email: Teacher email (for sending codes) / بريد المعلم'])
    writer.writerow(['# room: Room number / رقم الغرفة'])
    writer.writerow(['# slot_duration: Meeting duration in minutes (e.g. 5, 10, 15) / مدة المقابلة بالدقائق'])
    writer.writerow(['# slot_start: Time slots start (HH:MM) / بداية الفترات الزمنية'])
    writer.writerow(['# slot_end: Time slots end (HH:MM) / نهاية الفترات الزمنية'])
    writer.writerow(['# break_start/break_end: Break period (HH:MM) / فترة الراحة'])
    writer.writerow(['# blocked_start/blocked_end: Blocked period - no slots created (HH:MM) / فترة الحظر'])
    writer.writerow(['# Same teacher can appear multiple times for different classes/sections'])
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=data_entry_template.csv'})


@interviews_bp.route('/admin/events/<int:event_id>/data-entry/export')
@login_required
def admin_data_entry_export(event_id):
    """Export all assignments as CSV."""
    perm = get_permissions()
    if not perm.is_admin_or_manager(): abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    rows = _flatten_assignments(db, event_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['stage', 'class', 'section', 'course', 'teacher', 'email', 'room', 'code', 'slots'])
    for r in rows:
        writer.writerow([r['stage'], r['cls'], r['section'], r['course'],
                         r['teacher'], r['email'], r['room'], r['code'], r['slot_count']])
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={ev.name}_data_{datetime.now().strftime("%Y%m%d")}.csv'})


# ── Parent Table View (redesigned booking flow) ──

@interviews_bp.route('/book/<int:event_id>/parent-table')
def book_parent_table(event_id):
    """Parent sees a table: Stage | Class | Section | Booking Code"""
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    if not ev.is_open or not ev.is_active:
        return redirect(url_for('interviews.book_welcome'))
    session['pi_event_id'] = ev.id
    session['pi_event_code'] = ev.event_code
    # Build unique rows: one per section, using first assignment code
    assignments = db.query(PITeacherAssignment).filter_by(
        event_id=event_id, is_active=True).all()
    seen = {}
    rows = []
    for a in assignments:
        sec = a.section
        if not sec or sec.id in seen: continue
        seen[sec.id] = True
        cls = sec.school_class if sec else None
        stage = cls.stage if cls else None
        rows.append({
            'stage': stage.name if stage else '',
            'cls': cls.name if cls else '',
            'section': sec.name if sec else '',
            'code': a.assignment_code or '',
            'section_id': sec.id,
        })
    return render_template('interviews/book/parent_table.html', ev=ev, rows=rows)


# ── JSON API for cascading dropdown filters (public, no login required) ──

@interviews_bp.route('/api/events/<int:event_id>/stages')
def api_stages(event_id):
    db = get_db()
    stages = db.query(PISchoolStage).filter_by(event_id=event_id).order_by(PISchoolStage.sort_order).all()
    return jsonify([{'id': s.id, 'name': s.name, 'name_ar': s.name_ar or s.name} for s in stages])

@interviews_bp.route('/api/events/<int:event_id>/classes')
def api_classes(event_id):
    db = get_db()
    stage_id = request.args.get('stage_id', type=int)
    q = db.query(PISchoolClass).filter_by(event_id=event_id)
    if stage_id: q = q.filter_by(stage_id=stage_id)
    classes = q.order_by(PISchoolClass.sort_order).all()
    return jsonify([{'id': c.id, 'name': c.name, 'name_ar': c.name_ar or c.name} for c in classes])

@interviews_bp.route('/api/events/<int:event_id>/sections')
def api_sections(event_id):
    db = get_db()
    class_id = request.args.get('class_id', type=int)
    q = db.query(PISection).filter_by(event_id=event_id)
    if class_id: q = q.filter_by(class_id=class_id)
    sections = q.order_by(PISection.sort_order).all()
    return jsonify([{'id': s.id, 'name': s.name} for s in sections])

@interviews_bp.route('/api/events/<int:event_id>/teachers')
def api_teachers(event_id):
    db = get_db()
    section_id = request.args.get('section_id', type=int)
    if section_id:
        assignments = db.query(PITeacherAssignment).filter_by(
            event_id=event_id, section_id=section_id, is_active=True).all()
        teacher_ids = list(set(a.teacher_id for a in assignments))
        teachers = db.query(PITeacher).filter(PITeacher.id.in_(teacher_ids)).all() if teacher_ids else []
    else:
        teachers = db.query(PITeacher).filter_by(event_id=event_id, is_active=True).all()
    return jsonify([{'id': t.id, 'name': t.name, 'subjects': t.subjects or '', 'room': t.room or ''} for t in teachers])

@interviews_bp.route('/api/events/<int:event_id>/courses')
def api_courses(event_id):
    db = get_db()
    section_id = request.args.get('section_id', type=int)
    teacher_id = request.args.get('teacher_id', type=int)
    q = db.query(PITeacherAssignment).filter_by(event_id=event_id, is_active=True)
    if section_id: q = q.filter_by(section_id=section_id)
    if teacher_id: q = q.filter_by(teacher_id=teacher_id)
    assignments = q.all()
    return jsonify([{
        'id': a.id, 'assignment_code': a.assignment_code,
        'course_name': a.course_name, 'course_name_ar': a.course_name_ar or a.course_name,
        'room': a.room or '', 'teacher_id': a.teacher_id
    } for a in assignments])

@interviews_bp.route('/api/events/<int:event_id>/slots')
def api_slots(event_id):
    db = get_db()
    assignment_id = request.args.get('assignment_id', type=int)
    if not assignment_id:
        return jsonify([])
    slots = db.query(PISlot).filter(
        PISlot.assignment_id == assignment_id,
        PISlot.is_break == False,
        PISlot.is_booked == False
    ).order_by(PISlot.slot_date, PISlot.start_time).all()
    by_date = {}
    for s in slots:
        by_date.setdefault(s.slot_date, []).append({
            'id': s.id, 'start': s.start_time, 'end': s.end_time
        })
    return jsonify({'dates': by_date})


# ─────────────────────────────────────────────────────────────────────────────
# TEACHER Portal
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/teacher/<string:teacher_code>')
def teacher_timetable(teacher_code):
    db = get_db()
    teacher = db.query(PITeacher).filter(PITeacher.teacher_code == teacher_code).first()
    if not teacher:
        abort(404)
    ev = teacher.event
    slots = db.query(PISlot).filter(PISlot.teacher_id == teacher.id).order_by(
        PISlot.slot_date, PISlot.start_time).all()
    # Group by date
    by_date = {}
    for s in slots:
        by_date.setdefault(s.slot_date, []).append(s)
    dates = sorted(by_date.keys())
    # Assignment details for header table
    assignments = db.query(PITeacherAssignment).filter_by(
        teacher_id=teacher.id, event_id=ev.id, is_active=True).all()
    assignment_info = []
    for a in assignments:
        sec = a.section
        cls = sec.school_class if sec else None
        stage = cls.stage if cls else None
        assignment_info.append({
            'stage': stage.name if stage else '',
            'cls': cls.name if cls else '',
            'section': sec.name if sec else '',
            'course': a.course_name or '',
            'room': a.room or '',
            'code': a.assignment_code or '',
        })
    # Free slots for this teacher (for change-time feature)
    free_slots = db.query(PISlot).filter(
        PISlot.teacher_id == teacher.id,
        PISlot.is_booked == False,
        PISlot.is_break == False
    ).order_by(PISlot.slot_date, PISlot.start_time).all()
    # Other teachers in same event (for substitute feature)
    other_teachers = db.query(PITeacher).filter(
        PITeacher.event_id == ev.id,
        PITeacher.is_active == True,
        PITeacher.id != teacher.id
    ).all()
    return render_template('interviews/teacher/timetable.html',
                           teacher=teacher, ev=ev, by_date=by_date, dates=dates,
                           assignments=assignment_info,
                           free_slots=free_slots, other_teachers=other_teachers)


@interviews_bp.route('/teacher/<string:teacher_code>/cancel/<int:bid>', methods=['POST'])
def teacher_cancel_booking(teacher_code, bid):
    """Teachers are not allowed to cancel bookings — admin only."""
    abort(403)


@interviews_bp.route('/teacher/<string:teacher_code>/change-time/<int:bid>', methods=['POST'])
def teacher_change_time(teacher_code, bid):
    """Teacher moves a booking to a different available slot of their own."""
    db = get_db()
    teacher = db.query(PITeacher).filter(PITeacher.teacher_code == teacher_code).first()
    if not teacher:
        abort(404)
    booking = db.query(PIBooking).get(bid)
    if not booking or not booking.slot or booking.slot.teacher_id != teacher.id:
        abort(403)
    new_slot_id = request.form.get('new_slot_id', type=int)
    new_slot = db.query(PISlot).get(new_slot_id) if new_slot_id else None
    if not new_slot or new_slot.is_booked or new_slot.is_break or new_slot.teacher_id != teacher.id:
        return redirect(url_for('interviews.teacher_timetable', teacher_code=teacher_code))
    old_slot = booking.slot
    old_slot.is_booked = False
    new_slot.is_booked = True
    booking.slot_id = new_slot.id
    db.commit()
    return redirect(url_for('interviews.teacher_timetable', teacher_code=teacher_code))


@interviews_bp.route('/teacher/<string:teacher_code>/substitute/<int:bid>', methods=['POST'])
def teacher_substitute(teacher_code, bid):
    """Teacher transfers a booking to another teacher's available slot."""
    db = get_db()
    teacher = db.query(PITeacher).filter(PITeacher.teacher_code == teacher_code).first()
    if not teacher:
        abort(404)
    booking = db.query(PIBooking).get(bid)
    if not booking or not booking.slot or booking.slot.teacher_id != teacher.id:
        abort(403)
    new_slot_id = request.form.get('new_slot_id', type=int)
    new_slot = db.query(PISlot).get(new_slot_id) if new_slot_id else None
    if not new_slot or new_slot.is_booked or new_slot.is_break:
        return redirect(url_for('interviews.teacher_timetable', teacher_code=teacher_code))
    old_slot = booking.slot
    old_slot.is_booked = False
    new_slot.is_booked = True
    booking.slot_id = new_slot.id
    db.commit()
    return redirect(url_for('interviews.teacher_timetable', teacher_code=teacher_code))


@interviews_bp.route('/teacher/<string:teacher_code>/merge', methods=['POST'])
def teacher_merge_bookings(teacher_code):
    """Teacher merges two bookings — extends first slot to cover second, frees second."""
    db = get_db()
    teacher = db.query(PITeacher).filter(PITeacher.teacher_code == teacher_code).first()
    if not teacher:
        abort(404)
    bid1 = request.form.get('bid1', type=int)
    bid2 = request.form.get('bid2', type=int)
    b1 = db.query(PIBooking).get(bid1) if bid1 else None
    b2 = db.query(PIBooking).get(bid2) if bid2 else None
    if not b1 or not b2:
        return redirect(url_for('interviews.teacher_timetable', teacher_code=teacher_code))
    if b1.slot.teacher_id != teacher.id or b2.slot.teacher_id != teacher.id:
        abort(403)
    s1, s2 = b1.slot, b2.slot
    s1.end_time = s2.end_time
    s2.is_booked = False
    b2.status = 'cancelled'
    b2.comment = (b2.comment or '') + f' [Merged into {b1.booking_ref}]'
    db.commit()
    return redirect(url_for('interviews.teacher_timetable', teacher_code=teacher_code))


@interviews_bp.route('/teacher/<string:teacher_code>/free-slots/<int:tid>')
def teacher_free_slots_json(teacher_code, tid):
    """AJAX: Return free slots for a target teacher (used by substitute modal)."""
    db = get_db()
    teacher = db.query(PITeacher).filter(PITeacher.teacher_code == teacher_code).first()
    if not teacher:
        return jsonify([])
    target = db.query(PITeacher).get(tid)
    if not target or target.event_id != teacher.event_id:
        return jsonify([])
    slots = db.query(PISlot).filter(
        PISlot.teacher_id == tid,
        PISlot.is_booked == False,
        PISlot.is_break == False
    ).order_by(PISlot.slot_date, PISlot.start_time).all()
    return jsonify([{'id': s.id, 'date': s.slot_date, 'start': s.start_time, 'end': s.end_time} for s in slots])


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC Booking Portal
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/book/')
@interviews_bp.route('/book')
def book_welcome():
    db = get_db()
    active_events = db.query(PIEvent).filter(
        PIEvent.is_active == True, PIEvent.is_open == True
    ).order_by(PIEvent.created_at.desc()).all()
    # If exactly one active event, grab its logo for the welcome page
    logo = None
    if active_events:
        logo = active_events[0].school_logo_url or None
    return render_template('interviews/book/welcome.html',
                           active_events=active_events, logo=logo)


@interviews_bp.route('/book/enter', methods=['POST'])
def book_enter():
    from utils.i18n import get_lang
    db   = get_db()
    code = request.form.get('event_code', '').strip().upper()
    ev   = db.query(PIEvent).filter(PIEvent.event_code == code,
                                     PIEvent.is_active == True).first()
    if not ev:
        flash('رمز الفعالية غير صحيح. يرجى المحاولة مرة أخرى' if get_lang()=='ar' else 'Invalid event code. Please check and try again.', 'danger')
        return redirect(url_for('interviews.book_welcome'))
    if not ev.is_open:
        flash('الحجز لهذه الفعالية مغلق حالياً' if get_lang()=='ar' else 'Bookings for this event are currently closed.', 'warning')
        return redirect(url_for('interviews.book_welcome'))
    session['pi_event_id']   = ev.id
    session['pi_event_code'] = code
    if getattr(ev, 'use_hierarchy', False):
        return redirect(url_for('interviews.book_cascade', event_id=ev.id))
    return redirect(url_for('interviews.book_select', event_id=ev.id))


@interviews_bp.route('/book/<int:event_id>/select')
def book_select(event_id):
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    if session.get('pi_event_id') != event_id:
        return redirect(url_for('interviews.book_welcome'))
    teachers = db.query(PITeacher).filter(PITeacher.event_id == event_id,
                                           PITeacher.is_active == True).all()
    # Build available slots per teacher, grouped by date
    teacher_slots = {}
    for t in teachers:
        by_date = {}
        for s in db.query(PISlot).filter(
            PISlot.teacher_id == t.id,
            PISlot.is_break == False,
            PISlot.is_booked == False,
        ).order_by(PISlot.slot_date, PISlot.start_time).all():
            by_date.setdefault(s.slot_date, []).append(s)
        teacher_slots[t.id] = by_date
    return render_template('interviews/book/select.html',
                           ev=ev, teachers=teachers, teacher_slots=teacher_slots)


@interviews_bp.route('/book/<int:event_id>/cascade')
def book_cascade(event_id):
    """Redirect to new parent table view"""
    return redirect(url_for('interviews.book_parent_table', event_id=event_id))


@interviews_bp.route('/book/<int:event_id>/confirm', methods=['GET', 'POST'])
def book_confirm(event_id):
    from utils.i18n import get_lang
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    if session.get('pi_event_id') != event_id:
        return redirect(url_for('interviews.book_welcome'))

    if request.method == 'POST':
        # Parse selected slots
        selected_slot_ids = request.form.getlist('slot_ids')
        parent_name  = request.form.get('parent_name', '').strip()
        parent_email = request.form.get('parent_email', '').strip()
        parent_phone = request.form.get('parent_phone', '').strip()
        child_name   = request.form.get('child_name', '').strip()
        comment      = request.form.get('comment', '').strip()

        if not parent_name or not child_name or not selected_slot_ids:
            flash('يرجى ملء جميع الحقول المطلوبة واختيار فترة زمنية واحدة على الأقل' if get_lang()=='ar' else 'Please fill in all required fields and select at least one time slot.', 'danger')
            return redirect(url_for('interviews.book_select', event_id=event_id))

        sess_id = _gen_ref()
        created_bookings = []
        errors = []

        for sid in selected_slot_ids:
            slot = db.query(PISlot).get(int(sid))
            if not slot or slot.is_booked or slot.is_break:
                errors.append(f'Slot {sid} is no longer available.')
                continue
            # Create booking
            ref = _gen_ref()
            b = PIBooking(
                slot_id       = slot.id,
                event_id      = event_id,
                booking_ref   = ref,
                parent_name   = parent_name,
                parent_email  = parent_email,
                parent_phone  = parent_phone,
                child_name    = child_name,
                comment       = comment if ev.allow_comments else '',
                session_id    = sess_id,
                status        = 'confirmed',
            )
            slot.is_booked = True
            db.add(b)
            created_bookings.append(b)

        if errors:
            db.rollback()
            for e in errors:
                flash(e, 'danger')
            return redirect(url_for('interviews.book_select', event_id=event_id))

        db.commit()
        # Send confirmation emails
        if parent_email:
            for b in created_bookings:
                _send_confirmation(b, ev, b.slot.teacher, b.slot)

        # Store session ref for timetable view
        session['pi_session_id'] = sess_id
        flash('تم تأكيد حجوزاتك بنجاح!' if get_lang()=='ar' else 'Your bookings have been confirmed!', 'success')
        return redirect(url_for('interviews.book_timetable', session_id=sess_id))

    # GET — show summary before confirm
    slot_ids = request.args.getlist('slots')
    slots    = [db.query(PISlot).get(int(s)) for s in slot_ids if s]
    slots    = [s for s in slots if s and not s.is_booked]
    return render_template('interviews/book/confirm.html',
                           ev=ev, slots=slots, slot_ids=slot_ids)


@interviews_bp.route('/book/timetable/<string:session_id>')
def book_timetable(session_id):
    db       = get_db()
    bookings = db.query(PIBooking).filter(PIBooking.session_id == session_id,
                                           PIBooking.status == 'confirmed').all()
    if not bookings:
        abort(404)
    ev = bookings[0].event
    bookings.sort(key=lambda b: (b.slot.slot_date, b.slot.start_time))
    return render_template('interviews/book/timetable.html',
                           ev=ev, bookings=bookings, session_id=session_id)


@interviews_bp.route('/book/lookup', methods=['GET', 'POST'])
def book_lookup():
    """Let parent look up bookings by email"""
    db = get_db()
    bookings = []
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        ref   = request.form.get('ref', '').strip()
        q = db.query(PIBooking).filter(PIBooking.status == 'confirmed')
        if ref:
            q = q.filter(PIBooking.booking_ref == ref.upper())
        elif email:
            q = q.filter(PIBooking.parent_email.ilike(email))
        bookings = q.order_by(PIBooking.created_at.desc()).all()
        if not bookings:
            flash('No bookings found. Please check your email or reference number.', 'warning')
    return render_template('interviews/book/lookup.html', bookings=bookings)


@interviews_bp.route('/book/cancel/<string:booking_ref>', methods=['POST'])
def book_cancel(booking_ref):
    db = get_db()
    b  = db.query(PIBooking).filter(PIBooking.booking_ref == booking_ref).first() or abort(404)
    b.status       = 'cancelled'
    b.cancelled_at = datetime.now()
    if b.slot:
        b.slot.is_booked = False
    db.commit()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    flash('تم إلغاء الحجز بنجاح' if ar else 'Your booking has been cancelled.', 'success')
    return redirect(url_for('interviews.book_lookup'))


@interviews_bp.route('/book/change/<string:booking_ref>', methods=['GET', 'POST'])
def book_change(booking_ref):
    """Parent changes booking to a different available slot"""
    db = get_db()
    b = db.query(PIBooking).filter(PIBooking.booking_ref == booking_ref,
                                    PIBooking.status == 'confirmed').first() or abort(404)
    ev = b.event
    if not ev.is_open:
        from utils.i18n import get_lang
        ar = get_lang() == 'ar'
        flash('الحجز مغلق حالياً' if ar else 'Bookings are currently closed.', 'warning')
        return redirect(url_for('interviews.book_lookup'))

    from utils.i18n import get_lang
    ar = get_lang() == 'ar'

    if request.method == 'POST':
        new_slot_id = request.form.get('new_slot_id', type=int)
        if not new_slot_id:
            flash('يرجى اختيار فترة زمنية' if ar else 'Please select a time slot.', 'danger')
            return redirect(url_for('interviews.book_change', booking_ref=booking_ref))
        new_slot = db.query(PISlot).get(new_slot_id)
        if not new_slot or new_slot.is_booked or new_slot.is_break or new_slot.event_id != ev.id:
            flash('الفترة غير متاحة' if ar else 'Slot not available.', 'danger')
            return redirect(url_for('interviews.book_change', booking_ref=booking_ref))
        # Release old slot
        if b.slot:
            b.slot.is_booked = False
        # Assign new slot
        b.slot_id = new_slot.id
        new_slot.is_booked = True
        db.commit()
        # Send updated confirmation
        if b.parent_email:
            _send_confirmation(b, ev, new_slot.teacher, new_slot)
        flash('تم تغيير الموعد بنجاح' if ar else 'Booking changed successfully.', 'success')
        return redirect(url_for('interviews.book_lookup'))

    # GET — show available slots for this event
    teachers = db.query(PITeacher).filter(PITeacher.event_id == ev.id,
                                           PITeacher.is_active == True).all()
    teacher_slots = {}
    for t in teachers:
        by_date = {}
        for s in db.query(PISlot).filter(
            PISlot.teacher_id == t.id,
            PISlot.is_break == False,
            PISlot.is_booked == False,
        ).order_by(PISlot.slot_date, PISlot.start_time).all():
            by_date.setdefault(s.slot_date, []).append(s)
        if by_date:
            teacher_slots[t.id] = by_date
    return render_template('interviews/book/change.html',
                           ev=ev, booking=b, teachers=teachers, teacher_slots=teacher_slots)


# ─────────────────────────────────────────────────────────────────────────────
# STAFF — Phone Booking Portal (logged-in staff only)
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/staff/')
@login_required
def staff_index():
    db     = get_db()
    events = db.query(PIEvent).filter(PIEvent.is_active == True,
                                       PIEvent.is_open == True).all()
    return render_template('interviews/staff/index.html', events=events)


@interviews_bp.route('/staff/<int:event_id>/book', methods=['GET', 'POST'])
@login_required
def staff_book(event_id):
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    teachers = db.query(PITeacher).filter(PITeacher.event_id == event_id,
                                           PITeacher.is_active == True).all()
    teacher_slots = {}
    for t in teachers:
        by_date = {}
        for s in db.query(PISlot).filter(
            PISlot.teacher_id == t.id,
            PISlot.is_break == False,
            PISlot.is_booked == False,
        ).order_by(PISlot.slot_date, PISlot.start_time).all():
            by_date.setdefault(s.slot_date, []).append(s)
        teacher_slots[t.id] = by_date

    if request.method == 'POST':
        slot_ids     = request.form.getlist('slot_ids')
        parent_name  = request.form.get('parent_name', '').strip()
        parent_email = request.form.get('parent_email', '').strip()
        parent_phone = request.form.get('parent_phone', '').strip()
        child_name   = request.form.get('child_name', '').strip()
        comment      = request.form.get('comment', '').strip()
        sess_id      = _gen_ref()

        created = []
        for sid in slot_ids:
            slot = db.query(PISlot).get(int(sid))
            if not slot or slot.is_booked:
                continue
            b = PIBooking(
                slot_id         = slot.id,
                event_id        = event_id,
                booking_ref     = _gen_ref(),
                parent_name     = parent_name,
                parent_email    = parent_email,
                parent_phone    = parent_phone,
                child_name      = child_name,
                comment         = comment,
                session_id      = sess_id,
                booked_by_staff = True,
                status          = 'confirmed',
            )
            slot.is_booked = True
            db.add(b)
            created.append(b)
        db.commit()
        if parent_email and created:
            ev_obj = created[0].event
            for b in created:
                _send_confirmation(b, ev_obj, b.slot.teacher, b.slot)
        flash(f'{len(created)} booking(s) made for {parent_name}.', 'success')
        return redirect(url_for('interviews.book_timetable', session_id=sess_id))

    return render_template('interviews/staff/book.html',
                           ev=ev, teachers=teachers, teacher_slots=teacher_slots)


# ─────────────────────────────────────────────────────────────────────────────
# General Appointment Requests
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/book/request-by-code/<string:code>')
def book_request_by_code(code):
    """Redirect to request form using event code"""
    db = get_db()
    ev = db.query(PIEvent).filter(PIEvent.event_code == code.upper(),
                                   PIEvent.is_active == True).first()
    if not ev:
        from utils.i18n import get_lang
        ar = get_lang() == 'ar'
        flash('رمز الفعالية غير صحيح' if ar else 'Invalid event code.', 'danger')
        return redirect(url_for('interviews.book_welcome'))
    return redirect(url_for('interviews.book_request', event_id=ev.id))


@interviews_bp.route('/book/<int:event_id>/request', methods=['GET', 'POST'])
def book_request(event_id):
    """Parent submits a general appointment request"""
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    if not ev.is_open or not ev.is_active:
        flash('This event is not accepting requests.', 'warning')
        return redirect(url_for('interviews.book_welcome'))

    from utils.i18n import get_lang
    ar = get_lang() == 'ar'

    if request.method == 'POST':
        parent_name = request.form.get('parent_name', '').strip()
        parent_email = request.form.get('parent_email', '').strip()
        parent_phone = request.form.get('parent_phone', '').strip()
        child_name = request.form.get('child_name', '').strip()
        child_grade = request.form.get('child_grade', '').strip()
        reason = request.form.get('reason', '').strip()
        preferred_date = request.form.get('preferred_date', '').strip()
        preferred_time = request.form.get('preferred_time', '').strip()

        if not parent_name or not child_name or not reason:
            flash('الاسم واسم الطالب والسبب مطلوبة' if ar else 'Name, child name, and reason are required', 'danger')
            return redirect(url_for('interviews.book_request', event_id=event_id))

        req_code = 'REQ-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        ar_req = PIAppointmentRequest(
            event_id=event_id,
            request_code=req_code,
            parent_name=parent_name,
            parent_email=parent_email,
            parent_phone=parent_phone,
            child_name=child_name,
            child_grade=child_grade,
            reason=reason,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            status='pending',
        )
        db.add(ar_req)
        db.commit()
        flash(('تم إرسال طلبك بنجاح. رمز الطلب: ' if ar else 'Request submitted. Code: ') + req_code, 'success')
        return redirect(url_for('interviews.book_request_status', request_code=req_code))

    return render_template('interviews/book/request.html', ev=ev)


@interviews_bp.route('/book/request-status/<string:request_code>')
def book_request_status(request_code):
    db = get_db()
    ar_req = db.query(PIAppointmentRequest).filter(
        PIAppointmentRequest.request_code == request_code).first() or abort(404)
    ev = ar_req.event
    return render_template('interviews/book/request_status.html', req=ar_req, ev=ev)


@interviews_bp.route('/admin/events/<int:event_id>/requests')
@login_required
def admin_requests(event_id):
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ev = db.query(PIEvent).get(event_id) or abort(404)
    status_filter = request.args.get('status', '')
    q = db.query(PIAppointmentRequest).filter(PIAppointmentRequest.event_id == event_id)
    if status_filter:
        q = q.filter(PIAppointmentRequest.status == status_filter)
    requests_list = q.order_by(PIAppointmentRequest.created_at.desc()).all()
    return render_template('interviews/admin/requests.html', ev=ev, requests=requests_list, sel_status=status_filter)


@interviews_bp.route('/admin/requests/<int:rid>/action', methods=['POST'])
@login_required
def admin_request_action(rid):
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    ar_req = db.query(PIAppointmentRequest).get(rid) or abort(404)
    action = request.form.get('action', '')
    admin_notes = request.form.get('admin_notes', '').strip()

    if action == 'approve':
        assigned_date = request.form.get('assigned_date', '').strip()
        assigned_time = request.form.get('assigned_time', '').strip()
        ar_req.status = 'approved'
        ar_req.assigned_date = assigned_date
        ar_req.assigned_time = assigned_time
        ar_req.admin_notes = admin_notes
        ar_req.approved_by = current_user.id
        ar_req.approved_at = datetime.now()
    elif action == 'reject':
        ar_req.status = 'rejected'
        ar_req.admin_notes = admin_notes
        ar_req.approved_by = current_user.id
        ar_req.approved_at = datetime.now()
    elif action == 'amend':
        ar_req.status = 'amended'
        ar_req.assigned_date = request.form.get('assigned_date', '').strip()
        ar_req.assigned_time = request.form.get('assigned_time', '').strip()
        ar_req.admin_notes = admin_notes
        ar_req.approved_by = current_user.id
        ar_req.approved_at = datetime.now()

    db.commit()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    flash(('تم تحديث حالة الطلب' if ar else 'Request status updated'), 'success')
    return redirect(url_for('interviews.admin_requests', event_id=ar_req.event_id))


# ─────────────────────────────────────────────────────────────────────────────
# GENERAL APPOINTMENT CALENDAR — Public (free-form booking)
# ─────────────────────────────────────────────────────────────────────────────

def _time_to_minutes(t):
    """Convert HH:MM string to minutes since midnight"""
    h, m = map(int, t.split(':'))
    return h * 60 + m

def _check_blocked(db, booking_date, start_time, end_time):
    """Check if requested time overlaps any blocked period. Returns True if blocked."""
    blocked = db.query(PICalendarSlot).filter(
        PICalendarSlot.slot_date == booking_date,
        PICalendarSlot.status == 'blocked'
    ).all()
    req_start = _time_to_minutes(start_time)
    req_end = _time_to_minutes(end_time)
    for bp in blocked:
        bp_start = _time_to_minutes(bp.start_time)
        bp_end = _time_to_minutes(bp.end_time)
        # overlap check
        if req_start < bp_end and req_end > bp_start:
            return True
    return False


@interviews_bp.route('/calendar', methods=['GET', 'POST'])
def calendar_public():
    """Public calendar — pick any date/time within work hours to request an appointment"""
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    db = get_db()

    if request.method == 'POST':
        booking_date = request.form.get('booking_date', '').strip()
        start_time = request.form.get('start_time', '').strip()
        end_time = request.form.get('end_time', '').strip()
        requester_name = request.form.get('requester_name', '').strip()
        requester_email = request.form.get('requester_email', '').strip()
        requester_phone = request.form.get('requester_phone', '').strip()
        person_to_meet = request.form.get('person_to_meet', '').strip()
        reason = request.form.get('reason', '').strip()

        # Validate required fields
        if not requester_name or not person_to_meet or not reason or not booking_date or not start_time or not end_time:
            flash('جميع الحقول المطلوبة يجب تعبئتها' if ar else 'All required fields must be filled.', 'danger')
            return redirect(url_for('interviews.calendar_public'))

        # Validate date range (today to today+60)
        from datetime import date as date_cls
        try:
            bdate = date_cls.fromisoformat(booking_date)
        except ValueError:
            flash('تنسيق التاريخ غير صحيح' if ar else 'Invalid date format.', 'danger')
            return redirect(url_for('interviews.calendar_public'))

        today = date_cls.today()
        if bdate < today or bdate > today + timedelta(days=60):
            flash('التاريخ يجب أن يكون بين اليوم و 60 يوم قادمة' if ar else 'Date must be between today and 60 days from now.', 'danger')
            return redirect(url_for('interviews.calendar_public'))

        # Validate time within work hours (08:00 - 15:30)
        st_min = _time_to_minutes(start_time)
        et_min = _time_to_minutes(end_time)
        if st_min < 480 or et_min > 930:  # 8:00=480, 15:30=930
            flash('الوقت يجب أن يكون ضمن ساعات العمل (8:00 ص - 3:30 م)' if ar else 'Time must be within work hours (8:00 AM - 3:30 PM).', 'danger')
            return redirect(url_for('interviews.calendar_public'))

        if st_min >= et_min:
            flash('وقت البدء يجب أن يكون قبل وقت الانتهاء' if ar else 'Start time must be before end time.', 'danger')
            return redirect(url_for('interviews.calendar_public'))

        # Check against blocked periods
        if _check_blocked(db, booking_date, start_time, end_time):
            flash('الوقت المختار يتعارض مع فترة محظورة. يرجى اختيار وقت آخر.' if ar else 'Selected time conflicts with a blocked period. Please choose another time.', 'danger')
            return redirect(url_for('interviews.calendar_public'))

        # Create booking
        req_code = 'APT-' + ''.join(random.choices(string.ascii_uppercase, k=8))
        booking = PICalendarBooking(
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            request_code=req_code,
            requester_name=requester_name,
            requester_email=requester_email,
            requester_phone=requester_phone,
            person_to_meet=person_to_meet,
            reason=reason,
            status='pending',
        )
        db.add(booking)
        db.commit()

        # Send confirmation email
        if requester_email:
            try:
                from utils.email_helper import send_email
                d = 'rtl' if ar else 'ltr'
                subject = 'تأكيد طلب الموعد' if ar else 'Appointment Request Confirmation'
                greeting = f'عزيزي {requester_name}،' if ar else f'Dear {requester_name},'
                msg = 'تم استلام طلبك وسيتم مراجعته.' if ar else 'Your request has been received and will be reviewed.'
                lbl_code = 'رقم الطلب' if ar else 'Request Code'
                lbl_date = 'التاريخ' if ar else 'Date'
                lbl_time = 'الوقت' if ar else 'Time'
                lbl_person = 'الشخص المطلوب مقابلته' if ar else 'Person to Meet'
                lbl_reason = 'السبب' if ar else 'Reason'
                lbl_auto = 'هذه رسالة آلية.' if ar else 'This is an automated message.'
                body = f"""
<div style="font-family:sans-serif;max-width:600px;margin:auto;direction:{d}">
<div style="background:#2563eb;color:white;padding:20px;border-radius:8px 8px 0 0">
  <h2 style="margin:0">{'طلب موعد عام' if ar else 'General Appointment Request'}</h2>
</div>
<div style="padding:24px;border:1px solid #dee2e6;border-top:none;border-radius:0 0 8px 8px">
  <p>{greeting}</p>
  <p>{msg}</p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0">
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_code}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{req_code}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_date}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{booking_date}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_time}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{start_time} – {end_time}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_person}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{person_to_meet}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_reason}</td>
        <td style="padding:8px">{reason}</td></tr>
  </table>
  <p style="color:#6c757d;font-size:0.9em">{lbl_auto}</p>
</div>
</div>"""
                text_body = f"{greeting} {msg} {lbl_code}: {req_code}"
                send_email(to_email=requester_email, to_name=requester_name,
                           subject=subject, html_body=body, text_body=text_body)
            except Exception as e:
                current_app.logger.warning(f"Calendar booking email error: {e}")

        flash(('تم إرسال طلبك. رقم الطلب: ' if ar else 'Request submitted. Code: ') + req_code, 'success')
        return redirect(url_for('interviews.calendar_request_status', request_code=req_code))

    # GET — show booking form
    from datetime import date as date_cls
    today = date_cls.today().isoformat()
    max_date = (date_cls.today() + timedelta(days=60)).isoformat()

    # Build start time options: 8:00 AM to 3:00 PM, 15-min intervals
    start_times = []
    for m in range(480, 901, 15):  # 8:00 to 15:00
        hh = m // 60
        mm = m % 60
        val = f'{hh:02d}:{mm:02d}'
        ampm = 'AM' if hh < 12 else 'PM'
        disp_h = hh if hh <= 12 else hh - 12
        if disp_h == 0: disp_h = 12
        label = f'{disp_h}:{mm:02d} {ampm}'
        start_times.append({'val': val, 'label': label})

    # Build end time options: 8:15 AM to 3:30 PM, 15-min intervals
    end_times = []
    for m in range(495, 931, 15):  # 8:15 to 15:30
        hh = m // 60
        mm = m % 60
        val = f'{hh:02d}:{mm:02d}'
        ampm = 'AM' if hh < 12 else 'PM'
        disp_h = hh if hh <= 12 else hh - 12
        if disp_h == 0: disp_h = 12
        label = f'{disp_h}:{mm:02d} {ampm}'
        end_times.append({'val': val, 'label': label})

    return render_template('interviews/book/calendar.html',
                           today=today, max_date=max_date,
                           start_times=start_times, end_times=end_times)


@interviews_bp.route('/calendar/status/<string:request_code>')
def calendar_request_status(request_code):
    """Public status page for calendar booking"""
    db = get_db()
    booking = db.query(PICalendarBooking).filter(
        PICalendarBooking.request_code == request_code).first() or abort(404)
    return render_template('interviews/book/calendar_status.html', booking=booking)


# ─────────────────────────────────────────────────────────────────────────────
# GENERAL APPOINTMENT CALENDAR — Admin
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/admin/calendar/')
@login_required
def admin_calendar():
    """Admin calendar — manage blocked periods and view booking stats"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'view'):
        abort(403)
    db = get_db()
    # Get all blocked periods (slots)
    slots = db.query(PICalendarSlot).order_by(
        PICalendarSlot.slot_date, PICalendarSlot.start_time).all()

    # Group by date
    by_date = {}
    for s in slots:
        by_date.setdefault(s.slot_date, []).append(s)
    dates = sorted(by_date.keys())

    # Booking counts
    total_bookings = db.query(PICalendarBooking).count()
    pending_count = db.query(PICalendarBooking).filter(PICalendarBooking.status == 'pending').count()
    approved_count = db.query(PICalendarBooking).filter(PICalendarBooking.status == 'approved').count()
    rejected_count = db.query(PICalendarBooking).filter(PICalendarBooking.status == 'rejected').count()
    total_blocked = len(slots)

    return render_template('interviews/admin/calendar.html',
                           by_date=by_date, dates=dates,
                           total_bookings=total_bookings, pending_count=pending_count,
                           approved_count=approved_count, rejected_count=rejected_count,
                           total_blocked=total_blocked)


@interviews_bp.route('/admin/calendar/add-slot', methods=['POST'])
@login_required
def admin_calendar_add_slot():
    """Add a blocked period / break to calendar"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'add'):
        abort(403)
    db = get_db()
    slot_date = request.form.get('slot_date', '').strip()
    start_time = request.form.get('start_time', '').strip()
    end_time = request.form.get('end_time', '').strip()
    status = request.form.get('status', 'blocked').strip()
    note = request.form.get('note', '').strip()

    if not all([slot_date, start_time, end_time]):
        flash('التاريخ ووقت البدء والانتهاء مطلوبة' if session.get('lang','ar') == 'ar' else 'Date, start time, and end time are required.', 'danger')
        return redirect(url_for('interviews.admin_calendar'))

    slot = PICalendarSlot(
        slot_date=slot_date,
        start_time=start_time,
        end_time=end_time,
        status=status if status in ('blocked', 'break') else 'blocked',
        note=note,
        created_by=current_user.id,
    )
    db.add(slot)
    db.commit()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    flash('تمت إضافة الفترة المحظورة' if ar else 'Blocked period added.', 'success')
    return redirect(url_for('interviews.admin_calendar'))


@interviews_bp.route('/admin/calendar/edit-slot/<int:slot_id>', methods=['POST'])
@login_required
def admin_calendar_edit_slot(slot_id):
    """Edit a calendar blocked period"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'edit'):
        abort(403)
    db = get_db()
    slot = db.query(PICalendarSlot).get(slot_id) or abort(404)
    slot.slot_date = request.form.get('slot_date', slot.slot_date).strip()
    slot.start_time = request.form.get('start_time', slot.start_time).strip()
    slot.end_time = request.form.get('end_time', slot.end_time).strip()
    slot.status = request.form.get('status', slot.status).strip()
    slot.note = request.form.get('note', '').strip()
    db.commit()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    flash('تم تحديث الفترة' if ar else 'Period updated.', 'success')
    return redirect(url_for('interviews.admin_calendar'))


@interviews_bp.route('/admin/calendar/delete-slot/<int:slot_id>', methods=['POST'])
@login_required
def admin_calendar_delete_slot(slot_id):
    """Delete a calendar blocked period"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'delete'):
        abort(403)
    db = get_db()
    slot = db.query(PICalendarSlot).get(slot_id) or abort(404)
    db.delete(slot)
    db.commit()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    flash('تم حذف الفترة' if ar else 'Period deleted.', 'success')
    return redirect(url_for('interviews.admin_calendar'))


@interviews_bp.route('/admin/calendar/block-period', methods=['POST'])
@login_required
def admin_calendar_block_period():
    """Block a date range or time range"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'edit'):
        abort(403)
    db = get_db()
    from_date = request.form.get('from_date', '').strip()
    to_date = request.form.get('to_date', '').strip() or from_date
    start_time = request.form.get('start_time', '08:00').strip()
    end_time = request.form.get('end_time', '15:30').strip()
    note = request.form.get('note', '').strip()

    if not from_date:
        flash('التاريخ مطلوب' if session.get('lang','ar') == 'ar' else 'Date is required.', 'danger')
        return redirect(url_for('interviews.admin_calendar'))

    from datetime import date as date_cls
    try:
        d_from = date_cls.fromisoformat(from_date)
        d_to = date_cls.fromisoformat(to_date)
    except ValueError:
        flash('تنسيق التاريخ غير صحيح' if session.get('lang','ar') == 'ar' else 'Invalid date format.', 'danger')
        return redirect(url_for('interviews.admin_calendar'))

    count = 0
    current = d_from
    while current <= d_to:
        date_str = current.isoformat()
        slot = PICalendarSlot(
            slot_date=date_str,
            start_time=start_time,
            end_time=end_time,
            status='blocked',
            note=note,
            created_by=current_user.id,
        )
        db.add(slot)
        count += 1
        current += timedelta(days=1)

    db.commit()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    flash((f'تم حظر {count} فترة' if ar else f'{count} period(s) blocked.'), 'success')
    return redirect(url_for('interviews.admin_calendar'))


@interviews_bp.route('/admin/calendar/import', methods=['POST'])
@login_required
def admin_calendar_import():
    """Import blocked periods from CSV"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'add'):
        abort(403)
    db = get_db()
    f = request.files.get('csv_file')
    if not f:
        flash('يرجى رفع ملف CSV' if session.get('lang','ar') == 'ar' else 'Please upload a CSV file.', 'danger')
        return redirect(url_for('interviews.admin_calendar'))

    stream = io.StringIO(f.stream.read().decode('utf-8-sig'))
    reader = csv.DictReader(stream)
    count = 0
    errors = []
    for i, row in enumerate(reader, 2):
        slot_date = (row.get('date') or row.get('Date') or row.get('التاريخ') or '').strip()
        start = (row.get('start_time') or row.get('Start Time') or row.get('من') or '').strip()
        end = (row.get('end_time') or row.get('End Time') or row.get('إلى') or '').strip()
        status = (row.get('status') or row.get('Status') or row.get('الحالة') or 'blocked').strip().lower()
        note = (row.get('note') or row.get('Note') or row.get('ملاحظة') or '').strip()

        if not all([slot_date, start, end]):
            errors.append(f'Row {i}: missing fields')
            continue

        if status in ('blocked', 'break', 'unavailable', 'محظور'):
            status = 'blocked'
        else:
            status = 'blocked'

        slot = PICalendarSlot(
            slot_date=slot_date,
            start_time=start,
            end_time=end,
            status=status,
            note=note,
            created_by=current_user.id,
        )
        db.add(slot)
        count += 1

    db.commit()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    if count:
        flash((f'تم استيراد {count} فترة محظورة' if ar else f'{count} blocked periods imported.'), 'success')
    if errors:
        flash((f'{len(errors)} أخطاء' if ar else f'{len(errors)} errors: ') + '; '.join(errors[:3]), 'warning')
    return redirect(url_for('interviews.admin_calendar'))


@interviews_bp.route('/admin/calendar/template')
@login_required
def admin_calendar_template():
    """Download CSV template for blocked periods"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'view'):
        abort(403)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['date', 'start_time', 'end_time', 'status', 'note'])
    from datetime import date as date_cls
    today = date_cls.today()
    for i in range(5):  # Mon-Fri
        d = today + timedelta(days=(7 - today.weekday() + i))
        d_str = d.isoformat()
        w.writerow([d_str, '12:00', '13:00', 'blocked', 'Lunch break'])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=blocked_periods_template.csv'})


@interviews_bp.route('/admin/calendar/bookings')
@login_required
def admin_calendar_bookings():
    """Admin view of all calendar appointment requests"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'view'):
        abort(403)
    db = get_db()
    status_filter = request.args.get('status', '')
    q = db.query(PICalendarBooking)
    if status_filter:
        q = q.filter(PICalendarBooking.status == status_filter)
    bookings = q.order_by(PICalendarBooking.created_at.desc()).all()
    return render_template('interviews/admin/calendar_bookings.html', bookings=bookings, sel_status=status_filter)


@interviews_bp.route('/admin/calendar/bookings/<int:bid>/action', methods=['POST'])
@login_required
def admin_calendar_booking_action(bid):
    """Approve or reject a calendar booking"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'approve'):
        abort(403)
    db = get_db()
    booking = db.query(PICalendarBooking).get(bid) or abort(404)
    action = request.form.get('action', '')
    admin_notes = request.form.get('admin_notes', '').strip()

    if action == 'approve':
        booking.status = 'approved'
        booking.admin_notes = admin_notes
        booking.approved_by = current_user.id
        booking.approved_at = datetime.now()
    elif action == 'reject':
        booking.status = 'rejected'
        booking.admin_notes = admin_notes
        booking.approved_by = current_user.id
        booking.approved_at = datetime.now()

    db.commit()

    # Send status update email
    if booking.requester_email:
        try:
            from utils.email_helper import send_email
            from utils.i18n import get_lang
            ar = get_lang() == 'ar'
            d = 'rtl' if ar else 'ltr'
            b_date = booking.booking_date or (booking.slot.slot_date if booking.slot else '-')
            b_start = booking.start_time or (booking.slot.start_time if booking.slot else '')
            b_end = booking.end_time or (booking.slot.end_time if booking.slot else '')
            if action == 'approve':
                subject = 'تمت الموافقة على طلب الموعد' if ar else 'Appointment Request Approved'
                msg = 'تمت الموافقة على طلبك.' if ar else 'Your appointment request has been approved.'
                color = '#16a34a'
            else:
                subject = 'تم رفض طلب الموعد' if ar else 'Appointment Request Rejected'
                msg = 'نأسف، تم رفض طلبك.' if ar else 'Sorry, your appointment request has been declined.'
                color = '#dc2626'

            lbl_code = 'رقم الطلب' if ar else 'Request Code'
            lbl_date = 'التاريخ' if ar else 'Date'
            lbl_time = 'الوقت' if ar else 'Time'
            lbl_notes = 'ملاحظات' if ar else 'Notes'
            body = f"""
<div style="font-family:sans-serif;max-width:600px;margin:auto;direction:{d}">
<div style="background:{color};color:white;padding:20px;border-radius:8px 8px 0 0">
  <h2 style="margin:0">{subject}</h2>
</div>
<div style="padding:24px;border:1px solid #dee2e6;border-top:none;border-radius:0 0 8px 8px">
  <p>{'عزيزي' if ar else 'Dear'} {booking.requester_name},</p>
  <p>{msg}</p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0">
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_code}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{booking.request_code}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_date}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{b_date}</td></tr>
    <tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_time}</td>
        <td style="padding:8px;border-bottom:1px solid #dee2e6">{b_start} – {b_end}</td></tr>
    {f'<tr><td style="padding:8px;background:#f8f9fa;font-weight:bold">{lbl_notes}</td><td style="padding:8px">{admin_notes}</td></tr>' if admin_notes else ''}
  </table>
</div>
</div>"""
            text_body = f"{msg} {lbl_code}: {booking.request_code}"
            send_email(to_email=booking.requester_email, to_name=booking.requester_name,
                       subject=subject, html_body=body, text_body=text_body)
        except Exception as e:
            current_app.logger.warning(f"Calendar booking action email error: {e}")

    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    flash('تم تحديث حالة الطلب' if ar else 'Request status updated.', 'success')
    return redirect(url_for('interviews.admin_calendar_bookings'))


@interviews_bp.route('/admin/calendar/export')
@login_required
def admin_calendar_export():
    """Export blocked periods as CSV"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'view'):
        abort(403)
    db = get_db()
    slots = db.query(PICalendarSlot).order_by(PICalendarSlot.slot_date, PICalendarSlot.start_time).all()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    out = io.StringIO()
    w = csv.writer(out)
    if ar:
        w.writerow(['التاريخ', 'من', 'إلى', 'الحالة', 'ملاحظة'])
    else:
        w.writerow(['Date', 'Start Time', 'End Time', 'Status', 'Note'])
    for s in slots:
        w.writerow([s.slot_date, s.start_time, s.end_time, s.status, s.note or ''])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=blocked_periods.csv'})


@interviews_bp.route('/admin/calendar/bookings/export')
@login_required
def admin_calendar_bookings_export():
    """Export calendar bookings as CSV"""
    perm = get_permissions()
    if not perm.is_admin_or_manager() and not perm.can('pi_calendar', 'view'):
        abort(403)
    db = get_db()
    bookings = db.query(PICalendarBooking).order_by(PICalendarBooking.created_at.desc()).all()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'
    out = io.StringIO()
    w = csv.writer(out)
    if ar:
        w.writerow(['رقم الطلب', 'الاسم', 'البريد', 'الهاتف', 'الشخص المطلوب', 'السبب', 'التاريخ', 'الوقت', 'الحالة', 'ملاحظات المدير', 'تاريخ الطلب'])
    else:
        w.writerow(['Code', 'Name', 'Email', 'Phone', 'Person to Meet', 'Reason', 'Date', 'Time', 'Status', 'Admin Notes', 'Requested At'])
    for b in bookings:
        b_date = b.booking_date or (b.slot.slot_date if b.slot else '')
        b_time = f"{b.start_time or ''}-{b.end_time or ''}" if b.start_time else (f"{b.slot.start_time}-{b.slot.end_time}" if b.slot else '')
        w.writerow([
            b.request_code, b.requester_name, b.requester_email or '', b.requester_phone or '',
            b.person_to_meet, b.reason,
            b_date, b_time,
            b.status, b.admin_notes or '',
            b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else ''
        ])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=calendar_bookings.csv'})


# ─────────────────────────────────────────────────────────────────────────────
# REPORTS — Parent Interview Statistics
# ─────────────────────────────────────────────────────────────────────────────

@interviews_bp.route('/admin/reports/')
@login_required
def admin_reports():
    """Parent interview reports and statistics"""
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'

    events = db.query(PIEvent).order_by(PIEvent.created_at.desc()).all()

    # Overall stats
    total_events = len(events)
    active_events = sum(1 for e in events if e.is_active)
    total_bookings = db.query(PIBooking).count()
    confirmed_bookings = db.query(PIBooking).filter(PIBooking.status == 'confirmed').count()
    cancelled_bookings = db.query(PIBooking).filter(PIBooking.status == 'cancelled').count()
    total_teachers = db.query(PITeacher).filter(PITeacher.is_active == True).count()
    total_slots = db.query(PISlot).filter(PISlot.is_break == False).count()
    booked_slots = db.query(PISlot).filter(PISlot.is_booked == True).count()
    total_requests = db.query(PIAppointmentRequest).count()
    pending_requests = db.query(PIAppointmentRequest).filter(PIAppointmentRequest.status == 'pending').count()

    # Calendar stats
    cal_slots = db.query(PICalendarSlot).filter(PICalendarSlot.status == 'available').count()
    cal_bookings = db.query(PICalendarBooking).count()
    cal_pending = db.query(PICalendarBooking).filter(PICalendarBooking.status == 'pending').count()

    # Per-event stats
    event_stats = []
    for ev in events:
        ev_teachers = db.query(PITeacher).filter(PITeacher.event_id == ev.id, PITeacher.is_active == True).count()
        ev_total = db.query(PISlot).filter(PISlot.event_id == ev.id, PISlot.is_break == False).count()
        ev_booked = db.query(PISlot).filter(PISlot.event_id == ev.id, PISlot.is_booked == True).count()
        ev_confirmed = db.query(PIBooking).filter(PIBooking.event_id == ev.id, PIBooking.status == 'confirmed').count()
        ev_cancelled = db.query(PIBooking).filter(PIBooking.event_id == ev.id, PIBooking.status == 'cancelled').count()
        ev_requests = db.query(PIAppointmentRequest).filter(PIAppointmentRequest.event_id == ev.id).count()

        # Per-teacher stats for this event
        teacher_stats = []
        teachers = db.query(PITeacher).filter(PITeacher.event_id == ev.id).all()
        for t in teachers:
            t_total = db.query(PISlot).filter(PISlot.teacher_id == t.id, PISlot.is_break == False).count()
            t_booked = db.query(PISlot).filter(PISlot.teacher_id == t.id, PISlot.is_booked == True).count()
            teacher_stats.append({
                'name': t.name,
                'subjects': t.subjects,
                'total': t_total,
                'booked': t_booked,
                'pct': round(t_booked / t_total * 100) if t_total > 0 else 0,
            })
        teacher_stats.sort(key=lambda x: x['pct'], reverse=True)

        utilization = round(ev_booked / ev_total * 100) if ev_total > 0 else 0
        event_stats.append({
            'event': ev,
            'teachers': ev_teachers,
            'total_slots': ev_total,
            'booked': ev_booked,
            'confirmed': ev_confirmed,
            'cancelled': ev_cancelled,
            'requests': ev_requests,
            'utilization': utilization,
            'teacher_stats': teacher_stats,
        })

    return render_template('interviews/admin/reports.html',
        total_events=total_events, active_events=active_events,
        total_bookings=total_bookings, confirmed_bookings=confirmed_bookings,
        cancelled_bookings=cancelled_bookings, total_teachers=total_teachers,
        total_slots=total_slots, booked_slots=booked_slots,
        total_requests=total_requests, pending_requests=pending_requests,
        cal_slots=cal_slots, cal_bookings=cal_bookings, cal_pending=cal_pending,
        event_stats=event_stats,
        overall_utilization=round(booked_slots / total_slots * 100) if total_slots > 0 else 0)


@interviews_bp.route('/admin/reports/export')
@login_required
def admin_reports_export():
    """Export report as CSV"""
    perm = get_permissions()
    if not perm.is_admin_or_manager():
        abort(403)
    db = get_db()
    from utils.i18n import get_lang
    ar = get_lang() == 'ar'

    events = db.query(PIEvent).order_by(PIEvent.created_at.desc()).all()
    out = io.StringIO()
    w = csv.writer(out)

    if ar:
        w.writerow(['الفعالية', 'الرمز', 'المعلمين', 'إجمالي الفترات', 'المحجوز', 'نسبة الإشغال', 'مؤكد', 'ملغى', 'الطلبات'])
    else:
        w.writerow(['Event', 'Code', 'Teachers', 'Total Slots', 'Booked', 'Utilization', 'Confirmed', 'Cancelled', 'Requests'])

    for ev in events:
        ev_teachers = db.query(PITeacher).filter(PITeacher.event_id == ev.id, PITeacher.is_active == True).count()
        ev_total = db.query(PISlot).filter(PISlot.event_id == ev.id, PISlot.is_break == False).count()
        ev_booked = db.query(PISlot).filter(PISlot.event_id == ev.id, PISlot.is_booked == True).count()
        ev_confirmed = db.query(PIBooking).filter(PIBooking.event_id == ev.id, PIBooking.status == 'confirmed').count()
        ev_cancelled = db.query(PIBooking).filter(PIBooking.event_id == ev.id, PIBooking.status == 'cancelled').count()
        ev_requests = db.query(PIAppointmentRequest).filter(PIAppointmentRequest.event_id == ev.id).count()
        utilization = f"{round(ev_booked / ev_total * 100)}%" if ev_total > 0 else '0%'
        w.writerow([ev.name, ev.event_code, ev_teachers, ev_total, ev_booked, utilization, ev_confirmed, ev_cancelled, ev_requests])

    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=pi_report.csv'})
