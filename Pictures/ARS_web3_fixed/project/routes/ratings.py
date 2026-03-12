"""تقييمات القاعات"""
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, jsonify
from flask_login import login_required, current_user
from models.database import Rating, Reservation, Venue
from utils.helpers import get_db
from sqlalchemy import func

ratings_bp = Blueprint('ratings', __name__, url_prefix='/ratings')

@ratings_bp.route('/venue/<int:venue_id>')
@login_required
def venue_ratings(venue_id):
    db    = get_db()
    venue = db.query(Venue).get(venue_id)
    if not venue: abort(404)
    ratings = (db.query(Rating).filter_by(venue_id=venue_id)
               .order_by(Rating.created_at.desc()).all())
    avg = db.query(func.avg(Rating.rating)).filter_by(venue_id=venue_id).scalar() or 0
    return render_template('ratings/venue.html', venue=venue, ratings=ratings,
                           avg=round(avg, 1))

@ratings_bp.route('/add/<int:res_id>', methods=['GET','POST'])
@login_required
def add(res_id):
    db  = get_db()
    res = db.query(Reservation).get(res_id)
    if not res: abort(404)
    if res.user_id != current_user.id: abort(403)
    if res.status not in ('approved','completed'):
        flash('لا يمكن التقييم إلا للحجوزات المعتمدة', 'warning')
        return redirect(url_for('reservations.detail', res_id=res_id))
    existing = db.query(Rating).filter_by(reservation_id=res_id, user_id=current_user.id).first()
    if existing:
        flash('لقد قيّمت هذا الحجز مسبقاً', 'info')
        return redirect(url_for('reservations.detail', res_id=res_id))
    if request.method == 'POST':
        score   = request.form.get('rating', type=int)
        comment = request.form.get('comment','').strip()
        if not score or score < 1 or score > 5:
            flash('يرجى اختيار تقييم من 1 إلى 5', 'danger')
            return render_template('ratings/form.html', res=res, form=request.form)
        r = Rating(user_id=current_user.id, venue_id=res.venue_id,
                   reservation_id=res_id, rating=score, comment=comment)
        db.add(r); db.commit()
        flash('✅ شكراً على تقييمك!', 'success')
        return redirect(url_for('reservations.detail', res_id=res_id))
    return render_template('ratings/form.html', res=res, form={})
