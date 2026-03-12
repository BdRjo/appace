"""مسارات القاعات"""
from flask import Blueprint, render_template, abort
from flask_login import login_required
from models.database import Venue, Location
from utils.helpers import get_db, get_permissions

venues_bp = Blueprint('venues', __name__, url_prefix='/venues')

@venues_bp.route('/')
@login_required
def index():
    db    = get_db()
    perms = get_permissions()
    if not perms.can('venues_view'):
        abort(403)
    venues = (db.query(Venue)
              .join(Location, isouter=True)
              .filter(Venue.is_active == True)
              .order_by(Location.name, Venue.name)
              .all())
    return render_template('venues/index.html', venues=venues, perms=perms)

@venues_bp.route('/<int:venue_id>')
@login_required
def detail(venue_id):
    db    = get_db()
    venue = db.query(Venue).get(venue_id)
    if not venue:
        abort(404)
    from models.database import Reservation
    upcoming = (db.query(Reservation)
                .filter(
                    Reservation.venue_id == venue_id,
                    Reservation.status.in_(['pending','approved'])
                )
                .order_by(Reservation.start_time)
                .limit(10).all())
    return render_template('venues/detail.html', venue=venue, upcoming=upcoming)
