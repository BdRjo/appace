"""
ARS — Back-Office (Admin Panel)
واجهة إدارة كاملة لكل جداول قاعدة البيانات
"""
import json
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   request, abort, jsonify)
from flask_login import login_required, current_user
from sqlalchemy import inspect, text
from utils.helpers import get_db, syslog
from utils.flash_helper import flash_msg

bo_bp = Blueprint('backoffice', __name__, url_prefix='/admin/backoffice')

# ── Tables exposed in back-office ─────────────────────────────────────────────
TABLES = {
    'users': {
        'label': 'Users / المستخدمون', 'label_ar': 'المستخدمون', 'label_en': 'Users',
        'icon': 'bi-people',
        'color': '#0C67EC',
        'hidden_cols': ['password_hash', 'reset_code', 'verification_code'],
        'readonly_cols': ['id', 'created_at', 'last_login', 'login_count'],
        'searchable': ['username', 'full_name', 'email'],
        'order_by': 'id DESC',
    },
    'reservations': {
        'label': 'Reservations / الحجوزات', 'label_ar': 'الحجوزات', 'label_en': 'Reservations',
        'icon': 'bi-journal-text',
        'color': '#0d6efd',
        'hidden_cols': [],
        'readonly_cols': ['id', 'created_at', 'booking_number'],
        'searchable': ['title', 'booking_number', 'status'],
        'order_by': 'id DESC',
    },
    'venues': {
        'label': 'Venues / القاعات', 'label_ar': 'القاعات', 'label_en': 'Venues',
        'icon': 'bi-building',
        'color': '#6C3483',
        'hidden_cols': [],
        'readonly_cols': ['id'],
        'searchable': ['name', 'code'],
        'order_by': 'id DESC',
    },
    'locations': {
        'label': 'Locations / المواقع', 'label_ar': 'المواقع', 'label_en': 'Locations',
        'icon': 'bi-geo-alt',
        'color': '#fd7e14',
        'hidden_cols': [],
        'readonly_cols': ['id', 'created_at'],
        'searchable': ['name', 'city', 'area'],
        'order_by': 'id DESC',
    },
    'roles': {
        'label': 'Roles / الأدوار', 'label_ar': 'الأدوار', 'label_en': 'Roles',
        'icon': 'bi-shield',
        'color': '#dc3545',
        'hidden_cols': [],
        'readonly_cols': ['id'],
        'searchable': ['name'],
        'order_by': 'id',
    },
    'contacts': {
        'label': 'Contacts / جهات الاتصال', 'label_ar': 'جهات الاتصال', 'label_en': 'Contacts',
        'icon': 'bi-person-lines-fill',
        'color': '#0dcaf0',
        'hidden_cols': [],
        'readonly_cols': ['id', 'created_at'],
        'searchable': ['first_name', 'last_name', 'email'],
        'order_by': 'id DESC',
    },
    'system_logs': {
        'label': 'System Logs / سجل النظام', 'label_ar': 'سجل النظام', 'label_en': 'System Logs',
        'icon': 'bi-shield-check',
        'color': '#6610f2',
        'hidden_cols': [],
        'readonly_cols': ['id', 'created_at', 'user_id', 'action', 'detail', 'ip'],
        'searchable': ['action', 'detail'],
        'order_by': 'id DESC',
        'read_only': True,
    },
    'login_logs': {
        'label': 'Login Logs / سجل الدخول', 'label_ar': 'سجل الدخول', 'label_en': 'Login Logs',
        'icon': 'bi-clock-history',
        'color': '#198754',
        'hidden_cols': [],
        'readonly_cols': ['id', 'user_id', 'login_at', 'ip', 'browser', 'success'],
        'searchable': ['ip', 'browser'],
        'order_by': 'id DESC',
        'read_only': True,
    },
    'blocked_periods': {
        'label': 'Blocked Periods / الفترات المحظورة', 'label_ar': 'الفترات المحظورة', 'label_en': 'Blocked Periods',
        'icon': 'bi-slash-circle',
        'color': '#adb5bd',
        'hidden_cols': [],
        'readonly_cols': ['id', 'created_at'],
        'searchable': ['reason'],
        'order_by': 'id DESC',
    },
    'checklists': {
        'label': 'Checklists / قوائم المهام', 'label_ar': 'قوائم المهام', 'label_en': 'Checklists',
        'icon': 'bi-check2-square',
        'color': '#20c997',
        'hidden_cols': [],
        'readonly_cols': ['id', 'created_at'],
        'searchable': ['title'],
        'order_by': 'id DESC',
    },
}

def _admin_required():
    from utils.helpers import get_permissions
    return get_permissions().is_admin()

def _get_columns(db, table_name, hidden=None):
    """Get column names for a table, excluding hidden ones"""
    try:
        result = db.execute(text(f'SELECT * FROM "{table_name}" LIMIT 0'))
        cols = [c for c in result.keys()]
        if hidden:
            cols = [c for c in cols if c not in hidden]
        return cols
    except Exception:
        return []

def _get_rows(db, table_name, search='', page=1, per_page=25, searchable=None, order_by='id DESC'):
    offset = (page - 1) * per_page
    try:
        where = ''
        params = {}
        if search and searchable:
            conds = [f'CAST("{c}" AS TEXT) LIKE :q' for c in searchable]
            where = 'WHERE ' + ' OR '.join(conds)
            params['q'] = f'%{search}%'
        count_sql = f'SELECT COUNT(*) FROM "{table_name}" {where}'
        total = db.execute(text(count_sql), params).scalar() or 0
        rows_sql = f'SELECT * FROM "{table_name}" {where} ORDER BY {order_by} LIMIT {per_page} OFFSET {offset}'
        rows = db.execute(text(rows_sql), params).fetchall()
        return rows, total
    except Exception as e:
        return [], 0

def _get_row(db, table_name, row_id):
    try:
        result = db.execute(text(f'SELECT * FROM "{table_name}" WHERE id = :id'), {'id': row_id})
        return result.fetchone()
    except Exception:
        return None

# ── Routes ────────────────────────────────────────────────────────────────────
@bo_bp.route('/')
@login_required
def index():
    if not _admin_required():
        flash_msg('غير مصرح', 'danger')
        return redirect(url_for('admin.dashboard'))
    db = get_db()
    stats = {}
    for tname in TABLES:
        try:
            stats[tname] = db.execute(text(f'SELECT COUNT(*) FROM "{tname}"')).scalar() or 0
        except:
            stats[tname] = '—'
    return render_template('admin/backoffice/index.html',
                           tables=TABLES, stats=stats)

@bo_bp.route('/table/<table_name>')
@login_required
def table_view(table_name):
    if not _admin_required(): abort(403)
    if table_name not in TABLES: abort(404)
    cfg = TABLES[table_name]
    db  = get_db()
    search   = request.args.get('q', '')
    page     = int(request.args.get('page', 1))
    per_page = 30
    rows, total = _get_rows(db, table_name, search, page, per_page,
                             cfg.get('searchable'), cfg.get('order_by','id DESC'))
    cols = _get_columns(db, table_name, cfg.get('hidden_cols', []))
    pages = max(1, (total + per_page - 1) // per_page)
    return render_template('admin/backoffice/table.html',
        table_name=table_name, cfg=cfg, cols=cols,
        rows=rows, total=total, page=page, pages=pages,
        search=search, per_page=per_page,
        tables=TABLES)

@bo_bp.route('/table/<table_name>/row/<int:row_id>', methods=['GET', 'POST'])
@login_required
def row_edit(table_name, row_id):
    if not _admin_required(): abort(403)
    if table_name not in TABLES: abort(404)
    cfg = TABLES[table_name]
    if cfg.get('read_only'):
        flash_msg('هذا الجدول للقراءة فقط', 'warning')
        return redirect(url_for('backoffice.table_view', table_name=table_name))
    db = get_db()
    row = _get_row(db, table_name, row_id)
    if not row: abort(404)
    cols = _get_columns(db, table_name, cfg.get('hidden_cols', []))
    if request.method == 'POST':
        updates = {}
        for col in cols:
            if col in cfg.get('readonly_cols', []) or col == 'id': continue
            val = request.form.get(col, '')
            updates[col] = val if val != '' else None
        if updates:
            set_clause = ', '.join([f'"{k}" = :{k}' for k in updates])
            updates['_id'] = row_id
            db.execute(text(f'UPDATE "{table_name}" SET {set_clause} WHERE id = :_id'), updates)
            db.commit()
            syslog('BACKOFFICE_EDIT', f'{table_name} row {row_id} updated')
            flash_msg(f'✅ تم تحديث السجل #{row_id}', 'success')
        return redirect(url_for('backoffice.table_view', table_name=table_name))
    return render_template('admin/backoffice/row_edit.html',
        table_name=table_name, cfg=cfg, cols=cols,
        row=row, row_dict=dict(zip(row._fields, row)),
        tables=TABLES)

@bo_bp.route('/table/<table_name>/row/<int:row_id>/delete', methods=['POST'])
@login_required
def row_delete(table_name, row_id):
    if not _admin_required(): abort(403)
    if table_name not in TABLES: abort(404)
    cfg = TABLES[table_name]
    if cfg.get('read_only'):
        flash_msg('هذا الجدول للقراءة فقط', 'warning')
        return redirect(url_for('backoffice.table_view', table_name=table_name))
    db = get_db()
    try:
        db.execute(text(f'DELETE FROM "{table_name}" WHERE id = :id'), {'id': row_id})
        db.commit()
        syslog('BACKOFFICE_DELETE', f'{table_name} row {row_id} deleted')
        flash_msg(f'✅ تم حذف السجل #{row_id}', 'success')
    except Exception as e:
        flash_msg(f'خطأ: {e}', 'danger')
    return redirect(url_for('backoffice.table_view', table_name=table_name))

@bo_bp.route('/table/<table_name>/new', methods=['GET', 'POST'])
@login_required
def row_new(table_name):
    if not _admin_required(): abort(403)
    if table_name not in TABLES: abort(404)
    cfg = TABLES[table_name]
    if cfg.get('read_only'):
        flash_msg('هذا الجدول للقراءة فقط', 'warning')
        return redirect(url_for('backoffice.table_view', table_name=table_name))
    db = get_db()
    cols = _get_columns(db, table_name, cfg.get('hidden_cols', []))
    editable = [c for c in cols if c not in cfg.get('readonly_cols', []) and c != 'id']
    if request.method == 'POST':
        inserts = {}
        for col in editable:
            val = request.form.get(col, '')
            if val: inserts[col] = val
        if inserts:
            cols_sql  = ', '.join([f'"{k}"' for k in inserts])
            vals_sql  = ', '.join([f':{k}' for k in inserts])
            db.execute(text(f'INSERT INTO "{table_name}" ({cols_sql}) VALUES ({vals_sql})'), inserts)
            db.commit()
            syslog('BACKOFFICE_INSERT', f'{table_name} new row added')
            flash_msg('✅ تم إضافة السجل', 'success')
        return redirect(url_for('backoffice.table_view', table_name=table_name))
    return render_template('admin/backoffice/row_new.html',
        table_name=table_name, cfg=cfg, cols=editable,
        tables=TABLES)

@bo_bp.route('/api/table/<table_name>/count')
@login_required
def api_count(table_name):
    if not _admin_required(): abort(403)
    db = get_db()
    try:
        count = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
        return jsonify({'count': count})
    except:
        return jsonify({'count': 0})
