"""
iFace 702 Device Integration — Employee Attendance
====================================================
Connects to an iFace 702 (ZKTeco-compatible) biometric device over TCP/IP,
pulls attendance logs for a selected date range, maps them to EASEmployee records
by employee_id, calculates status using the selected group's timetable (shift
settings), and saves EASRecord rows with source='iface702'.

Blueprint prefix: /eas/device
Register in app.py:
    from routes.iface_device import iface_bp
    app.register_blueprint(iface_bp)

Requires:  pyzk>=0.9   (add to requirements.txt)
           pip install pyzk
"""

import json
from datetime import datetime, date, timedelta
from collections import defaultdict

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, abort, session
)
from sqlalchemy.orm import joinedload

from models.database import SASConfig, EASGroup, EASEmployee, EASRecord
from utils.helpers import admin_required, get_db
from utils.i18n import get_lang

iface_bp = Blueprint('iface_device', __name__, url_prefix='/eas/device')

# ── i18n helper ──────────────────────────────────────────────────────────────
def _t(ar: str, en: str) -> str:
    return en if get_lang() == 'en' else ar


# ── Internal helpers ─────────────────────────────────────────────────────────

def _get_config():
    db = get_db()
    cfg = db.query(SASConfig).first()
    if not cfg:
        abort(404, "SAS config not found")
    return cfg


def _connect_device(ip: str, port: int, password: int = 0, timeout: int = 10):
    """
    Open a connection to an iFace 702 / ZKTeco device.
    Returns a ZK object (already connected) or raises RuntimeError.
    """
    try:
        from zk import ZK  # pyzk
    except ImportError:
        raise RuntimeError(
            "pyzk is not installed. Run:  pip install pyzk"
        )
    zk = ZK(ip, port=port, timeout=timeout, password=password, force_udp=False, ommit_ping=True)
    conn = zk.connect()
    return conn


def _parse_hhmm(v) -> str:
    """Return 'HH:MM' string from various input types, or empty string."""
    if v is None:
        return ''
    if isinstance(v, datetime):
        return v.strftime('%H:%M')
    s = str(v).strip()
    if len(s) >= 5:
        return s[:5]
    return ''


def _calc_status(check_in_str: str, shift_start_str: str, late_tolerance_min: int):
    """Return (status, late_minutes)."""
    if not check_in_str:
        return 'absent', 0
    try:
        ci = datetime.strptime(check_in_str[:5], '%H:%M')
        sh = datetime.strptime(shift_start_str[:5], '%H:%M')
        diff = int((ci - sh).total_seconds() / 60)
        if diff > late_tolerance_min:
            return 'late', diff
        return 'present', 0
    except Exception:
        return 'present', 0


# ── Routes ────────────────────────────────────────────────────────────────────

@iface_bp.route('/', methods=['GET'])
@admin_required
def index():
    """
    Main page: device settings form + date range + group/timetable selector.
    Saved device settings are stored in the user session for convenience.
    """
    db = get_db()
    cfg = _get_config()
    groups = (
        db.query(EASGroup)
        .filter(EASGroup.config_id == cfg.id)
        .order_by(EASGroup.name)
        .all()
    )
    # Restore last-used device settings from session
    device_defaults = session.get('iface_device', {
        'ip': '',
        'port': 4370,
        'password': 0,
        'timeout': 10,
    })
    return render_template(
        'eas/iface_device.html',
        config=cfg,
        groups=groups,
        device=device_defaults,
        today=date.today().strftime('%Y-%m-%d'),
    )


@iface_bp.route('/test-connection', methods=['POST'])
@admin_required
def test_connection():
    """
    AJAX endpoint — tries to open a socket to the device and returns JSON.
    Body: { ip, port, password, timeout }
    """
    data = request.get_json(silent=True) or {}
    ip       = str(data.get('ip', '')).strip()
    port     = int(data.get('port', 4370))
    password = int(data.get('password', 0))
    timeout  = int(data.get('timeout', 10))

    if not ip:
        return jsonify(ok=False, message=_t('يرجى إدخال عنوان IP', 'Please enter IP address'))

    try:
        conn = _connect_device(ip, port, password, timeout)
        info = {}
        try:
            info['serial'] = conn.get_serialnumber()
        except Exception:
            pass
        try:
            info['firmware'] = conn.get_firmware_version()
        except Exception:
            pass
        try:
            info['users'] = conn.get_users_count()
        except Exception:
            pass
        conn.disconnect()
        return jsonify(ok=True, info=info,
                       message=_t('تم الاتصال بنجاح', 'Connected successfully'))
    except Exception as exc:
        return jsonify(ok=False, message=str(exc))


@iface_bp.route('/fetch', methods=['POST'])
@admin_required
def fetch():
    """
    Fetches attendance logs from the device for the given date range,
    maps them to EASEmployee rows (by employee_id field), calculates
    attendance status using the selected group's timetable, and saves
    EASRecord rows with source='iface702'.

    Form fields:
        ip, port, password, timeout
        date_from (YYYY-MM-DD), date_to (YYYY-MM-DD)
        group_ids[]  — one or more EASGroup IDs to process
        overwrite    — 'yes' to replace existing iface702 records in the range
    """
    db  = get_db()
    cfg = _get_config()

    # ── read form ────────────────────────────────────────────────────────────
    # دعم عدة أجهزة
    ips_raw    = request.form.get('ip', '').strip()
    ips        = [i.strip() for i in ips_raw.replace(',', '\n').splitlines() if i.strip()]
    ip         = ips[0] if ips else ''
    port       = int(request.form.get('port') or 4370)
    password   = int(request.form.get('password') or 0)
    timeout    = int(request.form.get('timeout') or 10)
    date_from  = request.form.get('date_from', '')
    date_to    = request.form.get('date_to', '')
    group_ids  = request.form.getlist('group_ids', type=int)
    overwrite  = request.form.get('overwrite', 'no') == 'yes'

    # ── persist device settings in session ───────────────────────────────────
    session['iface_device'] = {'ip': ip, 'port': port, 'password': password, 'timeout': timeout}

    # ── validate ─────────────────────────────────────────────────────────────
    if not ip:
        flash(_t('يرجى إدخال عنوان IP للجهاز', 'Please enter device IP address'), 'danger')
        return redirect(url_for('iface_device.index'))
    if not date_from or not date_to:
        flash(_t('يرجى تحديد نطاق التاريخ', 'Please select a date range'), 'danger')
        return redirect(url_for('iface_device.index'))
    if not group_ids:
        flash(_t('يرجى اختيار مجموعة واحدة على الأقل', 'Please select at least one group'), 'danger')
        return redirect(url_for('iface_device.index'))

    try:
        d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        d_to   = datetime.strptime(date_to,   '%Y-%m-%d').date()
    except ValueError:
        flash(_t('تنسيق التاريخ غير صحيح', 'Invalid date format'), 'danger')
        return redirect(url_for('iface_device.index'))

    if d_from > d_to:
        flash(_t('تاريخ البداية يجب أن يكون قبل تاريخ النهاية',
                 'Start date must be before end date'), 'danger')
        return redirect(url_for('iface_device.index'))

    # ── fetch selected groups ─────────────────────────────────────────────────
    groups = (
        db.query(EASGroup)
        .filter(EASGroup.config_id == cfg.id, EASGroup.id.in_(group_ids))
        .all()
    )
    if not groups:
        flash(_t('لم يتم العثور على المجموعات المحددة', 'Selected groups not found'), 'danger')
        return redirect(url_for('iface_device.index'))

    # ── connect to device ─────────────────────────────────────────────────────
    try:
        conn = _connect_device(ip, port, password, timeout)
    except Exception as exc:
        flash(_t(f'فشل الاتصال بالجهاز: {exc}', f'Device connection failed: {exc}'), 'danger')
        return redirect(url_for('iface_device.index'))

    # ── pull attendance logs ──────────────────────────────────────────────────
    # جلب من عدة أجهزة
    attendances = []
    failed_ips = []
    for device_ip in ips:
        try:
            from zk import ZK
            _zk = ZK(device_ip, port=port, timeout=timeout, password=password, force_udp=False, ommit_ping=True)
            _conn = _zk.connect()
            attendances += _conn.get_attendance()
            _conn.disconnect()
        except Exception as exc:
            failed_ips.append(f'{device_ip}: {exc}')
    
    if failed_ips:
        flash(_t(f'تعذر الاتصال بـ: {", ".join(failed_ips)}', f'Could not connect to: {", ".join(failed_ips)}'), 'warning')
    
    if not attendances:
        flash(_t('لم يتم جلب أي سجلات', 'No records fetched'), 'danger')
        return redirect(url_for('iface_device.index'))

    # ── filter by date range & build per-user-per-day buckets ─────────────────
    # Each attendance entry has: user_id (str), timestamp (datetime), status (int), punch (int)
    # punch: 0=check-in, 1=check-out  (device-dependent; we use min=in, max=out)
    day_punches: dict[tuple, list[datetime]] = defaultdict(list)
    for att in attendances:
        if att.timestamp is None:
            continue
        att_date = att.timestamp.date()
        if not (d_from <= att_date <= d_to):
            continue
        key = (str(att.user_id), att_date.strftime('%Y-%m-%d'))
        day_punches[key].append(att.timestamp)

    # ── build employee_id → employee map for selected groups ──────────────────
    emp_map: dict[str, EASEmployee] = {}
    for grp in groups:
        for emp in db.query(EASEmployee).filter(
            EASEmployee.group_id == grp.id,
            EASEmployee.is_active == True,
        ).all():
            if emp.employee_id:
                emp_map[str(emp.employee_id).strip()] = emp

    # ── optionally delete existing iface702 records in range for these groups ─
    if overwrite:
        emp_ids = [e.id for e in emp_map.values()]
        if emp_ids:
            db.query(EASRecord).filter(
                EASRecord.employee_id.in_(emp_ids),
                EASRecord.record_date >= date_from,
                EASRecord.record_date <= date_to,
                EASRecord.source == 'iface702',
            ).delete(synchronize_session=False)

    # ── build group shift lookup ───────────────────────────────────────────────
    group_by_emp: dict[int, EASGroup] = {}
    for grp in groups:
        for emp in grp.employees:
            group_by_emp[emp.id] = grp

    # ── create EASRecord rows ─────────────────────────────────────────────────
    added     = 0
    skipped   = 0
    unknown   = 0

    for (dev_uid, rec_date_str), timestamps in day_punches.items():
        emp = emp_map.get(dev_uid)
        if emp is None:
            unknown += 1
            continue

        grp = group_by_emp.get(emp.id)
        shift_start    = (grp.shift_start    or '07:30') if grp else '07:30'
        late_tolerance = (grp.late_tolerance or 10)      if grp else 10

        # first punch = check-in, last punch = check-out
        timestamps_sorted = sorted(timestamps)
        check_in_dt  = timestamps_sorted[0]
        check_out_dt = timestamps_sorted[-1] if len(timestamps_sorted) > 1 else None

        check_in_str  = check_in_dt.strftime('%H:%M')
        check_out_str = check_out_dt.strftime('%H:%M') if check_out_dt else ''

        status, late_min = _calc_status(check_in_str, shift_start, late_tolerance)

        # skip if record already exists (and not overwriting)
        exists = db.query(EASRecord).filter(
            EASRecord.employee_id == emp.id,
            EASRecord.record_date == rec_date_str,
        ).first()
        if exists and not overwrite:
            skipped += 1
            continue

        rec = EASRecord(
            employee_id  = emp.id,
            record_date  = rec_date_str,
            check_in     = check_in_str or None,
            check_out    = check_out_str or None,
            status       = status,
            late_minutes = late_min,
            source       = 'iface702',
        )
        db.add(rec)
        added += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        flash(_t(f'خطأ في حفظ البيانات: {exc}', f'Database error: {exc}'), 'danger')
        return redirect(url_for('iface_device.index'))

    # ── توليد سجلات الغياب للموظفين الذين لم يبصموا ──────────────────────────
    absent_added = 0
    from datetime import datetime as _dt, timedelta as _td
    for grp in groups:
        work_days_set = set(int(d) for d in (grp.work_days or '1,2,3,4,5').split(',') if d.strip())
        try:
            _d_from = _dt.strptime(date_from, '%Y-%m-%d').date()
            _d_to   = _dt.strptime(date_to,   '%Y-%m-%d').date()
        except ValueError:
            continue
        all_days = []
        _cur = _d_from
        while _cur <= _d_to:
            wd = (_cur.weekday() + 1) % 7
            if wd in work_days_set:
                all_days.append(_cur.strftime('%Y-%m-%d'))
            _cur += _td(days=1)

        emps = db.query(EASEmployee).filter(
            EASEmployee.group_id == grp.id,
            EASEmployee.is_active == True,
        ).all()

        for emp in emps:
            for day in all_days:
                exists = db.query(EASRecord).filter(
                    EASRecord.employee_id == emp.id,
                    EASRecord.record_date == day,
                ).first()
                if not exists:
                    db.add(EASRecord(
                        employee_id=emp.id,
                        record_date=day,
                        status='absent',
                        late_minutes=0,
                        source='auto',
                    ))
                    absent_added += 1
    try:
        db.commit()
    except Exception:
        db.rollback()

    parts = [_t(f'تم حفظ {added} سجل', f'Saved {added} records')]
    if skipped:
        parts.append(_t(f'تم تخطي {skipped} (موجود مسبقاً)', f'{skipped} skipped (already exist)'))
    if unknown:
        parts.append(_t(f'{unknown} بصمة غير معروفة (لا يوجد موظف مطابق)',
                        f'{unknown} unknown device IDs (no matching employee)'))
    flash(' | '.join(parts), 'success')

    # ── redirect to EAS report for first selected group ───────────────────────
    return redirect(url_for(
        'eas.report',
        group_id=group_ids[0],
        **{'from': date_from, 'to': date_to}
    ))


@iface_bp.route('/report', methods=['GET'])
@admin_required
def report():
    """
    Attendance report grouped by EASGroup, filtered by date range and
    optionally by timetable (group shift settings).
    Query params: group_ids (repeatable), from, to
    """
    db  = get_db()
    cfg = _get_config()

    group_ids  = request.args.getlist('group_ids', type=int)
    date_from  = request.args.get('from', '')
    date_to    = request.args.get('to', '')

    all_groups = (
        db.query(EASGroup)
        .filter(EASGroup.config_id == cfg.id)
        .order_by(EASGroup.name)
        .all()
    )

    report_data = []  # list of { group, employees: [{emp, records, stats}] }

    if group_ids and date_from and date_to:
        selected_groups = [g for g in all_groups if g.id in group_ids]
        for grp in selected_groups:
            emp_rows = []
            employees = (
                db.query(EASEmployee)
                .filter(EASEmployee.group_id == grp.id, EASEmployee.is_active == True)
                .order_by(EASEmployee.name)
                .all()
            )
            # generate all working days in range
            work_days_set = set(int(d) for d in (grp.work_days or '1,2,3,4,5').split(',') if d.strip())
            try:
                d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                d_to   = datetime.strptime(date_to,   '%Y-%m-%d').date()
            except ValueError:
                continue

            all_days = []
            cur = d_from
            while cur <= d_to:
                # weekday(): Mon=0 … Sun=6  →  our convention: 0=Sun,1=Mon,…,6=Sat
                wd = (cur.weekday() + 1) % 7  # convert Python weekday to Sun=0
                if wd in work_days_set:
                    all_days.append(cur.strftime('%Y-%m-%d'))
                cur += timedelta(days=1)

            for emp in employees:
                records_q = (
                    db.query(EASRecord)
                    .filter(
                        EASRecord.employee_id == emp.id,
                        EASRecord.record_date >= date_from,
                        EASRecord.record_date <= date_to,
                    )
                    .order_by(EASRecord.record_date)
                    .all()
                )
                rec_by_date = {r.record_date: r for r in records_q}

                # fill in absent for work days with no record
                full_records = []
                present_count = absent_count = late_count = 0
                total_late_min = 0
                for day in all_days:
                    if day in rec_by_date:
                        r = rec_by_date[day]
                        full_records.append(r)
                        if r.status == 'present':
                            present_count += 1
                        elif r.status == 'late':
                            late_count += 1
                            total_late_min += (r.late_minutes or 0)
                        elif r.status == 'absent':
                            absent_count += 1
                        else:
                            present_count += 1
                    else:
                        # synthesize absent record for display
                        absent_rec = EASRecord(
                            employee_id=emp.id,
                            record_date=day,
                            status='absent',
                            source='computed',
                        )
                        full_records.append(absent_rec)
                        absent_count += 1

                emp_rows.append({
                    'employee':      emp,
                    'records':       full_records,
                    'present_count': present_count,
                    'absent_count':  absent_count,
                    'late_count':    late_count,
                    'total_late_min': total_late_min,
                    'work_days':     len(all_days),
                })

            report_data.append({'group': grp, 'employees': emp_rows})

    return render_template(
        'eas/iface_report.html',
        config=cfg,
        all_groups=all_groups,
        group_ids=group_ids,
        date_from=date_from,
        date_to=date_to,
        report_data=report_data,
    )

@iface_bp.route('/import-users', methods=['POST'])
@admin_required
def import_users():
    """جلب المستخدمين من الجهاز وإضافتهم كموظفين"""
    db = get_db()
    cfg = _get_config()

    ip       = request.form.get('ip', '').strip()
    port     = int(request.form.get('port') or 4370)
    password = int(request.form.get('password') or 0)
    timeout  = int(request.form.get('timeout') or 10)
    group_id = request.form.get('group_id', type=int)

    if not ip or not group_id:
        flash(_t('يرجى إدخال IP واختيار مجموعة', 'Please enter IP and select a group'), 'danger')
        return redirect(url_for('iface_device.index'))

    group = db.get(EASGroup, group_id)
    if not group:
        abort(404)

    try:
        from zk import ZK
        zk = ZK(ip, port=port, timeout=timeout, password=password, force_udp=False, ommit_ping=True)
        conn = zk.connect()
        users = conn.get_users()
        conn.disconnect()

        added = 0
        flash(f'الجهاز عنده {len(users)} مستخدم', 'info')
        for u in users:
            if not u.name: continue
            exists = db.query(EASEmployee).filter(
                EASEmployee.group_id == group_id,
                EASEmployee.employee_id == str(u.uid)
            ).first()
            if not exists:
                emp = EASEmployee(
                    group_id=group_id,
                    name=u.name,
                    employee_id=str(u.user_id),
                )
                db.add(emp)
                added += 1

        db.commit()
        flash(_t(f'تم استيراد {added} موظف من الجهاز', f'Imported {added} employees from device'), 'success')
    except Exception as e:
        flash(_t(f'خطأ: {e}', f'Error: {e}'), 'danger')

    return redirect(url_for('iface_device.index'))
