"""قوائم المهام — Task Tracker مع مشاركة وتعليقات وإشعارات"""
from utils.flash_helper import flash_msg
from flask import (Blueprint, render_template, redirect, url_for,
                   request, abort, jsonify, session)
from flask_login import login_required, current_user
from models.database import (Checklist, ChecklistItem, ChecklistShare,
                              ChecklistComment, Notification, Reservation, User)
from utils.helpers import get_db, get_permissions
from datetime import datetime

checklists_bp = Blueprint('checklists', __name__, url_prefix='/checklists')


def _push(db, user_id, title_ar, body_ar='', link=None, title_en=None, body_en=None):
    """Create bilingual local notification for a user"""
    from models.database import User as _User
    try:
        u = db.query(_User).get(user_id)
        lang = getattr(u, 'language', 'ar') if u else 'ar'
        title = (title_en or title_ar) if lang == 'en' else title_ar
        body  = (body_en  or body_ar)  if lang == 'en' else body_ar
        db.add(Notification(user_id=user_id, title=title, body=body, link=link))
        db.commit()
    except Exception:
        pass


def _can_access(cl, db, write=False):
    """Check if current user can access this checklist"""
    if cl.created_by_id == current_user.id:
        return True
    perms = get_permissions()
    if perms.is_admin():
        return True
    share = db.query(ChecklistShare).filter_by(
        checklist_id=cl.id, user_id=current_user.id).first()
    if not share:
        return cl.is_public and not write
    if write:
        return share.permission == 'edit'
    return True


@checklists_bp.route('/')
@login_required
def index():
    db = get_db(); perms = get_permissions()
    from sqlalchemy import or_
    # My checklists + shared with me + public
    my_ids = [s.checklist_id for s in db.query(ChecklistShare).filter_by(user_id=current_user.id).all()]
    q = db.query(Checklist).filter_by(is_template=True).filter(
        or_(
            Checklist.created_by_id == current_user.id,
            Checklist.id.in_(my_ids),
            Checklist.is_public == True
        )
    )
    if perms.is_admin():
        q = db.query(Checklist).filter_by(is_template=True)
    checklists = q.order_by(Checklist.created_at.desc()).all()
    all_users = db.query(User).filter_by(is_active=True).order_by(User.full_name).all()
    return render_template('checklists/index.html', checklists=checklists,
                           perms=perms, all_users=all_users)


@checklists_bp.route('/<int:cl_id>')
@login_required
def detail(cl_id):
    db = get_db(); perms = get_permissions()
    cl = db.query(Checklist).get(cl_id)
    if not cl: abort(404)
    if not _can_access(cl, db): abort(403)
    can_edit = _can_access(cl, db, write=True)
    items = sorted(cl.items, key=lambda x: (x.order_index, x.id))
    done  = sum(1 for i in items if i.is_checked)
    comments = db.query(ChecklistComment).filter_by(
        checklist_id=cl_id, item_id=None).order_by(ChecklistComment.created_at).all()
    shares = db.query(ChecklistShare).filter_by(checklist_id=cl_id).all()
    all_users = db.query(User).filter_by(is_active=True).order_by(User.full_name).all()
    shared_user_ids = {s.user_id for s in shares}
    from datetime import timedelta
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return render_template('checklists/detail.html',
                           cl=cl, items=items, done=done, total=len(items),
                           perms=perms, can_edit=can_edit,
                           comments=comments, shares=shares,
                           all_users=[u for u in all_users if u.id != current_user.id and u.id not in shared_user_ids],
                           today=today, today_plus2=today + timedelta(days=2))


@checklists_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    db = get_db(); perms = get_permissions()
    if not perms.can('checklists_add'): abort(403)
    if request.method == 'POST':
        name   = request.form.get('name', '').strip()
        desc   = request.form.get('description', '').strip()
        public = request.form.get('is_public') == 'on'
        color  = request.form.get('color', '#0C67EC')
        emoji  = request.form.get('emoji', '📋')
        items  = request.form.getlist('items[]')
        notes  = request.form.getlist('notes[]')
        prios  = request.form.getlist('priorities[]')
        dues   = request.form.getlist('due_dates[]')
        if not name:
            flash_msg('اسم القائمة مطلوب', 'danger')
            return render_template('checklists/form.html', cl=None, form=request.form)
        cl = Checklist(name=name, description=desc, is_template=True,
                       is_public=public, created_by_id=current_user.id,
                       color=color, emoji=emoji)
        db.add(cl); db.flush()
        for i, item_text in enumerate(items):
            if item_text.strip():
                due = None
                try:
                    if dues[i]: due = datetime.fromisoformat(dues[i])
                except: pass
                db.add(ChecklistItem(
                    checklist_id=cl.id, content=item_text.strip(),
                    note=notes[i] if i < len(notes) else '',
                    priority=int(prios[i]) if i < len(prios) and prios[i].isdigit() else 0,
                    due_date=due, order_index=i
                ))
        db.commit()
        flash_msg(f'✅ تمت إضافة القائمة: {name}', 'success')
        return redirect(url_for('checklists.detail', cl_id=cl.id))
    return render_template('checklists/form.html', cl=None, form={})


@checklists_bp.route('/<int:cl_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(cl_id):
    db = get_db(); perms = get_permissions()
    cl = db.query(Checklist).get(cl_id)
    if not cl: abort(404)
    if not _can_access(cl, db, write=True): abort(403)
    if request.method == 'POST':
        cl.name        = request.form.get('name', '').strip()
        cl.description = request.form.get('description', '').strip()
        cl.is_public   = request.form.get('is_public') == 'on'
        cl.color       = request.form.get('color', '#0C67EC')
        cl.emoji       = request.form.get('emoji', '📋')
        for item in cl.items: db.delete(item)
        db.flush()
        items = request.form.getlist('items[]')
        notes = request.form.getlist('notes[]')
        prios = request.form.getlist('priorities[]')
        dues  = request.form.getlist('due_dates[]')
        for i, item_text in enumerate(items):
            if item_text.strip():
                due = None
                try:
                    if dues[i]: due = datetime.fromisoformat(dues[i])
                except: pass
                db.add(ChecklistItem(
                    checklist_id=cl.id, content=item_text.strip(),
                    note=notes[i] if i < len(notes) else '',
                    priority=int(prios[i]) if i < len(prios) and prios[i].isdigit() else 0,
                    due_date=due, order_index=i
                ))
        db.commit()
        flash_msg('✅ تم تحديث القائمة', 'success')
        return redirect(url_for('checklists.detail', cl_id=cl.id))
    return render_template('checklists/form.html', cl=cl, form={})


@checklists_bp.route('/<int:cl_id>/delete', methods=['POST'])
@login_required
def delete(cl_id):
    db = get_db(); perms = get_permissions()
    cl = db.query(Checklist).get(cl_id)
    if not cl: abort(404)
    if cl.created_by_id != current_user.id and not perms.is_admin(): abort(403)
    db.delete(cl); db.commit()
    flash_msg('تم حذف القائمة', 'success')
    return redirect(url_for('checklists.index'))


# ── AJAX: toggle item ──────────────────────────────────────────────────────────
@checklists_bp.route('/item/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_item(item_id):
    db   = get_db()
    item = db.query(ChecklistItem).get(item_id)
    if not item: return jsonify({'ok': False, 'error': 'not found'}), 404
    # Check access
    if item.checklist_id:
        cl = db.query(Checklist).get(item.checklist_id)
        if cl and not _can_access(cl, db, write=True):
            return jsonify({'ok': False, 'error': 'forbidden'}), 403
    try:
        item.is_checked    = not item.is_checked
        item.checked_at    = datetime.now() if item.is_checked else None
        item.checked_by_id = current_user.id if item.is_checked else None
        db.commit()
        if item.checklist_id:
            cl    = db.query(Checklist).get(item.checklist_id)
            total = len(cl.items)
            done  = sum(1 for i in cl.items if i.is_checked)
        else:
            total = done = 0
        return jsonify({'ok': True, 'checked': item.is_checked, 'done': done, 'total': total})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── AJAX: add comment ──────────────────────────────────────────────────────────
@checklists_bp.route('/<int:cl_id>/comment', methods=['POST'])
@login_required
def add_comment(cl_id):
    db = get_db()
    cl = db.query(Checklist).get(cl_id)
    if not cl or not _can_access(cl, db): return jsonify({'ok': False}), 403
    data    = request.json or {}
    content = data.get('content', '').strip()
    item_id = data.get('item_id')
    if not content: return jsonify({'ok': False, 'error': 'empty'})
    c = ChecklistComment(checklist_id=cl_id, user_id=current_user.id,
                         content=content, item_id=item_id or None)
    db.add(c); db.commit()
    # Push local notification to owner
    if cl.created_by_id != current_user.id:
        _push(db, cl.created_by_id,
              f'💬 New comment on: {cl.name}',
              f'{current_user.full_name or current_user.username}: {content[:80]}',
              f'/checklists/{cl_id}')
    # Also notify shared users
    for s in db.query(ChecklistShare).filter_by(checklist_id=cl_id).all():
        if s.user_id != current_user.id:
            _push(db, s.user_id,
                  f'💬 New comment on: {cl.name}',
                  f'{current_user.full_name or current_user.username}: {content[:80]}',
                  f'/checklists/{cl_id}')
    # Send email notification to owner if not the commenter
    if cl.created_by_id != current_user.id:
        try:
            owner = db.query(User).get(cl.created_by_id)
            if owner and owner.email:
                from utils.email_helper import _send, _html_wrapper
                body = _html_wrapper(f'''
                <p style="color:#4a5568">مرحباً {owner.full_name or owner.username}،</p>
                <p style="color:#4a5568">أضاف <strong>{current_user.full_name or current_user.username}</strong> تعليقاً على قائمتك <strong>{cl.name}</strong>:</p>
                <div style="background:#f7f9fc;border-right:4px solid #0C67EC;padding:12px 16px;border-radius:8px;margin:16px 0;color:#2d3748">{content}</div>
                <a href="/checklists/{cl_id}" style="background:#0C67EC;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;display:inline-block">عرض القائمة</a>
                ''', 'تعليق جديد')
                _send(owner.email, owner.full_name or '', f'💬 تعليق جديد على {cl.name}', body, f'تعليق: {content}')
        except: pass
    return jsonify({
        'ok': True, 'id': c.id,
        'content': c.content,
        'user': current_user.full_name or current_user.username,
        'avatar': (current_user.full_name or current_user.username)[:1].upper(),
        'time': c.created_at.strftime('%Y-%m-%d %H:%M')
    })


# ── AJAX: share checklist ──────────────────────────────────────────────────────
@checklists_bp.route('/<int:cl_id>/share', methods=['POST'])
@login_required
def share(cl_id):
    db = get_db()
    cl = db.query(Checklist).get(cl_id)
    if not cl: return jsonify({'ok': False}), 404
    if cl.created_by_id != current_user.id and not get_permissions().is_admin():
        return jsonify({'ok': False, 'error': 'forbidden'}), 403
    data       = request.json or {}
    user_id    = data.get('user_id')
    permission = data.get('permission', 'view')
    if not user_id: return jsonify({'ok': False, 'error': 'no user'})
    target = db.query(User).get(user_id)
    if not target: return jsonify({'ok': False, 'error': 'user not found'})
    existing = db.query(ChecklistShare).filter_by(checklist_id=cl_id, user_id=user_id).first()
    if existing:
        existing.permission = permission
    else:
        db.add(ChecklistShare(checklist_id=cl_id, user_id=user_id, permission=permission))
    db.commit()
    # Push local notification
    perm_label = 'edit' if permission == 'edit' else 'view'
    _push(db, user_id,
          f'📋 Shared checklist: {cl.name}' if True else f'📋 تمت مشاركة قائمة: {cl.name}',
          f'{current_user.full_name or current_user.username} shared "{cl.name}" with you ({perm_label})',
          f'/checklists/{cl_id}')
    # Send notification email
    try:
        if target.email:
            from utils.email_helper import _send, _html_wrapper
            perm_label = 'تعديل' if permission == 'edit' else 'عرض'
            body = _html_wrapper(f'''
            <p style="color:#4a5568">مرحباً {target.full_name or target.username}،</p>
            <p style="color:#4a5568">شارك معك <strong>{current_user.full_name or current_user.username}</strong> قائمة المهام <strong>{cl.name}</strong> بصلاحية <strong>{perm_label}</strong>.</p>
            <a href="/checklists/{cl_id}" style="background:#0C67EC;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;display:inline-block">عرض القائمة</a>
            ''', 'تمت مشاركة قائمة مهام')
            _send(target.email, target.full_name or '', f'📋 تمت مشاركة قائمة: {cl.name}', body, f'تمت مشاركة قائمة {cl.name} معك')
    except: pass
    return jsonify({'ok': True, 'user': target.full_name or target.username,
                    'user_id': target.id, 'permission': permission,
                    'avatar': (target.full_name or target.username)[:1].upper()})


# ── AJAX: remove share ────────────────────────────────────────────────────────
@checklists_bp.route('/<int:cl_id>/unshare/<int:user_id>', methods=['POST'])
@login_required
def unshare(cl_id, user_id):
    db = get_db()
    cl = db.query(Checklist).get(cl_id)
    if not cl: return jsonify({'ok': False}), 404
    if cl.created_by_id != current_user.id and not get_permissions().is_admin():
        return jsonify({'ok': False}), 403
    share = db.query(ChecklistShare).filter_by(checklist_id=cl_id, user_id=user_id).first()
    if share: db.delete(share); db.commit()
    return jsonify({'ok': True})


# ── AJAX: add quick item ──────────────────────────────────────────────────────
@checklists_bp.route('/<int:cl_id>/add-item', methods=['POST'])
@login_required
def add_item(cl_id):
    db = get_db()
    cl = db.query(Checklist).get(cl_id)
    if not cl or not _can_access(cl, db, write=True): return jsonify({'ok': False}), 403
    data    = request.json or {}
    content = data.get('content', '').strip()
    if not content: return jsonify({'ok': False, 'error': 'empty'})
    note     = data.get('note', '').strip() or None
    priority = int(data.get('priority', 0) or 0)
    due_raw  = data.get('due_date', '').strip()
    due_date = None
    if due_raw:
        try: due_date = datetime.strptime(due_raw, '%Y-%m-%d')
        except: pass
    count = db.query(ChecklistItem).filter_by(checklist_id=cl_id).count()
    item  = ChecklistItem(checklist_id=cl_id, content=content, note=note,
                          priority=priority, due_date=due_date, order_index=count)
    db.add(item); db.commit()
    # Notify shared editors
    try:
        shares = db.query(ChecklistShare).filter_by(checklist_id=cl_id, permission='edit').all()
        for s in shares:
            u = db.query(User).get(s.user_id)
            if u and u.email and u.id != current_user.id:
                from utils.email_helper import _send, _html_wrapper
                body = _html_wrapper(f'<p style="color:#4a5568">أضاف <strong>{current_user.full_name}</strong> مهمة جديدة في <strong>{cl.name}</strong>: <strong>{content}</strong></p><a href="/checklists/{cl_id}" style="background:#0C67EC;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;display:inline-block">عرض</a>', 'مهمة جديدة')
                _send(u.email, u.full_name or '', f'➕ مهمة جديدة في {cl.name}', body, f'مهمة: {content}')
    except: pass
    return jsonify({'ok': True, 'id': item.id, 'content': item.content,
                    'note': item.note, 'priority': item.priority,
                    'due_date': item.due_date.strftime('%Y-%m-%d') if item.due_date else None})


# ── AJAX: delete item ─────────────────────────────────────────────────────────
@checklists_bp.route('/item/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    db   = get_db()
    item = db.query(ChecklistItem).get(item_id)
    if not item: return jsonify({'ok': False}), 404
    if item.checklist_id:
        cl = db.query(Checklist).get(item.checklist_id)
        if cl and not _can_access(cl, db, write=True): return jsonify({'ok': False}), 403
    res_id = item.reservation_id
    db.delete(item); db.commit()
    if request.is_json: return jsonify({'ok': True})
    if res_id: return redirect(url_for('checklists.reservation_checklist', res_id=res_id))
    return jsonify({'ok': True})


# ── AJAX toggle for reservation checklist ─────────────────────────────────────
@checklists_bp.route('/res/<int:res_id>/toggle/<int:item_id>', methods=['POST'])
@login_required
def res_toggle_item(res_id, item_id):
    db   = get_db()
    item = db.query(ChecklistItem).get(item_id)
    if not item: return jsonify({'ok': False}), 404
    try:
        item.is_checked    = not item.is_checked
        item.checked_at    = datetime.now() if item.is_checked else None
        item.checked_by_id = current_user.id if item.is_checked else None
        db.commit()
        return jsonify({'ok': True, 'checked': item.is_checked})
    except Exception as e:
        db.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Upcoming items ────────────────────────────────────────────────────────────
@checklists_bp.route('/upcoming')
@login_required
def upcoming():
    from datetime import timedelta
    from sqlalchemy import or_
    db = get_db()
    limit = datetime.now() + timedelta(days=7)
    shared_ids = [s.checklist_id for s in db.query(ChecklistShare).filter_by(user_id=current_user.id).all()]
    cl_ids = [cl.id for cl in db.query(Checklist).filter(
        or_(Checklist.created_by_id == current_user.id, Checklist.id.in_(shared_ids))
    ).filter_by(is_template=True).all()]
    if not cl_ids: return jsonify({'items': []})
    items = db.query(ChecklistItem).filter(
        ChecklistItem.checklist_id.in_(cl_ids),
        ChecklistItem.is_checked == False,
        ChecklistItem.due_date != None,
        ChecklistItem.due_date <= limit
    ).order_by(ChecklistItem.due_date).limit(10).all()
    result = [{'id': i.id, 'content': i.content,
               'due': i.due_date.strftime('%Y-%m-%d'),
               'overdue': i.due_date < datetime.now(),
               'cl_id': i.checklist_id,
               'cl_name': i.checklist.name if i.checklist else '',
               'priority': i.priority} for i in items]
    return jsonify({'items': result})


# ── Sticky notes ──────────────────────────────────────────────────────────────
@checklists_bp.route('/sticky-notes', methods=['GET', 'POST'])
@login_required
def sticky_notes():
    from models.database import SystemLog
    db = get_db()
    if request.method == 'POST':
        content  = request.json.get('content', '')
        existing = db.query(SystemLog).filter_by(action='STICKY_NOTES', user_id=current_user.id).first()
        if existing: existing.description = content
        else: db.add(SystemLog(action='STICKY_NOTES', description=content, user_id=current_user.id, level='info'))
        db.commit()
        return jsonify({'ok': True})
    row = db.query(SystemLog).filter_by(action='STICKY_NOTES', user_id=current_user.id).first()
    return jsonify({'content': row.description if row else ''})


# ── Reservation checklist ─────────────────────────────────────────────────────
@checklists_bp.route('/reservation/<int:res_id>', methods=['GET', 'POST'])
@login_required
def reservation_checklist(res_id):
    db  = get_db(); perms = get_permissions()
    res = db.query(Reservation).get(res_id)
    if not res: abort(404)
    if res.user_id != current_user.id and not perms.can('reservations_view'): abort(403)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_item':
            content = request.form.get('content', '').strip()
            priority = request.form.get('priority', 1, type=int)
            due_raw  = request.form.get('due_date', '').strip()
            due_date = None
            if due_raw:
                try: due_date = datetime.strptime(due_raw, '%Y-%m-%d')
                except: pass
            if content:
                db.add(ChecklistItem(reservation_id=res_id, content=content,
                                     priority=priority, due_date=due_date))
                db.commit()
        elif action == 'toggle':
            item_id = request.form.get('item_id', type=int)
            item = db.query(ChecklistItem).get(item_id)
            if item and item.reservation_id == res_id:
                item.is_checked = not item.is_checked
                if item.is_checked:
                    item.checked_at    = datetime.now()
                    item.checked_by_id = current_user.id
                db.commit()
        elif action == 'apply_template':
            tmpl_id = request.form.get('template_id', type=int)
            tmpl = db.query(Checklist).get(tmpl_id)
            if tmpl:
                for t_item in tmpl.items:
                    db.add(ChecklistItem(reservation_id=res_id, content=t_item.content,
                                         order_index=t_item.order_index))
                db.commit()
        return redirect(url_for('checklists.reservation_checklist', res_id=res_id))
    items     = db.query(ChecklistItem).filter_by(reservation_id=res_id).order_by(ChecklistItem.order_index).all()
    templates = db.query(Checklist).filter_by(is_template=True, is_public=True).all()
    done = sum(1 for i in items if i.is_checked)
    from datetime import date as _d
    return render_template('checklists/reservation.html',
                           res=res, items=items, templates=templates,
                           done=done, total=len(items), today=_d.today())
