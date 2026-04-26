"""
Public Calendar — روزنامة عامة بدون تسجيل دخول
Blueprint منفصل تماماً عن calendar_view.py
"""
from flask import Blueprint, render_template, jsonify, request, current_app
from models.database import Reservation, Venue, Location
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
                'title': venue.name if venue else (r.title or ''),
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
        db  = get_db()
        res = db.query(Reservation).get(res_id)
        if not res or res.status != 'approved':
            return jsonify({'error': 'not found'}), 404

        venue    = db.query(Venue).get(res.venue_id)         if res.venue_id              else None
        location = db.query(Location).get(venue.location_id) if venue and venue.location_id else None

        return jsonify({
            'booking_number':     res.booking_number or '',
            'title':              getattr(res, 'title',              None) or '',
            'status_ar':          'معتمد',
            'status_en':          'Approved',
            'start_time':         res.start_time.strftime('%Y-%m-%d %H:%M') if res.start_time else '',
            'end_time':           res.end_time.strftime('%Y-%m-%d %H:%M')   if res.end_time   else '',
            'purpose':            getattr(res, 'purpose',            None) or '',
            'expected_attendees': str(getattr(res, 'expected_attendees', '') or ''),
            'venue_name':         venue.name            if venue    else '',
            'venue_capacity':     str(venue.capacity)   if venue and getattr(venue, 'capacity', None) else '',
            'location_name':      location.name         if location else '',
        })
    except Exception as e:
        current_app.logger.error(f'public booking detail error: {e}')
        return jsonify({'error': 'server error'}), 500
