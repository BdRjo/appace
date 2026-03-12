"""قوائم المهام — مساحة شخصية عصرية"""
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, abort, jsonify)
from flask_login import login_required, current_user
from models.database import Checklist, ChecklistItem, Reservation
from utils.helpers import get_db, get_permissions
from datetime import datetime

checklists_bp = Blueprint('checklists', __name__, url_prefix='/checklists')


@checklists_bp.route('/')
@login_required
def index():
    db = get_db(); perms = get_permissions()
    if not perms.can('checklists_view'): abort(403)
    q = db.query(Checklist).filter_by(is_template=True)
    if not perms.is_admin():
        from sqlalchemy import or_
        q = q.filter(or_(Checklist.is_public==True, Checklist.created_by_id==current_user.id))
    checklists = q.order_by(Checklist.created_at.desc()).all()
    return render_template('checklists/index.html', checklists=checklists, perms=perms)


@checklists_bp.route('/<int:cl_id>')
@login_required
def detail(cl_id):
    db = get_db(); perms = get_permissions()
    cl = db.query(Checklist).get(cl_id)
    if not cl: abort(404)
    if not cl.is_public and cl.created_by_id != current_user.id and not perms.is_admin():
        abort(403)
    items = sorted(cl.items, key=lambda x: (x.order_index, x.id))
    done  = sum(1 for i in items if i.is_checked)
    from datetime import datetime, timedelta
    today = datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
    return render_template('checklists/detail.html', cl=cl, items=items,
                           done=done, total=len(items), perms=perms,
                           today=today, today_plus2=today+timedelta(days=2))


@checklists_bp.route('/new', methods=['GET','POST'])
@login_required
def new():
    db = get_db(); perms = get_permissions()
    if not perms.can('checklists_add'): abort(403)
    if request.method == 'POST':
        name   = request.form.get('name','').strip()
        desc   = request.form.get('description','').strip()
        public = request.form.get('is_public') == 'on'
        color  = request.form.get('color','#1A555C')
        emoji  = request.form.get('emoji','📋')
        items  = request.form.getlist('items[]')
        notes  = request.form.getlist('notes[]')
        prios  = request.form.getlist('priorities[]')
        dues   = request.form.getlist('due_dates[]')
        if not name:
            flash('اسم القائمة مطلوب', 'danger')
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
        flash(f'✅ تمت إضافة القائمة: {name}', 'success')
        return redirect(url_for('checklists.detail', cl_id=cl.id))
    return render_template('checklists/form.html', cl=None, form={})


@checklists_bp.route('/<int:cl_id>/edit', methods=['GET','POST'])
@login_required
def edit(cl_id):
    db = get_db(); perms = get_permissions()
    cl = db.query(Checklist).get(cl_id)
    if not cl: abort(404)
    if not perms.can('checklists_edit') and cl.created_by_id != current_user.id: abort(403)
    if request.method == 'POST':
        cl.name        = request.form.get('name','').strip()
        cl.description = request.form.get('description','').strip()
        cl.is_public   = request.form.get('is_public') == 'on'
        cl.color       = request.form.get('color','#1A555C')
        cl.emoji       = request.form.get('emoji','📋')
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
        flash('✅ تم تحديث القائمة', 'success')
        return redirect(url_for('checklists.detail', cl_id=cl.id))
    return render_template('checklists/form.html', cl=cl, form={})


@checklists_bp.route('/<int:cl_id>/delete', methods=['POST'])
@login_required
def delete(cl_id):
    db = get_db(); perms = get_permissions()
    cl = db.query(Checklist).get(cl_id)
    if not cl: abort(404)
    if not perms.can('checklists_delete') and cl.created_by_id != current_user.id: abort(403)
    db.delete(cl); db.commit()
    flash('تم حذف القائمة', 'success')
    return redirect(url_for('checklists.index'))


# ── AJAX: toggle item ─────────────────────────────────────────────────────────
@checklists_bp.route('/item/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_item(item_id):
    db   = get_db()
    item = db.query(ChecklistItem).get(item_id)
    if not item: return jsonify({'ok': False}), 404
    item.is_checked = not item.is_checked
    item.checked_at = datetime.now() if item.is_checked else None
    item.checked_by_id = current_user.id if item.is_checked else None
    db.commit()
    # calc progress
    if item.checklist_id:
        cl = db.query(Checklist).get(item.checklist_id)
        total = len(cl.items); done = sum(1 for i in cl.items if i.is_checked)
    else:
        total = done = 0
    return jsonify({'ok': True, 'checked': item.is_checked, 'done': done, 'total': total})


# ── AJAX: add quick item ──────────────────────────────────────────────────────
@checklists_bp.route('/<int:cl_id>/add-item', methods=['POST'])
@login_required
def add_item(cl_id):
    db = get_db()
    cl = db.query(Checklist).get(cl_id)
    if not cl: return jsonify({'ok': False}), 404
    content = request.json.get('content','').strip()
    if not content: return jsonify({'ok': False, 'error': 'empty'})
    count = db.query(ChecklistItem).filter_by(checklist_id=cl_id).count()
    item  = ChecklistItem(checklist_id=cl_id, content=content, order_index=count)
    db.add(item); db.commit()
    return jsonify({'ok': True, 'id': item.id, 'content': item.content})


# ── AJAX: delete item ─────────────────────────────────────────────────────────
@checklists_bp.route('/item/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    db   = get_db()
    item = db.query(ChecklistItem).get(item_id)
    if not item: return jsonify({'ok': False}), 404
    cl_id = item.checklist_id
    res_id = item.reservation_id
    db.delete(item); db.commit()
    if res_id:
        return redirect(url_for('checklists.reservation_checklist', res_id=res_id))
    return jsonify({'ok': True})


# ── AJAX: save sticky notes ──────────────────────────────────────────────────
@checklists_bp.route('/sticky-notes', methods=['GET','POST'])
@login_required
def sticky_notes():
    """Save/load personal sticky notes (stored in SystemLog as hack)"""
    from models.database import SystemLog
    db = get_db()
    if request.method == 'POST':
        content = request.json.get('content','')
        # Store as special system log entry (action = STICKY_NOTES)
        existing = db.query(SystemLog).filter_by(
            action='STICKY_NOTES', user_id=current_user.id).first()
        if existing:
            existing.description = content
        else:
            db.add(SystemLog(action='STICKY_NOTES', description=content,
                             user_id=current_user.id, level='info'))
        db.commit()
        return jsonify({'ok': True})
    else:
        row = db.query(SystemLog).filter_by(
            action='STICKY_NOTES', user_id=current_user.id).first()
        return jsonify({'content': row.description if row else ''})


# ── AJAX: get upcoming items ──────────────────────────────────────────────────
@checklists_bp.route('/upcoming')
@login_required
def upcoming():
    from datetime import datetime, timedelta
    from sqlalchemy import or_
    db = get_db()
    limit = datetime.now() + timedelta(days=7)
    # Get all checklists owned by user
    my_lists = db.query(Checklist).filter_by(
        created_by_id=current_user.id, is_template=True).all()
    cl_ids = [cl.id for cl in my_lists]
    if not cl_ids:
        return jsonify({'items': []})
    from models.database import ChecklistItem
    items = db.query(ChecklistItem).filter(
        ChecklistItem.checklist_id.in_(cl_ids),
        ChecklistItem.is_checked == False,
        ChecklistItem.due_date != None,
        ChecklistItem.due_date <= limit
    ).order_by(ChecklistItem.due_date).limit(10).all()
    result = []
    for i in items:
        overdue = i.due_date < datetime.now()
        result.append({
            'id': i.id,
            'content': i.content,
            'due': i.due_date.strftime('%Y-%m-%d'),
            'overdue': overdue,
            'cl_id': i.checklist_id,
            'cl_name': i.checklist.name if i.checklist else '',
            'priority': i.priority,
        })
    return jsonify({'items': result})


# ── Reservation checklist ─────────────────────────────────────────────────────
@checklists_bp.route('/reservation/<int:res_id>', methods=['GET','POST'])
@login_required
def reservation_checklist(res_id):
    db  = get_db(); perms = get_permissions()
    res = db.query(Reservation).get(res_id)
    if not res: abort(404)
    if res.user_id != current_user.id and not perms.can('reservations_view'): abort(403)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_item':
            content = request.form.get('content','').strip()
            if content:
                db.add(ChecklistItem(reservation_id=res_id, content=content))
                db.commit()
        elif action == 'toggle':
            item_id = request.form.get('item_id', type=int)
            item = db.query(ChecklistItem).get(item_id)
            if item and item.reservation_id == res_id:
                item.is_checked = not item.is_checked
                if item.is_checked:
                    item.checked_at = datetime.now()
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
    done  = sum(1 for i in items if i.is_checked)
    return render_template('checklists/reservation.html',
                           res=res, items=items, templates=templates,
                           done=done, total=len(items))
