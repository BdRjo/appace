"""
Announcements — Admin broadcast popups for users
Completely isolated blueprint — no changes to existing routes
"""
import base64
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, jsonify, abort, session)
from flask_login import login_required, current_user
from models.database import Announcement, AnnouncementDismissal, User
from utils.helpers import get_db, admin_required, syslog
from utils.flash_helper import flash_msg

announcements_bp = Blueprint('announcements', __name__, url_prefix='/announcements')


# ── Admin: list all announcements ────────────────────────────────────────────
@announcements_bp.route('/')
@login_required
@admin_required
def index():
    db    = get_db()
    items = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
    return render_template('announcements/index.html', items=items)


# ── Admin: new announcement ──────────────────────────────────────────────────
@announcements_bp.route('/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new():
    db    = get_db()
    users = db.query(User).filter_by(is_active=True).order_by(User.full_name).all()

    if request.method == 'POST':
        a = _save_announcement(db, None)
        if a:
            syslog('ANNOUNCEMENT_CREATE', f'إعلان جديد: {a.title_ar}')
            flash_msg('✅ تم إنشاء الإعلان', 'success')
            return redirect(url_for('announcements.index'))

    return render_template('announcements/form.html', ann=None, users=users)


# ── Admin: edit announcement ─────────────────────────────────────────────────
@announcements_bp.route('/<int:ann_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(ann_id):
    db  = get_db()
    ann = db.query(Announcement).get(ann_id)
    if not ann: abort(404)
    users = db.query(User).filter_by(is_active=True).order_by(User.full_name).all()

    if request.method == 'POST':
        _save_announcement(db, ann)
        syslog('ANNOUNCEMENT_EDIT', f'تعديل إعلان: {ann.title_ar}')
        flash_msg('✅ تم تحديث الإعلان', 'success')
        return redirect(url_for('announcements.index'))

    return render_template('announcements/form.html', ann=ann, users=users)


# ── Admin: toggle active ─────────────────────────────────────────────────────
@announcements_bp.route('/<int:ann_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle(ann_id):
    db  = get_db()
    ann = db.query(Announcement).get(ann_id)
    if not ann: abort(404)
    ann.is_active = not ann.is_active
    db.commit()
    return jsonify({'active': ann.is_active})


# ── Admin: delete ────────────────────────────────────────────────────────────
@announcements_bp.route('/<int:ann_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(ann_id):
    db  = get_db()
    ann = db.query(Announcement).get(ann_id)
    if ann:
        db.delete(ann)
        db.commit()
        flash_msg('🗑️ تم حذف الإعلان', 'success')
    return redirect(url_for('announcements.index'))


# ── API: get pending announcements for current user ──────────────────────────
@announcements_bp.route('/api/pending')
@login_required
def api_pending():
    """Returns announcements the user should see. Returns debug info too."""
    db   = get_db()
    now  = datetime.now()
    lang = session.get('lang', 'ar')
    is_admin = hasattr(current_user, 'role') and current_user.role and                current_user.role.name in ('مدير النظام','admin','Admin','مشرف','Manager','manager')

    q = db.query(Announcement).filter_by(is_active=True)
    all_anns = q.all()
    items  = []
    skipped = []

    for ann in all_anns:
        skip_reason = None

        # Date range check — add 4hr buffer for timezone differences (server=UTC, admin=local)
        from datetime import timedelta
        tz_buffer = timedelta(hours=4)  # covers UTC+4 and similar
        if ann.start_date and now < ann.start_date - tz_buffer:
            skip_reason = f'not_started:{ann.start_date}'
        elif ann.end_date and now > ann.end_date.replace(hour=23, minute=59, second=59) + tz_buffer:
            skip_reason = f'expired:{ann.end_date}'
        # Target check
        elif not _user_matches_target(ann, current_user):
            skip_reason = f'target_mismatch:{ann.target}'
        else:
            # Dismissal check (skip for admin so they can preview)
            mode = getattr(ann, 'display_mode', 'once_session')
            if mode == 'once_ever' and not is_admin:
                dismissed = db.query(AnnouncementDismissal).filter_by(
                    announcement_id=ann.id, user_id=current_user.id).first()
                if dismissed:
                    skip_reason = 'dismissed_ever'
            elif mode == 'once_session':
                sess_key = f'ann_seen_{ann.id}'
                if session.get(sess_key):          # applies to everyone incl. admin
                    skip_reason = 'seen_this_session'

        if skip_reason:
            skipped.append({'id': ann.id, 'title': ann.title_ar, 'reason': skip_reason})
            continue

        items.append({
            'id':           ann.id,
            'title':        ann.title_en if lang == 'en' else ann.title_ar,
            'body':         ann.body_en  if lang == 'en' else ann.body_ar or '',
            'media_type':   getattr(ann, 'media_type',   'none')             or 'none',
            'media_url':    getattr(ann, 'media_url',    '')                 or '',
            'media_b64':    getattr(ann, 'media_b64',    '')                 or '',
            'display_mode': getattr(ann, 'display_mode', 'once_session'),
            'modal_size':   getattr(ann, 'modal_size',   'medium'),
            'modal_pos':    getattr(ann, 'modal_pos',    'center'),
            'header_color': getattr(ann, 'header_color', '#0847B0,#0C67EC'),
        })

    resp = {'items': items}
    if is_admin and skipped:
        resp['debug_skipped'] = skipped
    print(f"[ANN] user={current_user.id} active_anns={len(all_anns)} showing={len(items)} skipped={skipped}")
    return jsonify(resp)


# ── API: dismiss announcement ─────────────────────────────────────────────────
@announcements_bp.route('/api/dismiss/<int:ann_id>', methods=['POST'])
@login_required
def api_dismiss(ann_id):
    db  = get_db()
    ann = db.query(Announcement).get(ann_id)
    if not ann:
        return jsonify({'ok': False}), 404

    mode = ann.display_mode

    # Mark session as seen (for once_session)
    session[f'ann_seen_{ann_id}'] = True
    session.modified = True          # force Flask to save session

    # For once_ever: save dismissal to DB
    if mode == 'once_ever':
        existing = db.query(AnnouncementDismissal).filter_by(
            announcement_id=ann_id, user_id=current_user.id).first()
        if not existing:
            db.add(AnnouncementDismissal(
                announcement_id=ann_id,
                user_id=current_user.id
            ))
            db.commit()

    return jsonify({'ok': True})


# ── Helper: save form data to announcement ────────────────────────────────────
def _save_announcement(db, ann):
    f = request.form

    title_ar = f.get('title_ar', '').strip()
    if not title_ar:
        flash_msg('العنوان العربي مطلوب', 'danger')
        return None

    if ann is None:
        ann = Announcement(created_by=current_user.id)
        db.add(ann)

    ann.title_ar     = title_ar
    ann.title_en     = f.get('title_en', '').strip()
    ann.body_ar      = f.get('body_ar', '').strip()
    ann.body_en      = f.get('body_en', '').strip()
    ann.media_type   = f.get('media_type', 'none')
    ann.media_url    = f.get('media_url', '').strip()
    ann.target       = f.get('target', 'all')
    ann.target_roles = ','.join(f.getlist('target_roles'))
    ann.target_users = ','.join(f.getlist('target_users'))
    ann.display_mode = f.get('display_mode', 'once_session')
    ann.modal_size   = f.get('modal_size',   'medium')
    ann.modal_pos    = f.get('modal_pos',    'center')
    ann.header_color = f.get('header_color', '#0847B0,#0C67EC')
    ann.is_active    = f.get('is_active') == 'on'

    # Date fields
    try:
        ann.start_date = datetime.fromisoformat(f.get('start_date')) if f.get('start_date') else None
    except: ann.start_date = None
    try:
        ann.end_date = datetime.fromisoformat(f.get('end_date')) if f.get('end_date') else None
    except: ann.end_date = None

    # Image upload → base64
    img_file = request.files.get('media_image')
    if img_file and img_file.filename:
        data = img_file.read()
        mime = img_file.content_type or 'image/jpeg'
        ann.media_b64  = f'data:{mime};base64,' + base64.b64encode(data).decode()
        ann.media_type = 'image'

    db.commit()
    return ann


# ── Helper: check if user matches announcement target ────────────────────────
def _user_matches_target(ann, user):
    if ann.target == 'all':
        return True
    if ann.target == 'role':
        roles = [r.strip() for r in (ann.target_roles or '').split(',') if r.strip()]
        return bool(user.role and user.role.name in roles)
    if ann.target == 'users':
        uids = [u.strip() for u in (ann.target_users or '').split(',') if u.strip()]
        return str(user.id) in uids
    return True

@announcements_bp.route('/<int:ann_id>/reset-dismissals', methods=['POST'])
@login_required
@admin_required
def reset_dismissals(ann_id):
    """Clear all dismissals so all users see it again"""
    db = get_db()
    db.query(AnnouncementDismissal).filter_by(announcement_id=ann_id).delete()
    db.commit()
    flash_msg('✅ تم إعادة تعيين الإعلان — سيظهر لجميع المستخدمين مرة أخرى', 'success')
    return redirect(url_for('announcements.index'))

@announcements_bp.route('/api/debug')
@login_required
@admin_required
def api_debug():
    """Shows why each announcement is/isn't showing — admin only"""
    db  = get_db()
    now = datetime.now()
    result = []
    for ann in db.query(Announcement).all():
        dismissed = db.query(AnnouncementDismissal).filter_by(
            announcement_id=ann.id, user_id=current_user.id).first()
        sess_key = f'ann_seen_{ann.id}'
        result.append({
            'id':           ann.id,
            'title':        ann.title_ar,
            'is_active':    ann.is_active,
            'display_mode': getattr(ann, 'display_mode', '?'),
            'start_date':   str(ann.start_date) if ann.start_date else None,
            'end_date':     str(ann.end_date)   if ann.end_date   else None,
            'now':          str(now),
            'target':       ann.target,
            'dismissed_in_db': bool(dismissed),
            'seen_in_session': bool(session.get(sess_key)),
            'dismissal_count': db.query(AnnouncementDismissal).filter_by(announcement_id=ann.id).count(),
        })
    return jsonify(result)

@announcements_bp.route('/api/preview/<int:ann_id>')
@login_required
@admin_required
def api_preview(ann_id):
    """Returns full announcement data for admin preview — ignores all dismissal/session checks"""
    db  = get_db()
    ann = db.query(Announcement).get(ann_id)
    if not ann:
        return jsonify({'error': 'not found'}), 404
    lang = session.get('lang', 'ar')
    return jsonify({
        'id':           ann.id,
        'title':        ann.title_en if lang == 'en' else ann.title_ar,
        'body':         ann.body_en  if lang == 'en' else ann.body_ar or '',
        'media_type':   getattr(ann, 'media_type',   'none') or 'none',
        'media_url':    getattr(ann, 'media_url',    '') or '',
        'media_b64':    getattr(ann, 'media_b64',    '') or '',
        'display_mode': getattr(ann, 'display_mode', 'once_session'),
        'modal_size':   getattr(ann, 'modal_size',   'medium'),
        'modal_pos':    getattr(ann, 'modal_pos',    'center'),
        'header_color': getattr(ann, 'header_color', '#0847B0,#0C67EC'),
    })