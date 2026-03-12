"""
مسارات المصادقة: تسجيل الدخول، الخروج، التسجيل
"""

import hashlib
import json
import os
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, session)
from flask_login import login_user, logout_user, login_required, current_user
from models.database import User, Role, SystemLog, LoginLog
from utils.helpers import get_db

auth_bp = Blueprint('auth', __name__)


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


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
        return redirect(url_for('reservations.index'))

    # تحقق من تعليق النظام
    maint = _load_maintenance()
    if maint.get('system_suspended'):
        flash(maint.get('suspend_message', 'النظام معلق مؤقتاً للصيانة'), 'danger')

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        db       = get_db()

        user = db.query(User).filter_by(username=username).first()

        # تحقق من تعليق النظام — المدير يتجاوزه
        if maint.get('system_suspended'):
            is_admin = user and user.role and user.role.name in ('مدير النظام', 'admin')
            if not is_admin:
                flash('النظام معلق مؤقتاً. تواصل مع المدير.', 'danger')
                return redirect(url_for('auth.login'))

        if not user or user.password_hash != hash_password(password):
            _log_login(db, user, False, 'wrong_credentials', request)
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash('حسابك موقوف. تواصل مع المدير.', 'danger')
            return redirect(url_for('auth.login'))

        # تحقق من تفعيل البريد الإلكتروني (إذا كان مطلوباً)
        if not user.is_verified:
            flash('بريدك الإلكتروني غير مفعّل. تحقق من بريدك أو تواصل مع المدير.', 'warning')
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

        next_page = request.args.get('next')
        return redirect(next_page or url_for('reservations.index'))

    return render_template('auth/login.html')


# ── Logout ────────────────────────────────────────────────────────────────────
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('auth.login'))


# ── Register ──────────────────────────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('reservations.index'))

    maint = _load_maintenance()
    if maint.get('registration_suspended'):
        flash('التسجيل معلق مؤقتاً. تواصل مع المدير.', 'warning')
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
        if len(password) < 6:
            errors.append('كلمة المرور يجب أن تكون 6 أحرف على الأقل')
        if db.query(User).filter_by(username=username).first():
            errors.append('اسم المستخدم مستخدم مسبقاً')
        if db.query(User).filter_by(email=email).first():
            errors.append('البريد الإلكتروني مستخدم مسبقاً')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/register.html',
                                   form=request.form)

        # الدور الافتراضي
        default_role = (db.query(Role)
                        .filter(Role.name.in_(['مستخدم', 'user', 'User']))
                        .first())
        user = User(
            username      = username,
            email         = email,
            full_name     = full_name,
            password_hash = hash_password(password),
            phone         = phone,
            role_id       = default_role.id if default_role else None,
            is_verified   = False,
            is_active     = True,
        )
        db.add(user)
        db.commit()

        log = SystemLog(action='REGISTER_WEB',
                        description=f'تسجيل جديد عبر الويب: {username}',
                        user_id=user.id, level='info')
        db.add(log)
        db.commit()

        # تفعيل الحساب فوراً — البريد يُرسل في الخلفية إن كان مفعّلاً
        user.is_verified = True
        db.commit()

        # البريد اختياري — الحساب مفعّل تلقائياً

        flash('تم التسجيل بنجاح! يمكنك تسجيل الدخول الآن.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form={})


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
            if user.password_hash != hash_password(old_pw):
                flash('كلمة المرور الحالية غير صحيحة', 'danger')
                return redirect(url_for('auth.profile'))
            if len(new_pw) < 6:
                flash('كلمة المرور الجديدة قصيرة جداً', 'danger')
                return redirect(url_for('auth.profile'))
            user.password_hash = hash_password(new_pw)
            flash('تم تغيير كلمة المرور', 'success')

        db.commit()
        flash('تم حفظ التغييرات', 'success')
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
                flash('البريد الإلكتروني غير مسجل', 'danger')
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
                flash(f'✅ تم إرسال كود التحقق إلى {email}', 'success')
            else:
                flash(f'📧 البريد غير مفعّل — كود التحقق (للاختبار): <strong>{code}</strong>', 'info')
            return render_template('auth/forgot_password.html', step=2, email=email)

        elif step == '2':
            code    = request.form.get('code','').strip()
            stored  = session.get('reset_code','')
            expires = session.get('reset_expires','')
            if expires and datetime.fromisoformat(expires) < datetime.now():
                flash('انتهت صلاحية الكود. أعد المحاولة.', 'danger')
                session.pop('reset_code', None)
                return render_template('auth/forgot_password.html', step=1)
            if code != stored:
                flash('الكود غير صحيح', 'danger')
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
                flash('كلمتا المرور غير متطابقتين', 'danger')
                return render_template('auth/forgot_password.html', step=3)
            if len(new_pw) < 6:
                flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
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
            flash('تم تغيير كلمة المرور بنجاح. يمكنك تسجيل الدخول.', 'success')
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
