"""
مسارات المصادقة: تسجيل الدخول، الخروج، التسجيل
"""

import hashlib
from werkzeug.security import generate_password_hash, check_password_hash

def _legacy_hash(pw):
    """Old SHA-256 hash for backward compatibility"""
    return hashlib.sha256(pw.encode()).hexdigest()
import json
import os
from datetime import datetime
from utils.flash_helper import flash_msg
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, session)
from flask_login import login_user, logout_user, login_required, current_user
from models.database import User, Role, SystemLog, LoginLog
from utils.helpers import get_db

auth_bp = Blueprint('auth', __name__)


def hash_password(pw: str) -> str:
    return generate_password_hash(pw, method="pbkdf2:sha256", salt_length=16)

def verify_password(pw: str, stored_hash: str) -> bool:
    """Verify password - supports both old SHA-256 and new pbkdf2"""
    # New pbkdf2 format starts with 'pbkdf2:'
    if stored_hash.startswith('pbkdf2:'):
        return check_password_hash(stored_hash, pw)
    # Legacy SHA-256 (64 hex chars)
    return stored_hash == _legacy_hash(pw)


def _log_login(db, user, success, reason='', request=None):
    try:
        ip = (request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
              or request.remote_addr) if request else ''
        entry = LoginLog(
            user_id    = user.id if user else None,
            username   = user.username if user else 'unknown',
            ip_address = ip,
            platform   = request.user_agent.string[:200] if request else '',
            success    = success,
            reason     = reason,
        )
        db.add(entry)
        db.commit()
    except Exception:
        pass


# ── Login ─────────────────────────────────────────────────────────────────────
@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))

    # تحقق من تعليق النظام
    maint = _load_maintenance()
    if maint.get('system_suspended'):
        flash_msg(maint.get('suspend_message', 'النظام معلق مؤقتاً للصيانة'), 'danger')

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        db       = get_db()

        user = db.query(User).filter_by(username=username).first()

        # تحقق من تعليق النظام — المدير يتجاوزه
        if maint.get('system_suspended'):
            is_admin = user and user.role and user.role.name in ('مدير النظام', 'admin')
            if not is_admin:
                flash_msg('النظام معلق مؤقتاً. تواصل مع المدير.', 'danger')
                return redirect(url_for('auth.login'))

        if not user or not verify_password(password, user.password_hash):
            _log_login(db, user, False, 'wrong_credentials', request)
            flash_msg('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash_msg('حسابك موقوف. تواصل مع المدير.', 'danger')
            return redirect(url_for('auth.login'))

        # تحقق من تفعيل البريد الإلكتروني (إذا كان مطلوباً)
        if not user.is_verified:
            flash_msg('بريدك الإلكتروني غير مفعّل. تحقق من بريدك أو تواصل مع المدير.', 'warning')
            _log_login(db, user, False, 'not_verified', request)
            return redirect(url_for('auth.login'))

        # تحديث آخر دخول — non-fatal
        try:
            user.last_login  = datetime.now()
            user.login_count = (user.login_count or 0) + 1
            db.commit()
        except Exception:
            db.rollback()

        try:
            _log_login(db, user, True, '', request)
        except Exception:
            pass

        login_user(user, remember=request.form.get('remember') == 'on')

        # Sync session language to user.language so emails arrive in correct language
        _sess_lang = session.get('lang', 'ar')
        if user.language != _sess_lang:
            user.language = _sess_lang
            db.commit()

        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        # Regular users go to reservations, admins/managers go to dashboard
        from utils.helpers import PermCheck
        p = PermCheck()
        if p.is_admin_or_manager():
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('reservations.index'))

    return render_template('auth/login.html')


# ── Logout ────────────────────────────────────────────────────────────────────
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    from flask import request as _req
    if _req.args.get('reason') == 'timeout':
        flash_msg('⏱️ تم تسجيل خروجك تلقائياً بسبب عدم النشاط', 'warning')
    else:
        flash_msg('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('auth.login'))


# ── Register ──────────────────────────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))

    maint = _load_maintenance()
    if maint.get('registration_suspended'):
        flash_msg('التسجيل معلق مؤقتاً. تواصل مع المدير.', 'warning')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        db        = get_db()
        username  = request.form.get('username',  '').strip()
        email     = request.form.get('email',     '').strip()
        full_name = request.form.get('full_name', '').strip()
        phone     = request.form.get('phone',     '').strip()
        password  = request.form.get('password',  '').strip()
        password2 = request.form.get('password2', '').strip()

        errors = []
        if not all([username, email, full_name, password]):
            errors.append('جميع الحقول مطلوبة')
        if password != password2:
            errors.append('كلمتا المرور غير متطابقتين')
        if len(password) < 8:
            errors.append('كلمة المرور يجب أن تكون 8 أحرف على الأقل')
        if db.query(User).filter_by(username=username).first():
            errors.append('اسم المستخدم مستخدم مسبقاً')
        if db.query(User).filter_by(email=email).first():
            errors.append('البريد الإلكتروني مستخدم مسبقاً')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/register.html', form=request.form)

        # الدور الافتراضي
        default_role = (db.query(Role)
                        .filter(Role.name.in_(['مستخدم', 'user', 'User']))
                        .first())

        # توليد كود التحقق
        import random, string
        from datetime import timedelta
        code = ''.join(random.choices(string.digits, k=6))
        expiry = datetime.now() + timedelta(minutes=15)

        user = User(
            username           = username,
            email              = email,
            full_name          = full_name,
            password_hash      = hash_password(password),
            phone              = phone,
            role_id            = default_role.id if default_role else None,
            is_verified        = False,
            is_active          = True,
            verification_code  = code,
            verification_expiry= expiry,
        )
        db.add(user)
        db.commit()

        log = SystemLog(action='REGISTER_WEB',
                        description=f'تسجيل جديد عبر الويب: {username}',
                        user_id=user.id, level='info')
        db.add(log)
        db.commit()

        # إرسال كود التحقق
        email_ok = False
        email_err = ''
        try:
            from utils.email_helper import send_verification_code
            email_ok = send_verification_code(email, code, full_name)
        except Exception as e:
            email_err = str(e)
            print(f'[EMAIL ERROR] {e}')

        _lang = session.get('lang', 'ar')
        if email_ok:
            _msg = f'📧 Verification code sent to {email}' if _lang == 'en' else f'📧 تم إرسال كود التحقق إلى {email}'
            flash_msg(_msg, 'info')
        else:
            # Activate immediately if email failed
            user.is_verified = True
            db.commit()
            print(f'[EMAIL FAILED] activating user directly. Error: {email_err}')
            flash_msg('تم التسجيل بنجاح! يمكنك تسجيل الدخول الآن.' if _lang != 'en' else 'Registered successfully! You can sign in now.', 'success')
            return redirect(url_for('auth.login'))

        session['pending_verify_user_id'] = user.id
        return redirect(url_for('auth.verify_email'))

    return render_template('auth/register.html', form={})


@auth_bp.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    user_id = session.get('pending_verify_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))

    db   = get_db()
    user = db.query(User).get(user_id)
    if not user:
        return redirect(url_for('auth.login'))

    _lang = session.get('lang', 'ar')
    def _t(ar, en): return en if _lang == 'en' else ar

    if user.is_verified:
        session.pop('pending_verify_user_id', None)
        flash_msg(_t('تم التحقق مسبقاً، سجّل دخولك.', 'Already verified. Please sign in.'), 'info')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        entered = request.form.get('code', '').strip()

        # إعادة إرسال
        if request.form.get('resend'):
            import random, string
            from datetime import timedelta
            code   = ''.join(random.choices(string.digits, k=6))
            expiry = datetime.now() + timedelta(minutes=15)
            user.verification_code   = code
            user.verification_expiry = expiry
            db.commit()
            try:
                from utils.email_helper import send_verification_code
                send_verification_code(user.email, code, user.full_name)
                flash_msg(_t('📧 تم إعادة إرسال الكود', '📧 Code resent successfully'), 'info')
            except:
                flash_msg(_t('فشل إعادة الإرسال', 'Failed to resend code'), 'danger')
            return redirect(url_for('auth.verify_email'))

        # التحقق من الكود
        if not entered:
            flash_msg(_t('أدخل الكود', 'Please enter the code'), 'danger')
        elif user.verification_code != entered:
            flash_msg(_t('❌ الكود غير صحيح', '❌ Incorrect code'), 'danger')
        elif user.verification_expiry and datetime.now() > user.verification_expiry:
            flash_msg(_t('❌ انتهت صلاحية الكود — اطلب كوداً جديداً', '❌ Code expired — request a new one'), 'danger')
        else:
            user.is_verified        = True
            user.verification_code  = None
            user.verification_expiry= None
            db.commit()
            session.pop('pending_verify_user_id', None)
            flash_msg(_t('✅ تم تفعيل حسابك بنجاح! سجّل دخولك الآن.', '✅ Account activated! You can sign in now.'), 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/verify_email.html',
                           email=user.email, user=user)


# ── Profile ───────────────────────────────────────────────────────────────────
@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone     = request.form.get('phone', '').strip()
        language  = request.form.get('language', 'ar')
        old_pw    = request.form.get('old_password', '')
        new_pw    = request.form.get('new_password', '')

        user = db.query(User).get(current_user.id)
        if full_name: user.full_name = full_name
        if phone:     user.phone     = phone
        user.language = language

        if old_pw and new_pw:
            if not verify_password(old_pw, user.password_hash):
                flash_msg('كلمة المرور الحالية غير صحيحة', 'danger')
                return redirect(url_for('auth.profile'))
            if len(new_pw) < 6:
                flash_msg('كلمة المرور الجديدة قصيرة جداً', 'danger')
                return redirect(url_for('auth.profile'))
            user.password_hash = hash_password(new_pw)
            flash_msg('تم تغيير كلمة المرور', 'success')

        db.commit()
        flash_msg('تم حفظ التغييرات', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html', user=current_user)



# ── Forgot / Reset Password ────────────────────────────────────────────────────
import random
import string

def _gen_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

@auth_bp.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'POST':
        step = request.form.get('step','1')
        db   = get_db()

        if step == '1':
            email = request.form.get('email','').strip()
            user  = db.query(User).filter_by(email=email).first()
            if not user:
                flash_msg('البريد الإلكتروني غير مسجل', 'danger')
                return render_template('auth/forgot_password.html', step=1)
            code = _gen_code()
            from datetime import timedelta
            expires = datetime.now() + timedelta(minutes=10)
            session['reset_email']   = email
            session['reset_code']    = code
            session['reset_expires'] = expires.isoformat()
            # Try to send email; fall back to showing code in UI
            email_sent = False
            try:
                from utils.email_helper import send_reset_code
                email_sent = send_reset_code(email, code)
            except Exception:
                pass
            if email_sent:
                flash_msg(f'✅ تم إرسال كود التحقق إلى {email}', 'success')
            else:
                flash_msg(f'📧 البريد غير مفعّل — كود التحقق (للاختبار): <strong>{code}</strong>', 'info')
            return render_template('auth/forgot_password.html', step=2, email=email)

        elif step == '2':
            code    = request.form.get('code','').strip()
            stored  = session.get('reset_code','')
            expires = session.get('reset_expires','')
            if expires and datetime.fromisoformat(expires) < datetime.now():
                flash_msg('انتهت صلاحية الكود. أعد المحاولة.', 'danger')
                session.pop('reset_code', None)
                return render_template('auth/forgot_password.html', step=1)
            if code != stored:
                flash_msg('الكود غير صحيح', 'danger')
                return render_template('auth/forgot_password.html', step=2,
                                       email=session.get('reset_email',''))
            session['reset_verified'] = True
            return render_template('auth/forgot_password.html', step=3)

        elif step == '3':
            if not session.get('reset_verified'):
                return redirect(url_for('auth.forgot_password'))
            new_pw  = request.form.get('new_password','').strip()
            new_pw2 = request.form.get('new_password2','').strip()
            if new_pw != new_pw2:
                flash_msg('كلمتا المرور غير متطابقتين', 'danger')
                return render_template('auth/forgot_password.html', step=3)
            if len(new_pw) < 6:
                flash_msg('كلمة المرور يجب أن تكون 8 أحرف على الأقل', 'danger')
                return render_template('auth/forgot_password.html', step=3)
            db   = get_db()
            email = session.get('reset_email','')
            user  = db.query(User).filter_by(email=email).first()
            if user:
                user.password_hash = hash_password(new_pw)
                db.commit()
            session.pop('reset_code', None)
            session.pop('reset_verified', None)
            session.pop('reset_email', None)
            flash_msg('تم تغيير كلمة المرور بنجاح. يمكنك تسجيل الدخول.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html', step=1)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_maintenance():
    cfg_path = os.environ.get('MAINTENANCE_CONFIG', 'maintenance_config.json')
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


# ── Keep-alive endpoint (called by auto-logout JS) ────────────────────────────
from flask import jsonify as _jsonify
@auth_bp.route('/keep-alive', methods=['POST'])
def keep_alive():
    from flask_login import current_user
    if current_user.is_authenticated:
        return _jsonify({'ok': True})
    return _jsonify({'ok': False}), 401
