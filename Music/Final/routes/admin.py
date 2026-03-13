"""
Admin — لوحة التحكم + الصيانة + الإعدادات
مطابق لـ v54: show_dashboard + MaintenanceWindow + SettingsWindow
"""
import os, shutil, json
from datetime import datetime, timedelta
from utils.flash_helper import flash_msg
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort, jsonify, send_file)
from flask_login import login_required, current_user
from sqlalchemy import func, text
from models.database import Reservation, User, Venue, Location, SystemLog, LoginLog
from utils.helpers import get_db, admin_required, syslog, paginate

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

import os as _os
CONFIG_EMAIL = _os.environ.get('EMAIL_CONFIG_PATH',
    _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'email_config.json'))
CONFIG_MAINT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'maintenance_config.json')


# ── Dashboard — مطابق لـ v54 show_dashboard ───────────────────────────────────
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    db  = get_db()
    now = datetime.now()

    stats = {
        'total':      db.query(Reservation).count(),
        'pending':    db.query(Reservation).filter_by(status='pending').count(),
        'approved':   db.query(Reservation).filter_by(status='approved').count(),
        'rejected':   db.query(Reservation).filter_by(status='rejected').count(),
        'cancelled':  db.query(Reservation).filter_by(status='cancelled').count(),
        'completed':  db.query(Reservation).filter_by(status='completed').count(),
        'users':      db.query(User).filter_by(is_active=True).count(),
        'venues':     db.query(Venue).filter_by(is_active=True).count(),
        'locations':  db.query(Location).filter_by(is_active=True).count(),
        'this_month': db.query(Reservation).filter(
            Reservation.created_at >= now.replace(day=1)).count(),
    }

    # Trend شهري (12 شهر) — مثل v54 show_bar_chart
    monthly = []
    for i in range(11, -1, -1):
        d   = (now - timedelta(days=30*i)).replace(day=1,hour=0,minute=0,second=0)
        nd  = (d + timedelta(days=32)).replace(day=1)
        cnt = db.query(Reservation).filter(
            Reservation.created_at >= d, Reservation.created_at < nd).count()
        monthly.append({'month': d.strftime('%m/%Y'), 'count': cnt})

    # حجوزات معلقة — مثل v54 pending list
    pending_list = (db.query(Reservation).filter_by(status='pending')
                    .order_by(Reservation.created_at.asc()).limit(8).all())

    # أعلى 5 قاعات
    top_venues = (db.query(Venue.name, func.count(Reservation.id).label('cnt'))
                  .join(Reservation, Reservation.venue_id == Venue.id, isouter=True)
                  .group_by(Venue.id)
                  .order_by(func.count(Reservation.id).desc())
                  .limit(5).all())

    return render_template('admin/dashboard.html',
        stats=stats, monthly=monthly,
        pending_list=pending_list, top_venues=top_venues)


# ── System log — مطابق لـ v54 SecurityLogWindow ───────────────────────────────
@admin_bp.route('/system-log')
@login_required
@admin_required
def system_log():
    db     = get_db()
    page   = request.args.get('page',1,type=int)
    level  = request.args.get('level','')
    action = request.args.get('action','')
    q      = db.query(SystemLog)
    if level:  q = q.filter(SystemLog.level == level)
    if action: q = q.filter(SystemLog.action.ilike(f'%{action}%'))
    items, total, total_pages = paginate(q.order_by(SystemLog.created_at.desc()), page, 30)
    return render_template('admin/system_log.html',
        logs=items, total=total, page=page, total_pages=total_pages,
        level=level, action=action)


# ── Audit Log ──────────────────────────────────────────────────────────────────
@admin_bp.route('/audit-log')
@login_required
@admin_required
def audit_log():
    db   = get_db()
    page = request.args.get('page', 1, type=int)
    user_filter = request.args.get('user', '')
    action_filter = request.args.get('action', '')
    q = db.query(SystemLog)
    if user_filter:
        try:
            uid = int(user_filter)
            q = q.filter(SystemLog.user_id == uid)
        except ValueError:
            pass
    if action_filter:
        q = q.filter(SystemLog.action.ilike(f'%{action_filter}%'))
    items, total, total_pages = paginate(q.order_by(SystemLog.created_at.desc()), page, 50)
    users = db.query(User).order_by(User.full_name).all()
    return render_template('admin/audit_log.html',
        logs=items, total=total, page=page, total_pages=total_pages,
        users=users, user_filter=user_filter, action_filter=action_filter)


# ── Maintenance — مطابق لـ v54 MaintenanceWindow ─────────────────────────────
CONFIG_TICKER = 'ticker_config.json'

def _load_ticker():
    try:
        with open(CONFIG_TICKER, encoding='utf-8') as f:
            return json.load(f)
    except:
        return {
            'feeds_ar': ['مرحباً بكم في نظام ARS لإدارة الحجوزات'],
            'feeds_en': ['Welcome to ARS Reservation System'],
            'fg': '#F2C99A', 'bg': '', 'font': 'Tahoma',
            'size': 15, 'speed': 35, 'opacity': 0
        }

def _save_ticker(cfg):
    with open(CONFIG_TICKER, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def _save_maintenance(cfg):
    with open(CONFIG_MAINT, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

@admin_bp.route('/maintenance', methods=['GET','POST'])
@login_required
@admin_required
def maintenance():
    # قراءة حالة الصيانة
    try:
        with open(CONFIG_MAINT) as f:
            mcfg = json.load(f)
    except:
        mcfg = {'system_suspended': False, 'registration_suspended': False}

    db = get_db()
    log_count = db.query(SystemLog).count()
    ticker = _load_ticker()

    if request.method == 'POST':
        action = request.form.get('ticker_action','')
        if action == 'add_ar':
            text = request.form.get('ticker_text_ar','').strip()
            if text:
                ticker.setdefault('feeds_ar', []).append(text)
                _save_ticker(ticker)
        elif action == 'add_en':
            text = request.form.get('ticker_text_en','').strip()
            if text:
                ticker.setdefault('feeds_en', []).append(text)
                _save_ticker(ticker)
        elif action == 'del_ar':
            idx = int(request.form.get('ticker_idx', 0))
            feeds = ticker.get('feeds_ar', [])
            if 0 <= idx < len(feeds): feeds.pop(idx); ticker['feeds_ar'] = feeds; _save_ticker(ticker)
        elif action == 'del_en':
            idx = int(request.form.get('ticker_idx', 0))
            feeds = ticker.get('feeds_en', [])
            if 0 <= idx < len(feeds): feeds.pop(idx); ticker['feeds_en'] = feeds; _save_ticker(ticker)
        elif action == 'save_appearance':
            ticker['fg']      = request.form.get('ticker_fg', '#F2C99A')
            ticker['bg']      = request.form.get('ticker_bg', '')
            ticker['font']    = request.form.get('ticker_font', 'Tajawal')
            ticker['size']    = int(request.form.get('ticker_size', 11))
            ticker['speed']   = int(request.form.get('ticker_speed', 35))
            ticker['opacity'] = int(request.form.get('ticker_opacity', 0) or 0)
            _save_ticker(ticker)
        elif action == 'save_logo':
            import base64
            logo_file = request.files.get('logo_file')
            if logo_file and logo_file.filename:
                data = base64.b64encode(logo_file.read()).decode('utf-8')
                mt   = logo_file.content_type or 'image/png'
                mcfg['logo_b64'] = f'data:{mt};base64,{data}'
                if request.form.get('remove_logo'):
                    mcfg.pop('logo_b64', None)
            elif request.form.get('remove_logo'):
                mcfg.pop('logo_b64', None)
            # Save header image position (left / center / right)
            mcfg['header_img_position'] = request.form.get('header_img_position', 'center')
            # Save optional separate header image for PDF
            hdr_file = request.files.get('header_img_file')
            if hdr_file and hdr_file.filename:
                import base64 as _b64
                hdata = _b64.b64encode(hdr_file.read()).decode('utf-8')
                hmt   = hdr_file.content_type or 'image/png'
                mcfg['header_img_b64'] = f'data:{hmt};base64,{hdata}'
            if request.form.get('remove_header_img'):
                mcfg.pop('header_img_b64', None)
            _save_maintenance(mcfg)
        elif action == 'save_report_header':
            mcfg['report_header_title']    = request.form.get('report_header_title','').strip()
            mcfg['report_header_subtitle'] = request.form.get('report_header_subtitle','').strip()
            mcfg['report_header_extra']    = request.form.get('report_header_extra','').strip()
            mcfg['report_header_footer']   = request.form.get('report_header_footer','').strip()
            _save_maintenance(mcfg)
        flash_msg('تم تحديث شريط الأخبار', 'success')
        return redirect(url_for('admin.maintenance'))

    return render_template('admin/maintenance.html',
        mcfg=mcfg, log_count=log_count,
        ticker=ticker, ticker_cfg=ticker,
        ticker_messages_ar=ticker.get('feeds_ar',[]),
        ticker_messages_en=ticker.get('feeds_en',[]))


# ── Ticker config API ─────────────────────────────────────────────────────────
@admin_bp.route('/ticker-config')
def ticker_config_api():
    """Public endpoint for base.html ticker JS"""
    from flask import jsonify
    ticker = _load_ticker()
    # Default opacity = 0
    if 'opacity' not in ticker:
        ticker['opacity'] = 0
    return jsonify(ticker)


# ── Live users + IP/Browser info ──────────────────────────────────────────────
@admin_bp.route('/live-users')
@login_required
@admin_required
def live_users():
    from flask import jsonify
    from datetime import datetime, timedelta
    from models.database import LoginLog
    db = get_db()
    # Consider users active if logged in within last 15 minutes
    cutoff = datetime.now() - timedelta(minutes=15)
    try:
        recent = db.query(LoginLog).filter(
            LoginLog.created_at >= cutoff,
            LoginLog.success == True
        ).order_by(LoginLog.created_at.desc()).all()
        users = []
        seen = set()
        for log in recent:
            if log.user_id not in seen:
                seen.add(log.user_id)
                users.append({
                    'username': log.user.username if log.user else '?',
                    'full_name': log.user.full_name if log.user else '?',
                    'ip': log.ip_address or '—',
                    'browser': (log.platform or log.hostname or 'Browser')[:40],
                    'time': log.created_at.strftime('%H:%M') if log.created_at else '—',
                })
        return jsonify({'users': users, 'count': len(users)})
    except Exception as e:
        return jsonify({'users': [], 'count': 0, 'error': str(e)})


# ── Backup — مطابق لـ v54 backup_database ────────────────────────────────────
@admin_bp.route('/maintenance/backup', methods=['POST'])
@login_required
@admin_required
def backup():
    db_path = 'acs_venues.db'
    if not os.path.exists(db_path):
        flash_msg('لا توجد قاعدة بيانات SQLite (PostgreSQL لا تدعم هذه العملية في Render)', 'warning')
        return redirect(url_for('admin.maintenance'))
    os.makedirs('backups', exist_ok=True)
    ts  = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = f'backups/acs_backup_{ts}.db'
    shutil.copy2(db_path, dst)
    syslog('BACKUP', f'نسخة احتياطية: {dst}')
    flash_msg(f'✅ تم إنشاء النسخة الاحتياطية: {dst}', 'success')
    return redirect(url_for('admin.maintenance'))


# ── Clean logs — مطابق لـ v54 clean_logs ─────────────────────────────────────
@admin_bp.route('/maintenance/clean-logs', methods=['POST'])
@login_required
@admin_required
def clean_logs():
    db      = get_db()
    cutoff  = datetime.now() - timedelta(days=30)
    deleted = db.query(SystemLog).filter(SystemLog.created_at < cutoff).delete()
    db.commit()
    syslog('CLEAN_LOGS', f'تم حذف {deleted} سجل قديم')
    flash_msg(f'✅ تم حذف {deleted} سجل قديم (أكثر من 30 يوم)', 'success')
    return redirect(url_for('admin.maintenance'))


# ── Optimize — مطابق لـ v54 optimize_database ────────────────────────────────
@admin_bp.route('/maintenance/optimize', methods=['POST'])
@login_required
@admin_required
def optimize():
    db = get_db()
    try:
        db.execute(text('VACUUM'))
        db.commit()
    except:
        pass  # PostgreSQL لا تدعم VACUUM عبر SQLAlchemy
    syslog('OPTIMIZE', 'تحسين قاعدة البيانات')
    flash_msg('✅ تم تحسين قاعدة البيانات', 'success')
    return redirect(url_for('admin.maintenance'))


# ── Suspend toggle — مطابق لـ v54 _toggle_sys / _toggle_reg ──────────────────
@admin_bp.route('/maintenance/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_maintenance():
    try:
        with open(CONFIG_MAINT) as f:
            mcfg = json.load(f)
    except:
        mcfg = {'system_suspended': False, 'registration_suspended': False}

    toggle = request.form.get('toggle','')
    if toggle == 'system':
        mcfg['system_suspended'] = not mcfg.get('system_suspended', False)
    elif toggle == 'registration':
        mcfg['registration_suspended'] = not mcfg.get('registration_suspended', False)

    with open(CONFIG_MAINT, 'w') as f:
        json.dump(mcfg, f)

    syslog('TOGGLE_MAINTENANCE', f'{toggle}: {mcfg}')
    flash_msg('✅ تم تحديث إعدادات الصيانة', 'success')
    return redirect(url_for('admin.maintenance'))


# ── Settings (Email Config) — مطابق لـ v54 EmailConfigWindow ─────────────────
@admin_bp.route('/settings', methods=['GET','POST'])
@login_required
@admin_required
def settings():
    from utils.i18n import get_lang as _gl
    _is_en = _gl() == 'en'
    PROVIDERS = {
        'gmail':     {'label':'Gmail',                   'smtp':'smtp.gmail.com',          'port':587,
                      'help':'Use App Password from Google Account → Security → App passwords' if _is_en else 'استخدم App Password من Google Account → Security → App passwords'},
        'office365': {'label':'Microsoft 365 / Outlook', 'smtp':'smtp.office365.com',       'port':587,
                      'help':'Use Microsoft 365 email and password or App Password' if _is_en else 'استخدم بريد Microsoft 365 وكلمة المرور أو App Password'},
        'outlook':   {'label':'Outlook.com (Hotmail)',   'smtp':'smtp-mail.outlook.com',    'port':587,
                      'help':'Use your Outlook.com email and password' if _is_en else 'استخدم بريد Outlook.com وكلمة المرور'},
        'yahoo':     {'label':'Yahoo Mail',              'smtp':'smtp.mail.yahoo.com',      'port':587,
                      'help':'Enable "Allow apps that use less secure sign in" or use App password' if _is_en else 'فعّل "Allow apps that use less secure sign in" أو استخدم App password'},
        'brevo':     {'label':'Brevo (Sendinblue)',       'smtp':'smtp-relay.brevo.com',     'port':587,
                      'help':'Create a free account on brevo.com → SMTP & API → Generate SMTP Key' if _is_en else 'أنشئ حساباً مجانياً على brevo.com — اذهب إلى SMTP & API → Generate SMTP Key'},
        'custom':    {'label':'Custom Server' if _is_en else 'خادم مخصص', 'smtp':'', 'port':587,
                      'help':'Enter your server details manually' if _is_en else 'أدخل بيانات خادمك يدوياً'},
    }

    try:
        with open(CONFIG_EMAIL, encoding='utf-8') as f:
            cfg = json.load(f)
    except:
        cfg = {'smtp_server':'smtp.gmail.com','smtp_port':587,
               'sender_email':'','sender_password':'',
               'sender_name':'ARS Applied Reservation System',
               'use_tls':True,'provider_key':'gmail'}

    if request.method == 'POST':
        action = request.form.get('action','save')

        if action == 'test':
            # مطابق لـ v54 EmailConfigWindow test button
            from utils.email_helper import test_smtp
            ok, msg = test_smtp(
                request.form.get('smtp_server',''),
                request.form.get('smtp_port',587),
                request.form.get('sender_email',''),
                request.form.get('sender_password',''),
                request.form.get('use_tls') == 'on',
            )
            flash_msg(('✅ ' if ok else '❌ ') + msg, 'success' if ok else 'danger')
            return redirect(url_for('admin.settings'))

        # Save config — مثل v54 EmailSystem.save_config
        new_cfg = {
            'provider_key':   request.form.get('provider_key','gmail'),
            'smtp_server':    request.form.get('smtp_server',''),
            'smtp_port':      int(request.form.get('smtp_port',587)),
            'sender_email':   request.form.get('sender_email',''),
            'sender_password':request.form.get('sender_password',''),
            'sender_name':    request.form.get('sender_name','ARS Applied Reservation System'),
            'use_tls':        request.form.get('use_tls') == 'on',
        }
        with open(CONFIG_EMAIL,'w',encoding='utf-8') as f:
            json.dump(new_cfg, f, ensure_ascii=False, indent=2)
        syslog('SAVE_EMAIL_CONFIG', f"provider: {new_cfg['provider_key']}")
        flash_msg('✅ تم حفظ إعدادات البريد الإلكتروني', 'success')
        return redirect(url_for('admin.settings'))

    return render_template('admin/settings.html',
        cfg=cfg, providers=PROVIDERS)


# ── Ticker API — serves full ticker config to frontend ────────────────────────
@admin_bp.route('/api/ticker')
def ticker_api():
    from flask import jsonify
    ticker = _load_ticker()
    lang  = request.args.get('lang','ar')
    key   = 'feeds_ar' if lang == 'ar' else 'feeds_en'
    if lang == 'ar':
        msgs = ticker.get('feeds_ar', ticker.get('ar', ['مرحباً بكم في نظام ARS'])) or ['مرحباً بكم في نظام ARS']
    else:
        msgs = ticker.get('feeds_en', []) or ['Welcome to ARS Reservation Management System']
    return jsonify({
        'messages': msgs,
        'text':     ' ◆ '.join(msgs),
        'bg':       ticker.get('bg', ''),
        'fg':       ticker.get('fg', '#F2C99A'),
        'font':     ticker.get('font', 'Tahoma'),
        'size':     ticker.get('size', 15),
        'speed':    ticker.get('speed', 35),
        'opacity':  ticker.get('opacity', 0),
    })

