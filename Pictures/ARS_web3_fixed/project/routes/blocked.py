"""إدارة الفترات المحظورة — block_period for venue/location/reservation"""
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from models.database import BlockedPeriod, Venue, Location
from utils.helpers import get_db, get_permissions
from datetime import datetime

blocked_bp = Blueprint('blocked', __name__, url_prefix='/blocked')


def _admin_required():
    perms = get_permissions()
    if not perms.is_admin_or_manager():
        abort(403)


# ── General index (all blocked periods) ──────────────────────────────────────
@blocked_bp.route('/')
@login_required
def index():
    _admin_required()
    db      = get_db()
    perms   = get_permissions()
    venue_id   = request.args.get('venue_id', type=int)
    location_id= request.args.get('location_id', type=int)

    q = db.query(BlockedPeriod)
    if venue_id:    q = q.filter(BlockedPeriod.venue_id == venue_id)
    if location_id: q = q.filter(BlockedPeriod.location_id == location_id)
    periods  = q.order_by(BlockedPeriod.start_time.desc()).all()
    venues   = db.query(Venue).filter_by(is_active=True).order_by(Venue.name).all()
    locations= db.query(Location).filter_by(is_active=True).order_by(Location.name).all()
    return render_template('blocked/index.html',
        periods=periods, venues=venues, locations=locations,
        sel_venue=venue_id, sel_location=location_id)


# ── New blocked period ────────────────────────────────────────────────────────
@blocked_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    _admin_required()
    db      = get_db()
    venues  = db.query(Venue).filter_by(is_active=True).order_by(Venue.name).all()
    locations= db.query(Location).filter_by(is_active=True).order_by(Location.name).all()

    if request.method == 'POST':
        venue_id    = request.form.get('venue_id', type=int)
        location_id = request.form.get('location_id', type=int)
        start_str   = request.form.get('start_time', '')
        end_str     = request.form.get('end_time', '')
        reason      = request.form.get('reason', '').strip()

        if not start_str or not end_str:
            flash('يرجى تحديد الفترة الزمنية', 'danger')
            return render_template('blocked/form.html', venues=venues, locations=locations, form=request.form)

        try:
            start_dt = datetime.fromisoformat(start_str)
            end_dt   = datetime.fromisoformat(end_str)
        except ValueError:
            flash('صيغة التاريخ غير صحيحة', 'danger')
            return render_template('blocked/form.html', venues=venues, locations=locations, form=request.form)

        if end_dt <= start_dt:
            flash('تاريخ النهاية يجب أن يكون بعد تاريخ البداية', 'danger')
            return render_template('blocked/form.html', venues=venues, locations=locations, form=request.form)

        bp = BlockedPeriod(
            venue_id    = venue_id,
            location_id = location_id,
            start_time  = start_dt,
            end_time    = end_dt,
            reason      = reason,
            created_by_id = current_user.id,
        )
        db.add(bp)
        db.commit()
        flash('تم حظر الفترة بنجاح', 'success')
        return redirect(url_for('blocked.index'))

    return render_template('blocked/form.html', venues=venues, locations=locations, form={})


# ── Edit blocked period ───────────────────────────────────────────────────────
@blocked_bp.route('/<int:bp_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(bp_id):
    _admin_required()
    db     = get_db()
    bp     = db.query(BlockedPeriod).get(bp_id)
    if not bp: abort(404)
    venues = db.query(Venue).filter_by(is_active=True).order_by(Venue.name).all()
    locations= db.query(Location).filter_by(is_active=True).order_by(Location.name).all()

    if request.method == 'POST':
        start_str = request.form.get('start_time', '')
        end_str   = request.form.get('end_time', '')
        try:
            bp.start_time   = datetime.fromisoformat(start_str)
            bp.end_time     = datetime.fromisoformat(end_str)
            bp.reason       = request.form.get('reason', '').strip()
            bp.venue_id     = request.form.get('venue_id', type=int)
            bp.location_id  = request.form.get('location_id', type=int)
            db.commit()
            flash('تم تحديث الفترة المحظورة', 'success')
            return redirect(url_for('blocked.index'))
        except Exception as e:
            flash(f'خطأ: {e}', 'danger')

    return render_template('blocked/form.html', venues=venues, locations=locations,
                           form=bp, edit_mode=True, bp_id=bp_id)


# ── Delete blocked period ─────────────────────────────────────────────────────
@blocked_bp.route('/<int:bp_id>/delete', methods=['POST'])
@login_required
def delete(bp_id):
    _admin_required()
    db = get_db()
    bp = db.query(BlockedPeriod).get(bp_id)
    if bp:
        db.delete(bp)
        db.commit()
        flash('تم حذف الفترة المحظورة', 'success')
    return redirect(url_for('blocked.index'))


# ── Legacy venue-specific routes (keep for compatibility) ────────────────────
@blocked_bp.route('/venue/<int:venue_id>')
@login_required
def venue_index(venue_id):
    return redirect(url_for('blocked.index', venue_id=venue_id))

@blocked_bp.route('/venue/<int:venue_id>/new', methods=['GET','POST'])
@login_required
def venue_new(venue_id):
    return redirect(url_for('blocked.new'))
