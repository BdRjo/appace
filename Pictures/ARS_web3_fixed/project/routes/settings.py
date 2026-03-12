"""الإعدادات"""
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from utils.helpers import get_db, admin_required
import os, json

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

SETTINGS_FILE = os.environ.get('SETTINGS_PATH', 'ars_settings.json')

def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            return json.load(open(SETTINGS_FILE))
    except: pass
    return {
        'system_name': 'ARS — نظام إدارة الحجوزات',
        'email_provider': 'gmail', 'smtp_host': 'smtp.gmail.com',
        'smtp_port': 587, 'smtp_user': '', 'smtp_pass': '',
        'require_approval': True, 'allow_self_register': True,
        'max_days_advance': 90, 'min_hours_before': 2,
    }

def save_settings(data):
    try:
        json.dump(data, open(SETTINGS_FILE,'w'), ensure_ascii=False, indent=2)
        return True
    except: return False

@settings_bp.route('/', methods=['GET','POST'])
@login_required
@admin_required
def index():
    cfg = load_settings()
    if request.method == 'POST':
        cfg['system_name']       = request.form.get('system_name', cfg['system_name'])
        cfg['email_provider']    = request.form.get('email_provider', 'gmail')
        cfg['smtp_host']         = request.form.get('smtp_host','').strip()
        cfg['smtp_port']         = int(request.form.get('smtp_port', 587) or 587)
        cfg['smtp_user']         = request.form.get('smtp_user','').strip()
        cfg['require_approval']  = request.form.get('require_approval') == 'on'
        cfg['allow_self_register'] = request.form.get('allow_self_register') == 'on'
        cfg['max_days_advance']  = int(request.form.get('max_days_advance', 90) or 90)
        cfg['min_hours_before']  = int(request.form.get('min_hours_before', 2) or 2)
        new_pass = request.form.get('smtp_pass','').strip()
        if new_pass: cfg['smtp_pass'] = new_pass
        if save_settings(cfg):
            flash('✅ تم حفظ الإعدادات', 'success')
        else:
            flash('تعذّر حفظ الإعدادات (تحقق من صلاحيات الملف)', 'warning')
        return redirect(url_for('settings.index'))
    return render_template('settings/index.html', cfg=cfg)

@settings_bp.route('/test-email', methods=['POST'])
@login_required
@admin_required
def test_email():
    cfg = load_settings()
    to  = request.form.get('test_email_to', current_user.email or '')
    if not to:
        flash('أدخل بريداً إلكترونياً للاختبار', 'danger')
        return redirect(url_for('settings.index'))
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText('هذا بريد اختباري من نظام ARS', 'plain', 'utf-8')
        msg['Subject'] = 'اختبار ARS'
        msg['From']    = cfg['smtp_user']
        msg['To']      = to
        with smtplib.SMTP(cfg['smtp_host'], cfg['smtp_port']) as s:
            s.starttls()
            s.login(cfg['smtp_user'], cfg['smtp_pass'])
            s.send_message(msg)
        flash(f'✅ تم إرسال بريد اختباري إلى: {to}', 'success')
    except Exception as e:
        flash(f'فشل الإرسال: {e}', 'danger')
    return redirect(url_for('settings.index'))
