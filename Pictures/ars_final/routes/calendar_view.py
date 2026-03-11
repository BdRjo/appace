"""التقويم التفاعلي — مطابق لـ v54 مع فلاتر كاملة وألوان"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from models.database import Reservation, Venue, BlockedPeriod, User
from utils.helpers import get_db, get_permissions
from datetime import datetime

calendar_bp = Blueprint('calendar_view', __name__, url_prefix='/calendar')

@calendar_bp.route('/')
@login_required
def index():
    db     = get_db()
    perms  = get_permissions()
    venues = db.query(Venue).filter_by(is_active=True).order_by(Venue.name).all()
    return render_template('calendar/index.html', venues=venues, perms=perms)

@calendar_bp.route('/events')
@login_required
def events():
    db    = get_db()
    perms = get_permissions()
    start    = request.args.get('start','')
    end      = request.args.get('end','')
    venue_id = request.args.get('venue_id','')
    fltr     = request.args.get('filter','all')  # all/mine/approved/pending/rejected/blocked

    try:
        start_dt = datetime.fromisoformat(start[:10]) if start else None
        end_dt   = datetime.fromisoformat(end[:10])   if end   else None
    except:
        start_dt = end_dt = None

    result = []

    # ── Blocked periods ───────────────────────────────────────────────────────
    if fltr in ('all','blocked'):
        bq = db.query(BlockedPeriod)
        if start_dt: bq = bq.filter(BlockedPeriod.end_time   >= start_dt)
        if end_dt:   bq = bq.filter(BlockedPeriod.start_time <= end_dt)
        if venue_id and venue_id.isdigit():
            bq = bq.filter(BlockedPeriod.venue_id == int(venue_id))
        for bp in bq.all():
            result.append({
                'id':    f'bp_{bp.id}',
                'title': f'🚫 {bp.reason or "محجوب"} — {bp.venue.name if bp.venue else ""}',
                'start': bp.start_time.isoformat(),
                'end':   bp.end_time.isoformat(),
                'extendedProps': {'type': 'blocked', 'venue': bp.venue.name if bp.venue else ''},
            })

    # ── Reservations ──────────────────────────────────────────────────────────
    if fltr != 'blocked':
        # Status filter
        if fltr == 'approved':
            statuses = ['approved']
        elif fltr == 'pending':
            statuses = ['pending']
        elif fltr == 'rejected':
            statuses = ['rejected']
        else:
            statuses = ['approved','pending','rejected','cancelled','completed']

        q = db.query(Reservation).filter(Reservation.status.in_(statuses))

        # Mine filter
        if fltr == 'mine':
            q = q.filter(Reservation.user_id == current_user.id)
        elif not perms.is_admin_or_manager():
            # Regular users see own + approved others
            from sqlalchemy import or_
            q = q.filter(or_(
                Reservation.user_id == current_user.id,
                Reservation.status == 'approved'
            ))

        if start_dt: q = q.filter(Reservation.end_time   >= start_dt)
        if end_dt:   q = q.filter(Reservation.start_time <= end_dt)
        if venue_id and venue_id.isdigit():
            q = q.filter(Reservation.venue_id == int(venue_id))

        for r in q.all():
            is_mine = r.user_id == current_user.id
            result.append({
                'id':    r.id,
                'title': f'{r.title} — {r.venue.name if r.venue else ""}',
                'start': r.start_time.isoformat(),
                'end':   r.end_time.isoformat(),
                'url':   f'/reservations/{r.id}',
                'extendedProps': {
                    'status':    r.status,
                    'type':      'reservation',
                    'is_mine':   is_mine,
                    'user_id':   r.user_id,
                    'user_name': r.user.full_name if r.user else '',
                    'venue':     r.venue.name if r.venue else '',
                },
            })

    return jsonify(result)
