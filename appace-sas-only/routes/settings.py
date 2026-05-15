"""الإعدادات"""
from utils.flash_helper import flash_msg
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from utils.helpers import get_db, admin_required
import os, json

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

SETTINGS_FILE = os.environ.get('SETTINGS_PATH', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ars_settings.json'))

def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            return json.load(open(SETTINGS_FILE))
    except: pass
    return {
        'system_name': 'STAP — نظام الحضور والمقابلات',
        'provider_key': 'gmail', 'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587, 'sender_email': '', 'sender_password': '',
        'sender_name': 'STAP System', 'use_tls': True,
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
        cfg['system_name']       = request.form.get('system_name', cfg.get('system_name','STAP'))
        cfg['provider_key']      = request.form.get('provider_key', 'gmail')
        cfg['smtp_server']       = request.form.get('smtp_server','').strip()
        cfg['smtp_port']         = int(request.form.get('smtp_port', 587) or 587)
        cfg['sender_email']      = request.form.get('sender_email','').strip()
        cfg['sender_name']       = request.form.get('sender_name','').strip()
        cfg['use_tls']           = request.form.get('use_tls') == 'on'
        cfg['require_approval']  = request.form.get('require_approval') == 'on'
        cfg['allow_self_register'] = request.form.get('allow_self_register') == 'on'
        cfg['max_days_advance']  = int(request.form.get('max_days_advance', 90) or 90)
        cfg['min_hours_before']  = int(request.form.get('min_hours_before', 2) or 2)
        new_pass = request.form.get('sender_password','').strip()
        if new_pass: cfg['sender_password'] = new_pass
        if save_settings(cfg):
            flash_msg('✅ تم حفظ الإعدادات', 'success')
        else:
            flash_msg('تعذّر حفظ الإعدادات (تحقق من صلاحيات الملف)', 'warning')
        return redirect(url_for('settings.index'))
    return render_template('settings/index.html', cfg=cfg)

@settings_bp.route('/test-email', methods=['POST'])
@login_required
@admin_required
def test_email():
    cfg = load_settings()
    to  = request.form.get('test_email_to', current_user.email or '')
    if not to:
        flash_msg('أدخل بريداً إلكترونياً للاختبار', 'danger')
        return redirect(url_for('settings.index'))
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText('هذا بريد اختباري من نظام STAP', 'plain', 'utf-8')
        msg['Subject'] = 'اختبار STAP'
        msg['From']    = cfg.get('sender_email', cfg.get('smtp_user',''))
        msg['To']      = to
        host = cfg.get('smtp_server', cfg.get('smtp_host',''))
        port = cfg.get('smtp_port', 587)
        user = cfg.get('sender_email', cfg.get('smtp_user',''))
        pwd  = cfg.get('sender_password', cfg.get('smtp_pass',''))
        with smtplib.SMTP(host, port) as s:
            if cfg.get('use_tls', True): s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
        flash_msg(f'✅ تم إرسال بريد اختباري إلى: {to}', 'success')
    except Exception as e:
        flash_msg(f'فشل الإرسال: {e}', 'danger')
    return redirect(url_for('settings.index'))
