"""
routes/checkin.py — Event Check-in
Time-windowed, code-based attendance check-in for meetings/events.
Each invited attendee gets a one-time code by email. The code is only
accepted during a configured window; a short grace period after the window
still accepts the code but requires a reason for lateness. Anyone who never
checks in is reported as absent.
"""
import random
import string
from datetime import datetime, timedelta, timezone

from flask import (Blueprint, render_template, redirect, url_for, request,
                    flash, jsonify, abort, session)

from utils.helpers import get_db, admin_required
from utils.i18n import t, get_lang
from models.database import EventCheckin, EventAttendee, SASConfig

checkin_bp = Blueprint('checkin', __name__, url_prefix='/checkin')


def _get_school_config():
    """Reuse the same school config (name/logo) already set up for SAS."""
    db = get_db()
    return db.query(SASConfig).first()


def _now_amman():
    """Current wall-clock time in Jordan (Asia/Amman, UTC+3, no DST) as a
    naive datetime — regardless of what timezone the server's OS clock is
    actually set to. Falls back to a fixed UTC+3 offset if the IANA
    timezone database isn't available on the server (some minimal
    deployment images omit it). Naive on purpose: matches the naive
    DateTime columns already used throughout this module."""
    try:
        from zoneinfo import ZoneInfo
        aware = datetime.now(ZoneInfo('Asia/Amman'))
    except Exception:
        aware = datetime.now(timezone.utc) + timedelta(hours=3)
    return aware.replace(tzinfo=None)


def _t(ar_text, en_text):
    return ar_text if get_lang() == 'ar' else en_text


def _gen_code(length=6):
    # Avoid ambiguous characters (0/O, 1/I) for something people type by hand
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(random.choices(alphabet, k=length))


def _hhmm_to_minutes(hhmm):
    h, m = map(int, hhmm.split(':'))
    return h * 60 + m


def _resolve_status(event, attendee, now=None):
    """Compute the *effective* status for display: a still-'pending'
    attendee becomes 'absent' once the event's date has passed or the
    grace window has closed, without needing a background job."""
    if attendee.status in ('on_time', 'late'):
        return attendee.status
    now = now or _now_amman()
    today_str = now.strftime('%Y-%m-%d')
    grace_end_min = _hhmm_to_minutes(event.window_end) + (event.grace_minutes or 0)
    now_min = now.hour * 60 + now.minute
    if today_str > event.event_date:
        return 'absent'
    if today_str == event.event_date and now_min > grace_end_min:
        return 'absent'
    return 'pending'


# ===========================================================================
# ADMIN
# ===========================================================================

@checkin_bp.route('/admin')
@admin_required
def admin_list():
    db = get_db()
    events = db.query(EventCheckin).order_by(EventCheckin.event_date.desc()).all()
    return render_template('checkin/admin/list.html', events=events)


def _normalize_date(date_str):
    """Coerce a date string to canonical YYYY-MM-DD regardless of what
    format the browser's date picker actually submitted (some older/mobile
    browsers fall back to free-text entry in local format). Returns None
    if the string can't be confidently parsed."""
    date_str = (date_str or '').strip()
    if not date_str:
        return None
    # Already ISO
    if len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
        except ValueError:
            pass
    # Common alternates: DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY
    for fmt in ('%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


@checkin_bp.route('/admin/new', methods=['GET', 'POST'])
@admin_required
def admin_new():
    if request.method == 'GET':
        return render_template('checkin/admin/form.html', event=None)

    db = get_db()
    name = request.form.get('name', '').strip()
    event_date = _normalize_date(request.form.get('event_date', ''))
    window_start = request.form.get('window_start', '').strip()
    window_end = request.form.get('window_end', '').strip()
    grace_minutes = request.form.get('grace_minutes', type=int) or 5
    early_minutes = request.form.get('early_minutes', type=int)
    if early_minutes is None:
        early_minutes = 15

    if not (name and event_date and window_start and window_end):
        flash(_t('يرجى تعبئة جميع الحقول بشكل صحيح (تأكد من صيغة التاريخ)',
                  'Please fill in all fields correctly (check the date format)'), 'danger')
        return redirect(url_for('checkin.admin_new'))

    event = EventCheckin(
        name=name, event_date=event_date,
        window_start=window_start, window_end=window_end,
        grace_minutes=grace_minutes, early_minutes=early_minutes,
    )
    db.add(event)
    db.commit()
    flash(_t('تم إنشاء الفعالية', 'Event created'), 'success')
    return redirect(url_for('checkin.admin_detail', event_id=event.id))


@checkin_bp.route('/admin/<int:event_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit(event_id):
    db = get_db()
    event = db.get(EventCheckin, event_id)
    if not event:
        abort(404)

    if request.method == 'GET':
        return render_template('checkin/admin/form.html', event=event)

    name = request.form.get('name', '').strip()
    event_date = _normalize_date(request.form.get('event_date', ''))
    window_start = request.form.get('window_start', '').strip()
    window_end = request.form.get('window_end', '').strip()
    grace_minutes = request.form.get('grace_minutes', type=int) or 5
    early_minutes = request.form.get('early_minutes', type=int)
    if early_minutes is None:
        early_minutes = 15

    if not (name and event_date and window_start and window_end):
        flash(_t('يرجى تعبئة جميع الحقول بشكل صحيح (تأكد من صيغة التاريخ)',
                  'Please fill in all fields correctly (check the date format)'), 'danger')
        return redirect(url_for('checkin.admin_edit', event_id=event.id))

    event.name = name
    event.event_date = event_date
    event.window_start = window_start
    event.window_end = window_end
    event.grace_minutes = grace_minutes
    event.early_minutes = early_minutes
    db.commit()
    flash(_t('تم حفظ التعديلات', 'Changes saved'), 'success')
    return redirect(url_for('checkin.admin_detail', event_id=event.id))


@checkin_bp.route('/admin/<int:event_id>')
@admin_required
def admin_detail(event_id):
    db = get_db()
    event = db.get(EventCheckin, event_id)
    if not event:
        abort(404)
    attendees = sorted(event.attendees, key=lambda a: a.name)
    now = _now_amman()
    counts = {'on_time': 0, 'late': 0, 'absent': 0, 'pending': 0}
    for a in attendees:
        counts[_resolve_status(event, a, now)] += 1
    return render_template(
        'checkin/admin/detail.html', event=event, attendees=attendees,
        counts=counts, resolve_status=lambda a: _resolve_status(event, a, now),
        checkin_url=url_for('checkin.public_checkin', event_id=event.id, _external=True),
    )


def _parse_attendee_rows_from_file(file_storage):
    """Parse an uploaded .xlsx/.xls/.csv file into [(name, email), ...].
    Skips a header row automatically (a row is treated as data only if its
    second column looks like an email address)."""
    filename = (file_storage.filename or '').lower()
    rows = []
    if filename.endswith('.csv'):
        import csv as csv_mod
        text_stream = file_storage.stream.read().decode('utf-8-sig', errors='ignore')
        for parts in csv_mod.reader(text_stream.splitlines()):
            if parts:
                rows.append(parts)
    elif filename.endswith('.xlsx') or filename.endswith('.xls'):
        import openpyxl
        wb = openpyxl.load_workbook(file_storage, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        for row in ws.iter_rows(values_only=True):
            rows.append(['' if c is None else str(c) for c in row])
    else:
        return []

    pairs = []
    for r in rows:
        name = (r[0] if len(r) > 0 else '').strip()
        email = (r[1] if len(r) > 1 else '').strip()
        if not name:
            continue
        if email and '@' not in email:
            # Looks like a header row (e.g. "Name, Email") — skip it
            continue
        pairs.append((name, email))
    return pairs


@checkin_bp.route('/admin/<int:event_id>/attendees/add', methods=['POST'])
@admin_required
def admin_attendees_add(event_id):
    db = get_db()
    event = db.get(EventCheckin, event_id)
    if not event:
        abort(404)

    existing_codes = {a.code for a in event.attendees}
    pairs = []

    uploaded = request.files.get('file')
    if uploaded and uploaded.filename:
        try:
            pairs = _parse_attendee_rows_from_file(uploaded)
        except Exception as e:
            flash(_t(f'تعذرت قراءة الملف: {e}', f'Could not read the file: {e}'), 'danger')
            return redirect(url_for('checkin.admin_detail', event_id=event.id))
    else:
        raw = request.form.get('bulk_text', '')
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Accept "Name,Email" or "Name<TAB>Email" or just "Name".
            # Also normalize the Arabic comma "،" and Arabic semicolon "؛"
            # (easy to type by mistake on an Arabic keyboard) to a plain comma.
            normalized = line.replace('\t', ',').replace('،', ',').replace('؛', ',')
            parts = [p.strip() for p in normalized.split(',')]
            name = parts[0] if parts else ''
            email = parts[1] if len(parts) > 1 else ''
            if name:
                pairs.append((name, email))

    added = 0
    for name, email in pairs:
        code = _gen_code()
        while code in existing_codes:
            code = _gen_code()
        existing_codes.add(code)
        db.add(EventAttendee(event_id=event.id, name=name, email=email, code=code))
        added += 1
    db.commit()
    flash(_t(f'تمت إضافة {added} مدعو', f'Added {added} attendees'), 'success')
    return redirect(url_for('checkin.admin_detail', event_id=event.id))


@checkin_bp.route('/admin/<int:event_id>/attendees/<int:aid>/delete', methods=['POST'])
@admin_required
def admin_attendee_delete(event_id, aid):
    db = get_db()
    a = db.get(EventAttendee, aid)
    if a and a.event_id == event_id:
        db.delete(a)
        db.commit()
    return jsonify({'ok': True})


@checkin_bp.route('/admin/<int:event_id>/send-codes', methods=['POST'])
@admin_required
def admin_send_codes(event_id):
    db = get_db()
    event = db.get(EventCheckin, event_id)
    if not event:
        abort(404)

    from utils.email_helper import send_event_checkin_code
    lang = get_lang()
    checkin_url = url_for('checkin.public_checkin', event_id=event.id, _external=True)

    selected_ids = request.form.getlist('attendee_ids', type=int)
    if selected_ids:
        targets = [a for a in event.attendees if a.id in selected_ids and a.email]
    else:
        only_unsent = request.form.get('only_unsent', '1') == '1'
        targets = [a for a in event.attendees if (not only_unsent or not a.code_sent) and a.email]

    sent, failed = 0, 0
    for a in targets:
        try:
            ok = send_event_checkin_code(
                a.email, a.name, a.code, event.name, event.event_date,
                event.window_start, event.window_end, checkin_url, lang,
            )
        except Exception:
            ok = False
        if ok:
            a.code_sent = True
            sent += 1
        else:
            failed += 1
    db.commit()

    no_email_count = sum(1 for a in (event.attendees if not selected_ids else
                          [x for x in event.attendees if x.id in selected_ids]) if not a.email)
    msg = _t(f'تم إرسال {sent} رمز بنجاح', f'{sent} codes sent successfully')
    if failed:
        msg += _t(f'، وفشل إرسال {failed}', f', {failed} failed')
        msg += _t(' — راجع صفحة سجل البريد (Email Logs) لسبب الفشل بالتفصيل',
                   ' — check the Email Logs page for the detailed reason')
    if no_email_count:
        msg += _t(f' ({no_email_count} بدون بريد إلكتروني)', f' ({no_email_count} with no email)')
    flash(msg, 'success' if not failed else 'warning')
    return redirect(url_for('checkin.admin_detail', event_id=event.id))


@checkin_bp.route('/admin/<int:event_id>/report')
@admin_required
def admin_report(event_id):
    db = get_db()
    event = db.get(EventCheckin, event_id)
    if not event:
        abort(404)
    attendees = sorted(event.attendees, key=lambda a: a.name)
    now = _now_amman()
    resolved = [(a, _resolve_status(event, a, now)) for a in attendees]
    counts = {'on_time': 0, 'late': 0, 'absent': 0, 'pending': 0}
    for _, st in resolved:
        counts[st] += 1
    return render_template('checkin/admin/report.html', event=event, resolved=resolved, counts=counts)


# ===========================================================================
# PUBLIC CHECK-IN PAGE (no login — attendees use this at the door)
# ===========================================================================

@checkin_bp.route('/<int:event_id>', methods=['GET', 'POST'])
def public_checkin(event_id):
    db = get_db()
    event = db.get(EventCheckin, event_id)
    if not event:
        abort(404)
    cfg = _get_school_config()

    if request.method == 'GET':
        return render_template('checkin/checkin.html', event=event, config=cfg, result=None)

    code = request.form.get('code', '').strip().upper()
    late_reason = request.form.get('late_reason', '').strip()

    attendee = (
        db.query(EventAttendee)
        .filter(EventAttendee.event_id == event.id, EventAttendee.code == code)
        .first()
    )
    if not attendee:
        return render_template('checkin/checkin.html', event=event, config=cfg,
                                result={'ok': False, 'message': _t('الرمز غير صحيح', 'Invalid code')})

    if attendee.status in ('on_time', 'late'):
        return render_template('checkin/checkin.html', event=event, config=cfg,
                                result={'ok': False, 'message': _t('تم تسجيل حضورك مسبقاً', 'You have already checked in')})

    now = _now_amman()
    today_str = now.strftime('%Y-%m-%d')
    now_min = now.hour * 60 + now.minute
    start_min = _hhmm_to_minutes(event.window_start)
    end_min = _hhmm_to_minutes(event.window_end)
    early_open_min = start_min - (event.early_minutes or 0)
    grace_end_min = end_min + (event.grace_minutes or 0)

    if today_str != event.event_date:
        return render_template('checkin/checkin.html', event=event, config=cfg,
                                result={'ok': False, 'message': _t('هذا الرمز غير صالح اليوم', 'This code is not valid today')})

    if now_min < early_open_min:
        open_time = f'{early_open_min // 60:02d}:{early_open_min % 60:02d}'
        return render_template('checkin/checkin.html', event=event, config=cfg,
                                result={'ok': False, 'message': _t(f'التسجيل يبدأ الساعة {open_time}', f'Check-in opens at {open_time}')})

    if now_min <= end_min:
        attendee.status = 'on_time'
        attendee.checked_in_at = now
        db.commit()
        return render_template('checkin/checkin.html', event=event, config=cfg,
                                result={'ok': True, 'late': False, 'name': attendee.name})

    if now_min <= grace_end_min:
        if not late_reason:
            return render_template('checkin/checkin.html', event=event, config=cfg,
                                    result={'ok': False, 'need_reason': True, 'code': code,
                                            'message': _t('تجاوزت الوقت المحدد — الرجاء ذكر سبب التأخير',
                                                           'You are past the on-time window — please state a reason for lateness')})
        attendee.status = 'late'
        attendee.checked_in_at = now
        attendee.late_reason = late_reason
        db.commit()
        return render_template('checkin/checkin.html', event=event, config=cfg,
                                result={'ok': True, 'late': True, 'name': attendee.name})

    return render_template('checkin/checkin.html', event=event, config=cfg,
                            result={'ok': False, 'expired': True,
                                    'message': _t('انتهت مهلة تسجيل الحضور، تم اعتبارك غائباً عن الاجتماع',
                                                   'The check-in window has closed — you are recorded as absent from the meeting')})
