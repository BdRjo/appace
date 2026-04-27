"""
Public Calendar — روزنامة عامة بدون تسجيل دخول
Blueprint منفصل تماماً عن calendar_view.py
"""
import re
import base64
import io
from flask import Blueprint, render_template, jsonify, request, current_app, send_file
from models.database import Reservation, Venue, Location, Attachment, User
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

    try:
        q = db.query(Reservation).filter(Reservation.status == 'approved')
        if start_dt: q = q.filter(Reservation.end_time   >= start_dt)
        if end_dt:   q = q.filter(Reservation.start_time <= end_dt)
        if vid and vid.isdigit():
            q = q.filter(Reservation.venue_id == int(vid))

        result = []
        for r in q.all():
            try:
                venue = db.query(Venue).filter_by(id=r.venue_id).first() if r.venue_id else None
                result.append({
                    'id':    r.id,
                    'title': (r.title or '') + (' — ' + venue.name if venue else ''),
                    'start': r.start_time.isoformat() if r.start_time else '',
                    'end':   r.end_time.isoformat()   if r.end_time   else '',
                    'color': '#3D8EF5',
                })
            except Exception as e:
                current_app.logger.warning(f'event row skip: {e}')
                continue
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f'events endpoint error: {e}')
        return jsonify([])


@public_cal_bp.route('/booking/<int:res_id>')
def booking_detail(res_id):
    try:
        db  = get_db()
        res = db.query(Reservation).filter_by(id=res_id).first()
        if not res or res.status != 'approved':
            return jsonify({'error': 'not found'}), 404

        venue    = db.query(Venue).filter_by(id=res.venue_id).first()          if res.venue_id               else None
        location = db.query(Location).filter_by(id=venue.location_id).first()  if venue and venue.location_id else None

        notes_raw   = getattr(res, 'requester_notes', '') or ''
        on_behalf_m = re.search(r'\[on_behalf:([^\]]+)\]', notes_raw)
        on_behalf   = on_behalf_m.group(1) if on_behalf_m else ''
        clean_notes = re.sub(r'\[on_behalf:[^\]]+\]', '', notes_raw).strip()

        requester = db.query(User).filter_by(id=res.user_id).first() if res.user_id else None

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

        return jsonify({
            'booking_number':     res.booking_number or '',
            'title':              getattr(res, 'title', None) or '',
            'status_ar':          'معتمد',
            'status_en':          'Approved',
            'start_time':         res.start_time.strftime('%Y-%m-%d %H:%M') if res.start_time else '',
            'end_time':           res.end_time.strftime('%Y-%m-%d %H:%M')   if res.end_time   else '',
            'full_day':           bool(res.start_time and res.end_time and
                                       res.start_time.hour == 0 and res.start_time.minute == 0 and
                                       res.end_time.hour == 23 and res.end_time.minute >= 59),
            'date_only':          res.start_time.strftime('%Y-%m-%d') if res.start_time else '',
            'notes':              clean_notes,
            'on_behalf':          on_behalf,
            'requester_name':     (requester.full_name or requester.username) if requester else '',
            'expected_attendees': str(getattr(res, 'expected_attendees', '') or ''),
            'venue_name':         venue.name           if venue    else '',
            'venue_capacity':     str(venue.capacity)  if venue and getattr(venue, 'capacity', None) else '',
            'location_name':      location.name        if location else '',
            'attachments':        att_list,
        })
    except Exception as e:
        current_app.logger.error(f'booking detail error: {e}')
        return jsonify({'error': 'server error'}), 500


@public_cal_bp.route('/attachment/<int:att_id>')
def public_attachment(att_id):
    try:
        db  = get_db()
        att = db.query(Attachment).filter_by(id=att_id).first()
        if not att:
            return jsonify({'error': 'not found'}), 404
        res = db.query(Reservation).filter_by(id=att.reservation_id).first()
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
