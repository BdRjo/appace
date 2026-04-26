"""جهات الاتصال"""
import io, csv
from datetime import datetime
from utils.flash_helper import flash_msg
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, abort, Response, send_file)
from flask_login import login_required, current_user
from models.database import Contact, BookingContact, SystemLog
from utils.helpers import get_db, get_permissions

contacts_bp = Blueprint('contacts', __name__, url_prefix='/contacts')

@contacts_bp.route('/')
@login_required
def index():
    db = get_db(); perms = get_permissions()
    if not perms.can('contacts_view') and not perms.is_regular_user(): abort(403)
    search = request.args.get('q','')
    q = db.query(Contact)
    if not perms.is_admin():
        q = q.filter_by(created_by=current_user.id)
    if search:
        q = q.filter(
            (Contact.first_name.ilike(f'%{search}%')) |
            (Contact.last_name.ilike(f'%{search}%')) |
            (Contact.email.ilike(f'%{search}%')) |
            (Contact.company.ilike(f'%{search}%')) |
            (Contact.job_title.ilike(f'%{search}%'))
        )
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
        job_title  = request.form.get('job_title','').strip()
        company    = request.form.get('company','').strip()
        notes      = request.form.get('notes','').strip()
        if not first_name or not email:
            flash_msg('الاسم والبريد الإلكتروني مطلوبان', 'danger')
            return render_template('contacts/form.html', contact=None, form=request.form)
        department = request.form.get('department','').strip()
        c = Contact(first_name=first_name, last_name=last_name,
                    email=email, phone=phone,
                    job_title=job_title or None, company=company or None,
                    department=department or None, notes=notes or None,
                    created_by=current_user.id)
        db.add(c); db.commit()
        flash_msg(f'✅ تمت إضافة جهة الاتصال: {first_name}', 'success')
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
        c.job_title  = request.form.get('job_title','').strip() or None
        c.company    = request.form.get('company','').strip() or None
        c.department = request.form.get('department','').strip() or None
        c.notes      = request.form.get('notes','').strip() or None
        db.commit()
        flash_msg('✅ تم تحديث جهة الاتصال', 'success')
        return redirect(url_for('contacts.index'))
    return render_template('contacts/form.html', contact=c, form={})

@contacts_bp.route('/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    db = get_db(); perms = get_permissions()
    ids = request.form.getlist('ids'); count = 0
    for cid in ids:
        try:
            c = db.query(Contact).get(int(cid))
            if c and (c.created_by == current_user.id or perms.is_admin()):
                db.delete(c); count += 1
        except: pass
    db.commit()
    flash_msg(f'✅ تم حذف {count} جهة اتصال', 'success' if count else 'warning')
    return redirect(url_for('contacts.index'))


@contacts_bp.route('/<int:cid>/delete', methods=['POST'])
@login_required
def delete(cid):
    db = get_db(); perms = get_permissions()
    c = db.query(Contact).get(cid)
    if not c: abort(404)
    if c.created_by != current_user.id and not perms.is_admin(): abort(403)
    db.delete(c); db.commit()
    flash_msg('تم حذف جهة الاتصال', 'success')
    return redirect(url_for('contacts.index'))


# ── Individual Contact Export ─────────────────────────────────────────────────
@contacts_bp.route('/<int:cid>/export')
@login_required
def export_single(cid):
    db = get_db(); perms = get_permissions()
    c = db.query(Contact).get(cid)
    if not c: abort(404)
    if c.created_by != current_user.id and not perms.is_admin(): abort(403)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['first_name','last_name','email','phone','job_title','department','company','notes'])
    writer.writerow([
        c.first_name, c.last_name or '', c.email, c.phone or '',
        c.job_title or '', c.department or '', c.company or '', c.notes or ''
    ])
    content = b'\xef\xbb\xbf' + output.getvalue().encode('utf-8')
    safe_name = (c.first_name or 'contact').replace(' ','_')
    return Response(content, mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=contact_{safe_name}.csv'})


# ── CSV Template Download ─────────────────────────────────────────────────────
@contacts_bp.route('/csv-template')
@login_required
def csv_template():
    from flask import session
    is_en = session.get('lang','ar') == 'en'
    rows = [
        ['الاسم الأول','اسم العائلة','البريد الإلكتروني','الهاتف','المسمى الوظيفي','الدائرة','الشركة','ملاحظات'],
        ['محمد','الأحمد','m.ahmed@example.com','0791234567','مدير','المالية','شركة ABC',''],
        ['سارة','العلي','s.ali@example.com','0799876543','مستشار','الموارد البشرية','مؤسسة XYZ',''],
    ] if not is_en else [
        ['First Name','Last Name','Email','Phone','Job Title','Department','Company','Notes'],
        ['Mohammad','Al-Ahmad','m.ahmed@example.com','0791234567','Manager','Finance','ABC Corp',''],
        ['Sara','Al-Ali','s.ali@example.com','0799876543','Consultant','HR','XYZ Org',''],
    ]
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return Response(b'\xef\xbb\xbf' + out.getvalue().encode('utf-8'),
                    mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=contacts_template.csv'})

@contacts_bp.route('/import-csv', methods=['GET','POST'])
@login_required
def import_csv():
    db = get_db(); perms = get_permissions()
    if not perms.can('contacts_add'): abort(403)
    if request.method == 'POST':
        f = request.files.get('csv_file')
        if not f:
            flash_msg('اختر ملف CSV', 'danger')
            return redirect(url_for('contacts.import_csv'))
        try:
            content = f.read()
            text = ''
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
                    last_name=(row.get('last_name') or row.get('اسم العائلة') or '').strip() or None,
                    email=em,
                    phone=(row.get('phone') or row.get('الهاتف') or '').strip() or None,
                    job_title=(row.get('job_title') or row.get('المسمى الوظيفي') or '').strip() or None,
                    department=(row.get('department') or row.get('الدائرة') or '').strip() or None,
                    company=(row.get('company') or row.get('الشركة') or '').strip() or None,
                    notes=(row.get('notes') or row.get('ملاحظات') or '').strip() or None,
                    created_by=current_user.id
                )
                db.add(c); count += 1
            db.commit()
            flash_msg(f'✅ تم استيراد {count} جهة اتصال', 'success')
        except Exception as e:
            flash_msg(f'خطأ في الاستيراد: {e}', 'danger')
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
    writer.writerow(['first_name','last_name','email','phone','job_title','department','company','notes'])
    for c in contacts:
        writer.writerow([
            c.first_name, c.last_name or '', c.email, c.phone or '',
            c.job_title or '', c.department or '', c.company or '', c.notes or ''
        ])
    content = b'\xef\xbb\xbf' + output.getvalue().encode('utf-8')
    return Response(content, mimetype='text/csv',
                    headers={'Content-Disposition':
                             f'attachment; filename=contacts_{datetime.now().strftime("%Y%m%d")}.csv'})

@contacts_bp.route('/template-csv')
@login_required
def template_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['first_name','last_name','email','phone','job_title','company','notes'])
    writer.writerow(['أحمد','العلي','ahmed@example.com','0501234567','مدير','شركة أ',''])
    content = b'\xef\xbb\xbf' + output.getvalue().encode('utf-8')
    return Response(content, mimetype='text/csv',
                    headers={'Content-Disposition':'attachment; filename=contacts_template.csv'})
