"""
Public Calendar — روزنامة عامة بدون تسجيل دخول
"""
import re
import base64
import io
from flask import Blueprint, render_template, jsonify, request, current_app, send_file, flash, redirect, url_for
from models.database import Reservation, Venue, Location, Attachment, User, BlockedPeriod
from utils.helpers import get_db
from datetime import datetime

public_cal_bp = Blueprint('public_cal', __name__, url_prefix='/public-calendar')


def _book_num_guest(db):
    from datetime import datetime
    import random, string
    ts  = datetime.now().strftime('%Y%m%d%H%M%S')
    rnd = ''.join(random.choices(string.digits, k=4))
    return f'PUB-{ts}-{rnd}'


def _get_mc():
    import json, os
    try:
        p = os.path.join(os.path.dirname(__file__), '..', 'maintenance_config.json')
        return json.loads(open(p).read()) if os.path.exists(p) else {}
    except Exception:
        return {}


@public_cal_bp.route('/', strict_slashes=False)
def index():
    db     = get_db()
    venues = db.query(Venue).filter_by(is_active=True).order_by(Venue.name).all()
    mc     = _get_mc()
    return render_template('calendar/public.html', venues=venues, mc=mc)


@public_cal_bp.route('/book', methods=['GET', 'POST'])
def book():
    db     = get_db()
    venues = db.query(Venue).filter_by(is_active=True).order_by(Venue.name).all()
    mc     = _get_mc()

    if request.method == 'POST':
        # بيانات الطالب
        guest_name   = request.form.get('guest_name', '').strip()
        guest_email  = request.form.get('guest_email', '').strip()
        guest_phone  = request.form.get('guest_phone', '').strip()
        on_behalf    = request.form.get('on_behalf', '').strip()
        title        = request.form.get('title', '').strip()
        venue_id     = request.form.get('venue_id', '').strip()
        notes        = request.form.get('notes', '').strip()
        full_day     = request.form.get('full_day') == '1'

        if full_day:
            date_val = request.form.get('full_day_date', '')
            try:
                start_dt = datetime.strptime(date_val + ' 00:00', '%Y-%m-%d %H:%M')
                end_dt   = datetime.strptime(date_val + ' 23:59', '%Y-%m-%d %H:%M')
            except Exception:
                flash('تاريخ غير صحيح', 'danger')
                return render_template('calendar/public_book.html', venues=venues, mc=mc, form=request.form)
        else:
            try:
                start_dt = datetime.strptime(request.form.get('start_time',''), '%Y-%m-%dT%H:%M')
                end_dt   = datetime.strptime(request.form.get('end_time',''),   '%Y-%m-%dT%H:%M')
            except Exception:
                flash('وقت غير صحيح', 'danger')
                return render_template('calendar/public_book.html', venues=venues, mc=mc, form=request.form)

        if not all([guest_name, guest_email, title, venue_id]):
            flash('يرجى تعبئة جميع الحقول المطلوبة', 'danger')
            return render_template('calendar/public_book.html', venues=venues, mc=mc, form=request.form)

        # بناء الملاحظات مع بيانات الضيف
        full_notes = notes
        full_notes = (full_notes + '\n' if full_notes else '') + f'[guest_name:{guest_name}]'
        full_notes += f'\n[guest_email:{guest_email}]'
        if guest_phone: full_notes += f'\n[guest_phone:{guest_phone}]'
        if on_behalf:   full_notes += f'\n[on_behalf:{on_behalf}]'

        res = Reservation(
            booking_number = _book_num_guest(db),
            title          = title,
            user_id        = None,
            venue_id       = int(venue_id),
            start_time     = start_dt,
            end_time       = end_dt,
            status         = 'pending',
            booking_type   = 'external',
            requester_notes= full_notes,
        )
        db.add(res)
        db.flush()

        # المرفقات
        for f in request.files.getlist('attachments'):
            if f and f.filename:
                try:
                    data = base64.b64encode(f.read()).decode()
                    att  = Attachment(reservation_id=res.id, filename=f.filename,
                                      mimetype=f.mimetype, filedata=data)
                    db.add(att)
                except Exception:
                    pass

        db.commit()

        # إرسال إيميل تأكيد للطالب
        try:
            from utils.email_helper import _send, _html_wrapper, _info_row
            mc2   = _get_mc()
            venue = db.query(Venue).filter_by(id=int(venue_id)).first()
            subj  = f'✅ تم استلام طلب الحجز — {res.booking_number}'
            content = f"""
<div style="padding:16px;background:#e8f0ff;border-radius:10px;margin-bottom:16px;text-align:center">
  <div style="font-size:32px">📋</div>
  <h3 style="color:#0C67EC;margin:8px 0">تم استلام طلب الحجز</h3>
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #b8d0ff;border-radius:10px;overflow:hidden">
  {_info_row('📋 رقم الطلب', f'<strong style="color:#0C67EC">{res.booking_number}</strong>', '#f0f4ff')}
  {_info_row('📌 العنوان', title, '#ffffff')}
  {_info_row('🏢 القاعة', venue.name if venue else '', '#f0f4ff')}
  {_info_row('🕐 البداية', start_dt.strftime('%Y-%m-%d %H:%M'), '#ffffff')}
  {_info_row('🕐 الانتهاء', end_dt.strftime('%Y-%m-%d %H:%M'), '#f0f4ff')}
</table>
<div style="background:#fff3cd;border-radius:8px;padding:12px 16px;margin-top:16px;color:#856404;font-size:14px">
  ⏳ طلبك قيد المراجعة — سيصلك إيميل آخر عند البت في الطلب.
</div>"""
            _send(guest_email, guest_name, subj, _html_wrapper(content, subj, 'ar'),
                  f'تم استلام طلب الحجز {res.booking_number}', sync=False, email_type='notification')
        except Exception as e:
            current_app.logger.warning(f'public booking email error: {e}')

        return render_template('calendar/public_book_success.html',
                               res=res, mc=mc, guest_name=guest_name)

    return render_template('calendar/public_book.html', venues=venues, mc=mc, form={})


@public_cal_bp.route('/events')
def events():
    db    = get_db()
    start = request.args.get('start', '')
    end   = request.args.get('end', '')
    vid   = request.args.get('venue_id', '')
    try:
        from datetime import timedelta
        start_dt = datetime.fromisoformat(start[:10]) if start else None
        end_dt   = datetime.fromisoformat(end[:10]) + timedelta(days=1) if end else None
    except Exception:
        start_dt = end_dt = None
    try:
        # حجوزات معتمدة ومعلقة
        q = db.query(Reservation).filter(
            Reservation.status.in_(['approved', 'pending'])
        )
        if start_dt: q = q.filter(Reservation.end_time   >= start_dt)
        if end_dt:   q = q.filter(Reservation.start_time <  end_dt)
        if vid and vid.isdigit():
            q = q.filter(Reservation.venue_id == int(vid))

        result = []
        for r in q.all():
            try:
                venue = db.query(Venue).filter_by(id=r.venue_id).first() if r.venue_id else None
                title = r.title or ''
                if venue: title = title + (' — ' + venue.name if title else venue.name)
                color = '#3D8EF5' if r.status == 'approved' else '#F59E0B'
                result.append({
                    'id':    r.id,
                    'title': '🔒 ' + ('محجوز' if request.args.get('lang','ar')=='ar' else 'Booked'),
                    'start': r.start_time.isoformat() if r.start_time else '',
                    'end':   r.end_time.isoformat()   if r.end_time   else '',
                    'color': '#94a3b8' if r.status == 'pending' else '#3D8EF5',
                    'status': r.status,
                })
            except Exception as e:
                current_app.logger.warning(f'event row skip: {e}')
                continue

        # فترات الحظر
        bq = db.query(BlockedPeriod)
        if start_dt: bq = bq.filter(BlockedPeriod.end_time   >= start_dt)
        if end_dt:   bq = bq.filter(BlockedPeriod.start_time <= end_dt)
        if vid and vid.isdigit():
            bq = bq.filter(BlockedPeriod.venue_id == int(vid))
        for bp in bq.all():
            try:
                venue = db.query(Venue).filter_by(id=bp.venue_id).first() if bp.venue_id else None
                result.append({
                    'id':    f'bp_{bp.id}',
                    'title': '🚫 ' + (bp.reason or 'فترة محظورة'),
                    'start': bp.start_time.isoformat(),
                    'end':   bp.end_time.isoformat(),
                    'color': '#EF4444',
                    'status': 'blocked',
                })
            except Exception:
                continue

        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f'events error: {e}')
        return jsonify([])


@public_cal_bp.route('/booking/<int:res_id>')
def booking_detail(res_id):
    try:
        db  = get_db()
        res = db.query(Reservation).filter_by(id=res_id).first()
        if not res or res.status not in ('approved', 'pending'):
            return jsonify({'error': 'not found'}), 404

        venue    = db.query(Venue).filter_by(id=res.venue_id).first()           if res.venue_id               else None
        location = db.query(Location).filter_by(id=venue.location_id).first()   if venue and venue.location_id else None
        requester= db.query(User).filter_by(id=res.user_id).first()             if res.user_id                else None

        notes_raw = getattr(res, 'requester_notes', '') or ''

        def extract(tag):
            m = re.search(rf'\[{tag}:([^\]]+)\]', notes_raw)
            return m.group(1) if m else ''

        guest_name  = extract('guest_name')
        guest_email = extract('guest_email')
        guest_phone = extract('guest_phone')
        on_behalf   = extract('on_behalf')

        clean_notes = re.sub(r'\[(?:guest_name|guest_email|guest_phone|on_behalf|cc_emails):[^\]]+\]', '', notes_raw).strip()

        requester_name = guest_name or ((requester.full_name or requester.username) if requester else '')

        atts = db.query(Attachment).filter_by(reservation_id=res_id).all()
        att_list = []
        for a in atts:
            mime = a.mimetype or ''
            att_list.append({
                'id':     a.id,
                'name':   a.filename,
                'mime':   mime,
                'is_img': mime.startswith('image/'),
                'url':    f'/public-calendar/attachment/{a.id}',
            })

        full_day = bool(res.start_time and res.end_time and
                        res.start_time.hour == 0 and res.start_time.minute == 0 and
                        res.end_time.hour == 23 and res.end_time.minute >= 59)

        status_map = {
            'approved': {'ar': 'معتمد', 'en': 'Approved'},
            'pending':  {'ar': 'قيد المراجعة', 'en': 'Pending Review'},
        }

        return jsonify({
            'booking_number':     res.booking_number or '',
            'title':              res.title or '',
            'status':             res.status,
            'status_ar':          status_map.get(res.status, {}).get('ar', res.status),
            'status_en':          status_map.get(res.status, {}).get('en', res.status),
            'status_color':       '#22c55e' if res.status == 'approved' else '#f59e0b',
            'start_time':         res.start_time.strftime('%Y-%m-%d %H:%M') if res.start_time else '',
            'end_time':           res.end_time.strftime('%Y-%m-%d %H:%M')   if res.end_time   else '',
            'full_day':           full_day,
            'date_only':          res.start_time.strftime('%Y-%m-%d') if res.start_time else '',
            'notes':              clean_notes,
            'on_behalf':          on_behalf,
            'requester_name':     requester_name,
            'guest_email':        guest_email,
            'guest_phone':        guest_phone,
            'expected_attendees': str(getattr(res, 'expected_attendees', '') or ''),
            'venue_name':         venue.name           if venue    else '',
            'venue_capacity':     str(venue.capacity)  if venue and getattr(venue, 'capacity', None) else '',
            'location_name':      location.name        if location else '',
            'attachments':        att_list,
        })
    except Exception as e:
        current_app.logger.error(f'booking detail error: {e}')
        return jsonify({'error': 'server error'}), 500



@public_cal_bp.route('/lookup', methods=['GET','POST'])
def lookup():
    from utils.helpers import get_lang
    lang = get_lang()
    result = None
    error  = None
    query  = ''
    if request.method == 'POST':
        query = request.form.get('query','').strip()
        if query:
            db = get_db()
            res = db.query(Reservation).filter(
                Reservation.booking_number == query
            ).first()
            if not res:
                # try by email
                from models.database import User
                user = db.query(User).filter_by(email=query).first()
                if user:
                    res = db.query(Reservation).filter_by(user_id=user.id).order_by(Reservation.id.desc()).first()
            if res:
                venue = db.query(Venue).filter_by(id=res.venue_id).first() if res.venue_id else None
                result = {
                    'booking_number': res.booking_number,
                    'title':    res.title,
                    'status':   res.status,
                    'start':    res.start_time.strftime('%Y-%m-%d %H:%M') if res.start_time else '',
                    'end':      res.end_time.strftime('%Y-%m-%d %H:%M')   if res.end_time   else '',
                    'venue':    venue.name if venue else '—',
                    'notes':    res.approver_notes or '',
                    'req_notes':res.requester_notes or '',
                }
            else:
                error = 'لم يتم العثور على الحجز' if lang=='ar' else 'Booking not found'
    return render_template('calendar/lookup.html', result=result, error=error, query=query, lang=lang)
@public_cal_bp.route('/attachment/<int:att_id>')
def public_attachment(att_id):
    try:
        db  = get_db()
        att = db.query(Attachment).filter_by(id=att_id).first()
        if not att: return jsonify({'error': 'not found'}), 404
        res = db.query(Reservation).filter_by(id=att.reservation_id).first()
        if not res or res.status not in ('approved', 'pending'):
            return jsonify({'error': 'not found'}), 404
        file_data = base64.b64decode(att.filedata)
        return send_file(io.BytesIO(file_data), download_name=att.filename,
                         mimetype=att.mimetype or 'application/octet-stream')
    except Exception as e:
        current_app.logger.error(f'attachment error: {e}')
        return jsonify({'error': 'server error'}), 500
