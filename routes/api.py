"""API routes for AJAX"""
from flask import Blueprint, jsonify, request
from flask_login import login_required
from models.database import Venue, Location, Reservation
from utils.helpers import get_db

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/venues')
@login_required
def venues():
    db = get_db()
    venues = db.query(Venue).filter_by(is_active=True).all()
    return jsonify([{
        'id': v.id, 'name': v.name,
        'capacity': v.capacity,
        'location': v.location.name if v.location else ''
    } for v in venues])

@api_bp.route('/venues/<int:vid>/bookings')
@login_required
def venue_bookings(vid):
    db = get_db()
    from datetime import datetime
    month_str = request.args.get('month', datetime.now().strftime('%Y-%m'))
    try:
        year, month = map(int, month_str.split('-'))
    except Exception:
        return jsonify([])
    res = (db.query(Reservation)
           .filter(
               Reservation.venue_id == vid,
               Reservation.status.in_(['pending','approved']),
           ).all())
    events = []
    for r in res:
        if r.start_time and r.start_time.year == year and r.start_time.month == month:
            events.append({
                'id':     r.id,
                'title':  r.title,
                'start':  r.start_time.isoformat(),
                'end':    r.end_time.isoformat() if r.end_time else '',
                'status': r.status,
                'color':  {'pending':'#FFC107','approved':'#198754',
                           'rejected':'#DC3545','cancelled':'#6C757D'
                           }.get(r.status,'#0d6efd'),
            })
    return jsonify(events)

@api_bp.route('/stats')
@login_required
def stats():
    db = get_db()
    return jsonify({
        'pending':  db.query(Reservation).filter_by(status='pending').count(),
        'approved': db.query(Reservation).filter_by(status='approved').count(),
        'venues':   db.query(Venue).filter_by(is_active=True).count(),
    })
