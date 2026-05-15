"""
STAP — Control Panel (CP)
لوحة تحكم بالصفحات — مثل cPanel
"""
import json, os
from flask import (Blueprint, render_template, redirect, url_for,
                   request, jsonify)
from flask_login import login_required
from utils.helpers import get_db, syslog
from utils.flash_helper import flash_msg

cp_bp = Blueprint('cp', __name__, url_prefix='/admin/cp')

CP_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'cp_config.json'
)

# ── All system pages definition ───────────────────────────────────────────────
PAGES = [
    {
        'id': 'dashboard',
        'label_ar': 'لوحة التحكم الرئيسية',
        'label_en': 'Dashboard',
        'url': 'admin.dashboard',
        'icon': 'bi-speedometer2',
        'color': '#1565C0',
        'fields': [
            {'key': 'title_ar',    'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)',    'type': 'text',     'default': 'لوحة التحكم'},
            {'key': 'title_en',    'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)',    'type': 'text',     'default': 'Dashboard'},
            {'key': 'show_stats',  'label': 'Show Stat Cards', 'label_ar': 'إظهار بطاقات الإحصاء',   'type': 'toggle',   'default': True},
            {'key': 'show_chart',  'label': 'Show Chart', 'label_ar': 'إظهار الرسم البياني',        'type': 'toggle',   'default': True},
            {'key': 'show_recent', 'label': 'Show Recent Reservations', 'label_ar': 'إظهار آخر الحجوزات', 'type': 'toggle', 'default': True},
            {'key': 'show_quick',  'label': 'Show Quick Links', 'label_ar': 'إظهار الروابط السريعة',  'type': 'toggle',   'default': True},
        ]
    },
    {
        'id': 'reservations',
        'label_ar': 'الحجوزات',
        'label_en': 'Reservations',
        'url': 'reservations.index',
        'icon': 'bi-journal-text',
        'color': '#7B1FA2',
        'fields': [
            {'key': 'title_ar',     'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)',       'type': 'text',   'default': 'الحجوزات'},
            {'key': 'title_en',     'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)',       'type': 'text',   'default': 'Reservations'},
            {'key': 'enabled',      'label': 'Page Visible', 'label_ar': 'إظهار الصفحة',          'type': 'toggle', 'default': True},
            {'key': 'allow_new',    'label': 'Allow New Booking', 'label_ar': 'السماح بحجز جديد',     'type': 'toggle', 'default': True},
            {'key': 'allow_edit',   'label': 'Allow Edit', 'label_ar': 'السماح بالتعديل',            'type': 'toggle', 'default': True},
            {'key': 'allow_delete', 'label': 'Allow Delete', 'label_ar': 'السماح بالحذف',          'type': 'toggle', 'default': True},
            {'key': 'allow_export', 'label': 'Allow Export PDF/Excel', 'label_ar': 'تصدير PDF/Excel','type': 'toggle', 'default': True},
            {'key': 'show_employee','label': 'Show Requested Employee', 'label_ar': 'إظهار الموظف المطلوب','type': 'toggle','default': True},
        ]
    },
    {
        'id': 'venues',
        'label_ar': 'القاعات',
        'label_en': 'Venues',
        'url': 'venues.index',
        'icon': 'bi-building',
        'color': '#00695C',
        'fields': [
            {'key': 'title_ar',  'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)', 'type': 'text',   'default': 'القاعات'},
            {'key': 'title_en',  'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)', 'type': 'text',   'default': 'Venues'},
            {'key': 'enabled',   'label': 'Page Visible', 'label_ar': 'إظهار الصفحة',    'type': 'toggle', 'default': True},
            {'key': 'show_book', 'label': 'Show Book Button', 'label_ar': 'إظهار زر الحجز','type': 'toggle', 'default': True},
            {'key': 'show_map',  'label': 'Show Location', 'label_ar': 'إظهار الموقع',   'type': 'toggle', 'default': True},
        ]
    },
    {
        'id': 'venues_mgmt',
        'label_ar': 'إدارة القاعات',
        'label_en': 'Manage Venues',
        'url': 'venues_mgmt.index',
        'icon': 'bi-building-gear',
        'color': '#2E7D32',
        'fields': [
            {'key': 'title_ar',     'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)',  'type': 'text',   'default': 'إدارة القاعات'},
            {'key': 'title_en',     'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)',  'type': 'text',   'default': 'Manage Venues'},
            {'key': 'enabled',      'label': 'Page Visible', 'label_ar': 'إظهار الصفحة',     'type': 'toggle', 'default': True},
            {'key': 'allow_add',    'label': 'Allow Add', 'label_ar': 'السماح بالإضافة',        'type': 'toggle', 'default': True},
            {'key': 'allow_edit',   'label': 'Allow Edit', 'label_ar': 'السماح بالتعديل',       'type': 'toggle', 'default': True},
            {'key': 'allow_delete', 'label': 'Allow Delete', 'label_ar': 'السماح بالحذف',     'type': 'toggle', 'default': True},
            {'key': 'allow_import', 'label': 'Allow Import CSV', 'label_ar': 'استيراد CSV', 'type': 'toggle', 'default': True},
        ]
    },
    {
        'id': 'locations',
        'label_ar': 'المواقع',
        'label_en': 'Locations',
        'url': 'locations.index',
        'icon': 'bi-geo-alt',
        'color': '#E65100',
        'fields': [
            {'key': 'title_ar',  'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)', 'type': 'text',   'default': 'المواقع'},
            {'key': 'title_en',  'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)', 'type': 'text',   'default': 'Locations'},
            {'key': 'enabled',   'label': 'Page Visible', 'label_ar': 'إظهار الصفحة',    'type': 'toggle', 'default': True},
            {'key': 'allow_add', 'label': 'Allow Add', 'label_ar': 'السماح بالإضافة',       'type': 'toggle', 'default': True},
        ]
    },
    {
        'id': 'users',
        'label_ar': 'المستخدمون',
        'label_en': 'Users',
        'url': 'users.index',
        'icon': 'bi-people',
        'color': '#B71C1C',
        'fields': [
            {'key': 'title_ar',     'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)',   'type': 'text',   'default': 'المستخدمون'},
            {'key': 'title_en',     'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)',   'type': 'text',   'default': 'Users'},
            {'key': 'enabled',      'label': 'Page Visible', 'label_ar': 'إظهار الصفحة',      'type': 'toggle', 'default': True},
            {'key': 'allow_add',    'label': 'Allow Add User', 'label_ar': 'إضافة مستخدم',    'type': 'toggle', 'default': True},
            {'key': 'allow_edit',   'label': 'Allow Edit', 'label_ar': 'السماح بالتعديل',        'type': 'toggle', 'default': True},
            {'key': 'allow_delete', 'label': 'Allow Delete', 'label_ar': 'السماح بالحذف',      'type': 'toggle', 'default': True},
            {'key': 'allow_roles',  'label': 'Manage Roles', 'label_ar': 'إدارة الأدوار',      'type': 'toggle', 'default': True},
            {'key': 'allow_bulk',   'label': 'Bulk Message', 'label_ar': 'رسالة جماعية',      'type': 'toggle', 'default': True},
            {'key': 'allow_import', 'label': 'Import Users', 'label_ar': 'استيراد مستخدمين',      'type': 'toggle', 'default': True},
        ]
    },
    {
        'id': 'contacts',
        'label_ar': 'جهات الاتصال',
        'label_en': 'Contacts',
        'url': 'contacts.index',
        'icon': 'bi-person-lines-fill',
        'color': '#01579B',
        'fields': [
            {'key': 'title_ar',  'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)', 'type': 'text',   'default': 'جهات الاتصال'},
            {'key': 'title_en',  'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)', 'type': 'text',   'default': 'Contacts'},
            {'key': 'enabled',   'label': 'Page Visible', 'label_ar': 'إظهار الصفحة',    'type': 'toggle', 'default': True},
            {'key': 'allow_add', 'label': 'Allow Add', 'label_ar': 'السماح بالإضافة',       'type': 'toggle', 'default': True},
            {'key': 'allow_import','label': 'Allow Import', 'label_ar': 'استيراد',   'type': 'toggle', 'default': True},
            {'key': 'allow_export','label': 'Allow Export', 'label_ar': 'تصدير',   'type': 'toggle', 'default': True},
        ]
    },
    {
        'id': 'checklists',
        'label_ar': 'قوائم المهام',
        'label_en': 'Checklists',
        'url': 'checklists.index',
        'icon': 'bi-check2-square',
        'color': '#006064',
        'fields': [
            {'key': 'title_ar', 'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)', 'type': 'text',   'default': 'قوائم المهام'},
            {'key': 'title_en', 'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)', 'type': 'text',   'default': 'Checklists'},
            {'key': 'enabled',  'label': 'Page Visible', 'label_ar': 'إظهار الصفحة',    'type': 'toggle', 'default': True},
            {'key': 'allow_add','label': 'Allow Add', 'label_ar': 'السماح بالإضافة',       'type': 'toggle', 'default': True},
        ]
    },
    {
        'id': 'reports',
        'label_ar': 'التقارير',
        'label_en': 'Reports',
        'url': 'reports.index',
        'icon': 'bi-bar-chart',
        'color': '#4A148C',
        'fields': [
            {'key': 'title_ar',     'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)',    'type': 'text',   'default': 'التقارير'},
            {'key': 'title_en',     'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)',    'type': 'text',   'default': 'Reports'},
            {'key': 'enabled',      'label': 'Page Visible', 'label_ar': 'إظهار الصفحة',       'type': 'toggle', 'default': True},
            {'key': 'allow_export', 'label': 'Allow Export', 'label_ar': 'تصدير',       'type': 'toggle', 'default': True},
            {'key': 'show_compare', 'label': 'Show Comparison', 'label_ar': 'إظهار المقارنة',    'type': 'toggle', 'default': True},
        ]
    },
    {
        'id': 'calendar',
        'label_ar': 'التقويم',
        'label_en': 'Calendar',
        'url': 'calendar_view.index',
        'icon': 'bi-calendar3',
        'color': '#880E4F',
        'fields': [
            {'key': 'title_ar',    'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)',  'type': 'text',   'default': 'التقويم'},
            {'key': 'title_en',    'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)',  'type': 'text',   'default': 'Calendar'},
            {'key': 'enabled',     'label': 'Page Visible', 'label_ar': 'إظهار الصفحة',     'type': 'toggle', 'default': True},
            {'key': 'show_filter', 'label': 'Show Filters Bar', 'label_ar': 'إظهار شريط التصفية', 'type': 'toggle', 'default': True},
        ]
    },
    {
        'id': 'blocked',
        'label_ar': 'حظر الفترات',
        'label_en': 'Block Periods',
        'url': 'blocked.index',
        'icon': 'bi-slash-circle',
        'color': '#37474F',
        'fields': [
            {'key': 'title_ar', 'label': 'Page Title (AR)', 'label_ar': 'عنوان الصفحة (عربي)', 'type': 'text',   'default': 'حظر فترة'},
            {'key': 'title_en', 'label': 'Page Title (EN)', 'label_ar': 'عنوان الصفحة (إنجليزي)', 'type': 'text',   'default': 'Block Periods'},
            {'key': 'enabled',  'label': 'Page Visible', 'label_ar': 'إظهار الصفحة',    'type': 'toggle', 'default': True},
        ]
    },
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def _load():
    try:
        if os.path.exists(CP_CONFIG):
            return json.loads(open(CP_CONFIG, encoding='utf-8').read())
    except: pass
    return {}

def _save(cfg):
    with open(CP_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def cp_get(page_id, field_key, default=None):
    """Get a CP setting value"""
    cfg = _load()
    page_cfg = cfg.get(page_id, {})
    # Find default from PAGES definition
    if default is None:
        for p in PAGES:
            if p['id'] == page_id:
                for f in p.get('fields', []):
                    if f['key'] == field_key:
                        default = f.get('default', True)
                        break
    return page_cfg.get(field_key, default)

# ── Routes ────────────────────────────────────────────────────────────────────
@cp_bp.route('/')
@login_required
def index():
    from utils.helpers import get_permissions
    if not get_permissions().is_admin():
        flash_msg('غير مصرح', 'danger')
        return redirect(url_for('admin.dashboard'))
    cfg = _load()
    return render_template('admin/cp.html', pages=PAGES, cfg=cfg)

@cp_bp.route('/page/<page_id>', methods=['GET', 'POST'])
@login_required
def page_edit(page_id):
    from utils.helpers import get_permissions
    if not get_permissions().is_admin():
        flash_msg('غير مصرح', 'danger')
        return redirect(url_for('admin.dashboard'))

    page = next((p for p in PAGES if p['id'] == page_id), None)
    if not page:
        flash_msg('الصفحة غير موجودة', 'danger')
        return redirect(url_for('cp.index'))

    cfg = _load()

    if request.method == 'POST':
        page_cfg = {}
        for field in page['fields']:
            k = field['key']
            if field['type'] == 'toggle':
                page_cfg[k] = request.form.get(k) == '1'
            else:
                page_cfg[k] = request.form.get(k, field.get('default', ''))
        cfg[page_id] = page_cfg
        _save(cfg)
        syslog('CP_UPDATE', f'تم تحديث إعدادات صفحة: {page_id}')
        flash_msg(f'✅ تم حفظ إعدادات صفحة {page["label_ar"]}', 'success')
        return redirect(url_for('cp.index'))

    page_cfg = cfg.get(page_id, {})
    return render_template('admin/cp_page.html',
        page=page, page_cfg=page_cfg, cp_get=cp_get)

@cp_bp.route('/reset/<page_id>', methods=['POST'])
@login_required
def reset_page(page_id):
    from utils.helpers import get_permissions
    if not get_permissions().is_admin():
        return redirect(url_for('admin.dashboard'))
    cfg = _load()
    cfg.pop(page_id, None)
    _save(cfg)
    flash_msg('✅ تم إعادة الإعدادات الافتراضية', 'success')
    return redirect(url_for('cp.index'))

@cp_bp.route('/reset-all', methods=['POST'])
@login_required
def reset_all():
    from utils.helpers import get_permissions
    if not get_permissions().is_admin():
        return redirect(url_for('admin.dashboard'))
    if os.path.exists(CP_CONFIG):
        os.remove(CP_CONFIG)
    syslog('CP_RESET', 'تم إعادة تعيين كل إعدادات CP')
    flash_msg('✅ تم إعادة جميع الإعدادات', 'success')
    return redirect(url_for('cp.index'))
