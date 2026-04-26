"""
Public Calendar — روزنامة عامة بدون تسجيل دخول
Blueprint منفصل تماماً عن calendar_view.py
"""
from flask import Blueprint, render_template, jsonify, request, current_app
from models.database import Reservation, Venue, Location, Attachment
from utils.helpers import get_db
from datetime import datetime

public_cal_bp = Blueprint('public_cal', __name__, url_prefix='/public-calendar')


@public_cal_bp.route('/')
def index():
    db     = get_db()
    venues = db.query(Venue).filter_by(is_active=True).order_by(Venue.name).all()
    return render_template('calendar/public_cal.html', venues=venues)


@public_cal_bp.route('/events')
def events():
    db    = get_db()
    start = request.args.get('start', '')
    end   = request.args.get('end', '')
    vid   = request.args.get('venue_id', '')

    try:
        start_dt = datetime.fromisoformat(start[:10]) if start else None
        end_dt   = datetime.fromisoformat(end[:10])   if end   else None
    except Exception:
        start_dt = end_dt = None

    q = db.query(Reservation).filter(Reservation.status == 'approved')
    if start_dt: q = q.filter(Reservation.end_time   >= start_dt)
    if end_dt:   q = q.filter(Reservation.start_time <= end_dt)
    if vid and vid.isdigit():
        q = q.filter(Reservation.venue_id == int(vid))

    result = []
    for r in q.all():
        try:
            venue = db.query(Venue).get(r.venue_id) if r.venue_id else None
            result.append({
                'id':    r.id,
                'title': (r.title or '') + (' — ' + venue.name if venue else ''),
                'start': r.start_time.isoformat() if r.start_time else '',
                'end':   r.end_time.isoformat()   if r.end_time   else '',
                'color': '#3D8EF5',
            })
        except Exception:
            continue
    return jsonify(result)


@public_cal_bp.route('/booking/<int:res_id>')
def booking_detail(res_id):
    try:
        import re
        db  = get_db()
        res = db.query(Reservation).get(res_id)
        if not res or res.status != 'approved':
            return jsonify({'error': 'not found'}), 404

        venue    = db.query(Venue).get(res.venue_id)          if res.venue_id               else None
        location = db.query(Location).get(venue.location_id)  if venue and venue.location_id else None

        # استخراج on_behalf من الملاحظات
        notes_raw    = getattr(res, 'requester_notes', '') or ''
        on_behalf_m  = re.search(r'\[on_behalf:([^\]]+)\]', notes_raw)
        on_behalf    = on_behalf_m.group(1) if on_behalf_m else ''
        clean_notes  = re.sub(r'\[on_behalf:[^\]]+\]', '', notes_raw).strip()

        # المرفقات
        atts = db.query(Attachment).filter_by(reservation_id=res_id).all()
        att_list = [{'id': a.id, 'name': a.filename} for a in atts]

        return jsonify({
            'booking_number':     res.booking_number or '',
            'title':              getattr(res, 'title', None) or '',
            'status_ar':          'معتمد',
            'status_en':          'Approved',
            'start_time':         res.start_time.strftime('%Y-%m-%d %H:%M') if res.start_time else '',
            'end_time':           res.end_time.strftime('%Y-%m-%d %H:%M')   if res.end_time   else '',
            'notes':              clean_notes,
            'on_behalf':          on_behalf,
            'expected_attendees': str(getattr(res, 'expected_attendees', '') or ''),
            'venue_name':         venue.name           if venue    else '',
            'venue_capacity':     str(venue.capacity)  if venue and getattr(venue, 'capacity', None) else '',
            'location_name':      location.name        if location else '',
            'attachments':        att_list,
        })
    except Exception as e:
        current_app.logger.error(f'public booking detail error: {e}')
        return jsonify({'error': 'server error'}), 500


@public_cal_bp.route('/attachment/<int:att_id>')
def public_attachment(att_id):
    """تحميل مرفق عام — للحجوزات المعتمدة فقط"""
    try:
        import base64, io
        from flask import send_file
        db  = get_db()
        att = db.query(Attachment).get(att_id)
        if not att:
            return jsonify({'error': 'not found'}), 404
        res = db.query(Reservation).get(att.reservation_id)
        if not res or res.status != 'approved':
            return jsonify({'error': 'not found'}), 404
        file_data = base64.b64decode(att.filedata)
        return send_file(
            io.BytesIO(file_data),
            download_name=att.filename,
            mimetype=att.mimetype or 'application/octet-stream'
        )
    except Exception as e:
        current_app.logger.error(f'public attachment error: {e}')
        return jsonify({'error': 'server error'}), 500
