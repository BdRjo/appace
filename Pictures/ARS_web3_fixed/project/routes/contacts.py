"""جهات الاتصال"""
import io, csv
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, abort, Response)
from flask_login import login_required, current_user
from models.database import Contact, BookingContact, SystemLog
from utils.helpers import get_db, get_permissions

contacts_bp = Blueprint('contacts', __name__, url_prefix='/contacts')

@contacts_bp.route('/')
@login_required
def index():
    db = get_db(); perms = get_permissions()
    if not perms.can('contacts_view'): abort(403)
    search = request.args.get('q','')
    q = db.query(Contact)
    # Non-admins see only their contacts
    if not perms.is_admin():
        q = q.filter_by(created_by=current_user.id)
    if search:
        q = q.filter((Contact.first_name.ilike(f'%{search}%')) |
                     (Contact.last_name.ilike(f'%{search}%')) |
                     (Contact.email.ilike(f'%{search}%')))
    contacts = q.order_by(Contact.first_name).all()
    return render_template('contacts/index.html', contacts=contacts, search=search, perms=perms)

@contacts_bp.route('/new', methods=['GET','POST'])
@login_required
def new():
    db = get_db(); perms = get_permissions()
    if not perms.can('contacts_add'): abort(403)
    if request.method == 'POST':
        first_name = request.form.get('first_name','').strip()
        last_name  = request.form.get('last_name','').strip()
        email      = request.form.get('email','').strip()
        phone      = request.form.get('phone','').strip()
        if not first_name or not email:
            flash('الاسم والبريد الإلكتروني مطلوبان', 'danger')
            return render_template('contacts/form.html', contact=None, form=request.form)
        c = Contact(first_name=first_name, last_name=last_name,
                    email=email, phone=phone, created_by=current_user.id)
        db.add(c); db.commit()
        flash(f'✅ تمت إضافة جهة الاتصال: {first_name}', 'success')
        return redirect(url_for('contacts.index'))
    return render_template('contacts/form.html', contact=None, form={})

@contacts_bp.route('/<int:cid>/edit', methods=['GET','POST'])
@login_required
def edit(cid):
    db = get_db(); perms = get_permissions()
    if not perms.can('contacts_edit'): abort(403)
    c = db.query(Contact).get(cid)
    if not c: abort(404)
    if c.created_by != current_user.id and not perms.is_admin(): abort(403)
    if request.method == 'POST':
        c.first_name = request.form.get('first_name','').strip()
        c.last_name  = request.form.get('last_name','').strip()
        c.email      = request.form.get('email','').strip()
        c.phone      = request.form.get('phone','').strip()
        db.commit()
        flash('✅ تم تحديث جهة الاتصال', 'success')
        return redirect(url_for('contacts.index'))
    return render_template('contacts/form.html', contact=c, form={})

@contacts_bp.route('/<int:cid>/delete', methods=['POST'])
@login_required
def delete(cid):
    db = get_db(); perms = get_permissions()
    c = db.query(Contact).get(cid)
    if not c: abort(404)
    if c.created_by != current_user.id and not perms.is_admin(): abort(403)
    db.delete(c); db.commit()
    flash('تم حذف جهة الاتصال', 'success')
    return redirect(url_for('contacts.index'))

@contacts_bp.route('/import-csv', methods=['GET','POST'])
@login_required
def import_csv():
    db = get_db(); perms = get_permissions()
    if not perms.can('contacts_add'): abort(403)
    if request.method == 'POST':
        f = request.files.get('csv_file')
        if not f:
            flash('اختر ملف CSV', 'danger')
            return redirect(url_for('contacts.import_csv'))
        try:
            content = f.read()
            # Try multiple encodings
            for enc in ['utf-8-sig','utf-16','cp1256','utf-8']:
                try: text = content.decode(enc); break
                except: pass
            reader = csv.DictReader(io.StringIO(text))
            count = 0
            for row in reader:
                fn = (row.get('first_name') or row.get('الاسم الأول') or '').strip()
                em = (row.get('email') or row.get('البريد الإلكتروني') or '').strip()
                if not fn or not em: continue
                c = Contact(
                    first_name=fn,
                    last_name=(row.get('last_name') or row.get('الاسم الأخير') or '').strip(),
                    email=em,
                    phone=(row.get('phone') or row.get('رقم الهاتف') or '').strip(),
                    created_by=current_user.id
                )
                db.add(c); count += 1
            db.commit()
            flash(f'✅ تم استيراد {count} جهة اتصال', 'success')
        except Exception as e:
            flash(f'خطأ في الاستيراد: {e}', 'danger')
        return redirect(url_for('contacts.index'))
    return render_template('contacts/import.html')

@contacts_bp.route('/export-csv')
@login_required
def export_csv():
    db = get_db(); perms = get_permissions()
    q = db.query(Contact)
    if not perms.is_admin(): q = q.filter_by(created_by=current_user.id)
    contacts = q.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['first_name','last_name','email','phone'])
    for c in contacts:
        writer.writerow([c.first_name, c.last_name or '', c.email, c.phone or ''])
    content = b'\xff\xfe' + output.getvalue().encode('utf-16-le')
    return Response(content, mimetype='text/csv',
                    headers={'Content-Disposition':
                             f'attachment; filename=contacts_{datetime.now().strftime("%Y%m%d")}.csv'})

@contacts_bp.route('/template-csv')
@login_required
def template_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['first_name','last_name','email','phone'])
    writer.writerow(['أحمد','العلي','ahmed@example.com','0501234567'])
    content = b'\xff\xfe' + output.getvalue().encode('utf-16-le')
    return Response(content, mimetype='text/csv',
                    headers={'Content-Disposition':'attachment; filename=contacts_template.csv'})
