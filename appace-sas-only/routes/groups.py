"""
Contact Groups / Distribution Lists
"""
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, abort)
from flask_login import login_required, current_user
from utils.flash_helper import flash_msg
from utils.helpers import get_db, get_permissions, syslog
from models.database import ContactGroup, Contact, User

groups_bp = Blueprint('groups', __name__, url_prefix='/groups')


@groups_bp.route('/')
@login_required
def index():
    db = get_db()
    perms = get_permissions()
    q = db.query(ContactGroup).filter_by(is_active=True)
    if not perms.is_admin_or_manager():
        q = q.filter_by(created_by=current_user.id)
    groups = q.order_by(ContactGroup.created_at.desc()).all()
    return render_template('groups/index.html', groups=groups)


@groups_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    db = get_db()
    contacts = db.query(Contact).filter_by(created_by=current_user.id).order_by(Contact.first_name).all()
    users = db.query(User).filter_by(is_active=True).order_by(User.full_name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        contact_ids = request.form.getlist('contact_ids', type=int)
        user_ids = request.form.getlist('user_ids', type=int)

        if not name:
            flash_msg('اسم المجموعة مطلوب', 'danger')
            return render_template('groups/form.html', group=None, contacts=contacts, users=users)

        group = ContactGroup(
            name=name, description=description,
            created_by=current_user.id
        )
        # Add contacts
        for cid in contact_ids:
            c = db.query(Contact).get(cid)
            if c: group.contacts.append(c)
        # Add users
        for uid in user_ids:
            u = db.query(User).get(uid)
            if u: group.users.append(u)

        db.add(group)
        db.commit()
        syslog('CREATE_GROUP', f'مجموعة جديدة: {name}')
        flash_msg(f'✅ تم إنشاء المجموعة: {name}', 'success')
        return redirect(url_for('groups.index'))

    return render_template('groups/form.html', group=None, contacts=contacts, users=users)


@groups_bp.route('/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(group_id):
    db = get_db()
    perms = get_permissions()
    group = db.query(ContactGroup).get(group_id)
    if not group or not group.is_active: abort(404)
    if group.created_by != current_user.id and not perms.is_admin_or_manager():
        abort(403)

    contacts = db.query(Contact).filter_by(created_by=current_user.id).order_by(Contact.first_name).all()
    users = db.query(User).filter_by(is_active=True).order_by(User.full_name).all()

    if request.method == 'POST':
        group.name = request.form.get('name', '').strip()
        group.description = request.form.get('description', '').strip()

        contact_ids = request.form.getlist('contact_ids', type=int)
        user_ids = request.form.getlist('user_ids', type=int)

        group.contacts = [db.query(Contact).get(cid) for cid in contact_ids if db.query(Contact).get(cid)]
        group.users    = [db.query(User).get(uid) for uid in user_ids if db.query(User).get(uid)]

        db.commit()
        syslog('EDIT_GROUP', f'تعديل مجموعة: {group.name}')
        flash_msg('✅ تم حفظ التعديلات', 'success')
        return redirect(url_for('groups.index'))

    return render_template('groups/form.html', group=group, contacts=contacts, users=users)


@groups_bp.route('/<int:group_id>/delete', methods=['POST'])
@login_required
def delete(group_id):
    db = get_db()
    perms = get_permissions()
    group = db.query(ContactGroup).get(group_id)
    if not group: abort(404)
    if group.created_by != current_user.id and not perms.is_admin_or_manager():
        abort(403)
    group.is_active = False
    db.commit()
    flash_msg(f'تم حذف المجموعة: {group.name}', 'success')
    return redirect(url_for('groups.index'))


@groups_bp.route('/api/members/<int:group_id>')
@login_required
def api_members(group_id):
    """API: return group members as JSON for dynamic loading"""
    from flask import jsonify
    db = get_db()
    group = db.query(ContactGroup).get(group_id)
    if not group: return jsonify({'contacts': [], 'users': []})
    return jsonify({
        'contacts': [{'id': c.id, 'name': f'{c.first_name} {c.last_name or ""}', 'email': c.email} for c in group.contacts],
        'users':    [{'id': u.id, 'name': u.full_name, 'email': u.email} for u in group.users],
    })


@groups_bp.route('/import-csv', methods=['GET', 'POST'])
@login_required
def import_csv():
    """Import groups from CSV: group_name, contact_emails (comma-separated), user_usernames (comma-separated)"""
    import csv, io
    db = get_db()
    if request.method == 'POST':
        f = request.files.get('file')
        if not f:
            flash_msg('يرجى رفع ملف CSV', 'danger')
            return redirect(url_for('groups.import_csv'))
        content = f.stream.read().decode('utf-8-sig')
        reader  = csv.DictReader(io.StringIO(content))
        created = 0; errors = []
        for row in reader:
            name = (row.get('group_name') or row.get('name') or '').strip()
            if not name: continue
            desc = (row.get('description') or '').strip()
            grp = ContactGroup(name=name, description=desc, created_by=current_user.id)
            # Add contacts by email
            emails = [e.strip() for e in (row.get('contact_emails') or '').split(',') if e.strip()]
            for email in emails:
                c = db.query(Contact).filter_by(email=email).first()
                if c: grp.contacts.append(c)
            # Add users by username
            unames = [u.strip() for u in (row.get('user_usernames') or '').split(',') if u.strip()]
            for uname in unames:
                u = db.query(User).filter_by(username=uname).first()
                if u: grp.users.append(u)
            db.add(grp)
            created += 1
        db.commit()
        flash_msg(f'✅ تم استيراد {created} مجموعة', 'success')
        return redirect(url_for('groups.index'))
    return render_template('groups/import.html')
