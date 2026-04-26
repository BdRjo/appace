"""
Mobile API — JWT-based endpoints for ARS Mobile App
Prefix: /mobile-api
"""
import os
import jwt
import json
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, request, jsonify, current_app, g
from models.database import User, Reservation, Venue, Location, Notification
from utils.helpers import get_db

mobile_api_bp = Blueprint('mobile_api', __name__, url_prefix='/mobile-api')

# ── JWT helpers ───────────────────────────────────────────────────────────────

SECRET_KEY     = os.environ.get('MOBILE_JWT_SECRET', 'ars-mobile-secret-change-in-prod')
TOKEN_EXPIRY_HOURS = 72


def _make_token(user_id: int) -> str:
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')


def _verify_token(token: str):
    """Returns user_id if valid, else None."""
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return data.get('user_id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Token required'}), 401
        token = auth_header[7:]
        user_id = _verify_token(token)
        if not user_id:
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        db = get_db()
        user = db.query(User).filter_by(id=user_id, is_active=True).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 401
        g.current_mobile_user = user
        return f(*args, **kwargs)
    return decorated


def _user_dict(user):
    return {
        'id':        user.id,
        'username':  user.username,
        'full_name': user.full_name or user.username,
        'email':     user.email or '',
        'phone':     user.phone or '',
        'role':      user.role.name if user.role else '',
        'language':  user.language or 'ar',
    }


# ── Auth ──────────────────────────────────────────────────────────────────────

@mobile_api_bp.route('/login', methods=['POST'])
def login():
    data     = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required'}), 400

    db   = get_db()
    user = db.query(User).filter_by(username=username).first()

    if not user:
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

    # Support both pbkdf2 and legacy SHA-256
    from werkzeug.security import check_password_hash
    import hashlib as _hl
    if user.password_hash.startswith('pbkdf2:'):
        valid = check_password_hash(user.password_hash, password)
    else:
        valid = user.password_hash == _hl.sha256(password.encode()).hexdigest()

    if not valid:
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

    if not user.is_active:
        return jsonify({'success': False, 'message': 'Account is suspended'}), 403

    if not user.is_verified:
        return jsonify({'success': False, 'message': 'Email not verified'}), 403

    # Update last login
    try:
        user.last_login  = datetime.now()
        user.login_count = (user.login_count or 0) + 1
        db.commit()
    except Exception:
        db.rollback()

    token = _make_token(user.id)
    return jsonify({'success': True, 'token': token, 'user': _user_dict(user)})


@mobile_api_bp.route('/logout', methods=['POST'])
@token_required
def logout():
    # Token is stateless — client just deletes it
    return jsonify({'success': True})


# ── Profile ───────────────────────────────────────────────────────────────────

@mobile_api_bp.route('/profile', methods=['GET'])
@token_required
def get_profile():
    return jsonify({'success': True, 'user': _user_dict(g.current_mobile_user)})


@mobile_api_bp.route('/profile', methods=['PUT'])
@token_required
def update_profile():
    data      = request.get_json(silent=True) or {}
    db        = get_db()
    user      = db.query(User).get(g.current_mobile_user.id)
    if data.get('full_name'): user.full_name = data['full_name']
    if data.get('phone'):     user.phone     = data['phone']
    if data.get('language'):  user.language  = data['language']
    db.commit()
    return jsonify({'success': True, 'user': _user_dict(user)})


@mobile_api_bp.route('/change-password', methods=['POST'])
@token_required
def change_password():
    data        = request.get_json(silent=True) or {}
    old_pw      = data.get('oldPassword', '')
    new_pw      = data.get('newPassword', '')
    db          = get_db()
    user        = db.query(User).get(g.current_mobile_user.id)

    from werkzeug.security import check_password_hash, generate_password_hash
    import hashlib as _hl
    if user.password_hash.startswith('pbkdf2:'):
        valid = check_password_hash(user.password_hash, old_pw)
    else:
        valid = user.password_hash == _hl.sha256(old_pw.encode()).hexdigest()

    if not valid:
        return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400
    if len(new_pw) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

    user.password_hash = generate_password_hash(new_pw, method='pbkdf2:sha256', salt_length=16)
    db.commit()
    return jsonify({'success': True})


# ── Dashboard ─────────────────────────────────────────────────────────────────

@mobile_api_bp.route('/dashboard', methods=['GET'])
@token_required
def dashboard():
    db   = get_db()
    user = g.current_mobile_user
    q    = db.query(Reservation).filter_by(user_id=user.id)
    return jsonify({
        'success': True,
        'stats': {
            'total':    q.count(),
            'pending':  q.filter_by(status='pending').count(),
            'approved': q.filter_by(status='approved').count(),
            'rejected': q.filter_by(status='rejected').count(),
        }
    })


# ── Bookings ──────────────────────────────────────────────────────────────────

def _reservation_dict(r):
    return {
        'id':             r.id,
        'booking_number': r.booking_number,
        'title':          r.title,
        'start_time':     r.start_time.isoformat() if r.start_time else '',
        'end_time':       r.end_time.isoformat()   if r.end_time   else '',
        'status':         r.status,
        'venue':          r.venue.name if r.venue else '',
        'venue_id':       r.venue_id,
        'notes':          r.requester_notes or '',
        'created_at':     r.created_at.isoformat() if r.created_at else '',
    }


@mobile_api_bp.route('/bookings', methods=['GET'])
@token_required
def get_bookings():
    db     = get_db()
    user   = g.current_mobile_user
    status = request.args.get('status')
    q      = db.query(Reservation).filter_by(user_id=user.id)
    if status:
        q = q.filter_by(status=status)
    bookings = q.order_by(Reservation.created_at.desc()).all()
    return jsonify({'success': True, 'bookings': [_reservation_dict(r) for r in bookings]})


@mobile_api_bp.route('/bookings/<int:booking_id>', methods=['GET'])
@token_required
def get_booking(booking_id):
    db      = get_db()
    user    = g.current_mobile_user
    booking = db.query(Reservation).filter_by(id=booking_id, user_id=user.id).first()
    if not booking:
        return jsonify({'success': False, 'message': 'Booking not found'}), 404
    return jsonify({'success': True, 'booking': _reservation_dict(booking)})


@mobile_api_bp.route('/create-booking', methods=['POST'])
@token_required
def create_booking():
    data  = request.get_json(silent=True) or {}
    db    = get_db()
    user  = g.current_mobile_user

    required = ['title', 'venue_id', 'start_time', 'end_time']
    for field in required:
        if not data.get(field):
            return jsonify({'success': False, 'message': f'{field} is required'}), 400

    try:
        start = datetime.fromisoformat(data['start_time'])
        end   = datetime.fromisoformat(data['end_time'])
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format. Use ISO format.'}), 400

    if end <= start:
        return jsonify({'success': False, 'message': 'End time must be after start time'}), 400

    venue = db.query(Venue).filter_by(id=data['venue_id'], is_active=True).first()
    if not venue:
        return jsonify({'success': False, 'message': 'Venue not found'}), 404

    # Check for conflicts
    conflict = db.query(Reservation).filter(
        Reservation.venue_id == venue.id,
        Reservation.status.in_(['pending', 'approved']),
        Reservation.start_time < end,
        Reservation.end_time   > start,
    ).first()
    if conflict:
        return jsonify({'success': False, 'message': 'Venue is already booked for this time'}), 409

    # Generate booking number
    import random
    booking_number = f"BK-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000,9999)}"

    reservation = Reservation(
        booking_number   = booking_number,
        title            = data['title'],
        venue_id         = venue.id,
        user_id          = user.id,
        start_time       = start,
        end_time         = end,
        status           = 'pending',
        requester_notes  = data.get('notes', ''),
        booking_type     = data.get('booking_type', 'official'),
    )
    db.add(reservation)
    db.commit()
    return jsonify({'success': True, 'booking': _reservation_dict(reservation)}), 201


@mobile_api_bp.route('/bookings/<int:booking_id>', methods=['PUT'])
@token_required
def update_booking(booking_id):
    db      = get_db()
    user    = g.current_mobile_user
    booking = db.query(Reservation).filter_by(id=booking_id, user_id=user.id).first()
    if not booking:
        return jsonify({'success': False, 'message': 'Booking not found'}), 404
    if booking.status != 'pending':
        return jsonify({'success': False, 'message': 'Only pending bookings can be edited'}), 400

    data = request.get_json(silent=True) or {}
    if data.get('title'):          booking.title           = data['title']
    if data.get('notes') is not None: booking.requester_notes = data['notes']
    if data.get('start_time'):
        booking.start_time = datetime.fromisoformat(data['start_time'])
    if data.get('end_time'):
        booking.end_time   = datetime.fromisoformat(data['end_time'])
    db.commit()
    return jsonify({'success': True, 'booking': _reservation_dict(booking)})


@mobile_api_bp.route('/bookings/<int:booking_id>', methods=['DELETE'])
@token_required
def cancel_booking(booking_id):
    db      = get_db()
    user    = g.current_mobile_user
    booking = db.query(Reservation).filter_by(id=booking_id, user_id=user.id).first()
    if not booking:
        return jsonify({'success': False, 'message': 'Booking not found'}), 404
    if booking.status in ('rejected', 'cancelled'):
        return jsonify({'success': False, 'message': 'Booking is already cancelled'}), 400

    booking.status             = 'cancelled'
    booking.cancelled_by       = user.id
    booking.cancelled_at       = datetime.now()
    booking.cancellation_reason = request.get_json(silent=True, force=True).get('reason', '') if request.data else ''
    db.commit()
    return jsonify({'success': True})


# ── Venues ────────────────────────────────────────────────────────────────────

@mobile_api_bp.route('/venues', methods=['GET'])
@token_required
def get_venues():
    db     = get_db()
    venues = db.query(Venue).filter_by(is_active=True).order_by(Venue.name).all()
    return jsonify({'success': True, 'venues': [{
        'id':       v.id,
        'name':     v.name,
        'capacity': v.capacity,
        'location': v.location.name if v.location else '',
        'notes':    v.notes or '',
    } for v in venues]})


@mobile_api_bp.route('/venues/<int:venue_id>', methods=['GET'])
@token_required
def get_venue(venue_id):
    db    = get_db()
    venue = db.query(Venue).filter_by(id=venue_id, is_active=True).first()
    if not venue:
        return jsonify({'success': False, 'message': 'Venue not found'}), 404
    return jsonify({'success': True, 'venue': {
        'id':        venue.id,
        'name':      venue.name,
        'capacity':  venue.capacity,
        'location':  venue.location.name if venue.location else '',
        'equipment': venue.equipment or '',
        'notes':     venue.notes or '',
    }})


@mobile_api_bp.route('/venues/<int:venue_id>/availability', methods=['GET'])
@token_required
def check_availability(venue_id):
    db        = get_db()
    date_str  = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'message': 'date param required'}), 400
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'success': False, 'message': 'Date format must be YYYY-MM-DD'}), 400

    day_start = date.replace(hour=0,  minute=0,  second=0)
    day_end   = date.replace(hour=23, minute=59, second=59)

    bookings = db.query(Reservation).filter(
        Reservation.venue_id == venue_id,
        Reservation.status.in_(['pending', 'approved']),
        Reservation.start_time >= day_start,
        Reservation.start_time <= day_end,
    ).order_by(Reservation.start_time).all()

    return jsonify({'success': True, 'bookings': [_reservation_dict(r) for r in bookings]})


# ── Notifications ─────────────────────────────────────────────────────────────
# Uses the Reservation table to generate smart notifications for the user

@mobile_api_bp.route('/notifications', methods=['GET'])
@token_required
def get_notifications():
    db   = get_db()
    user = g.current_mobile_user

    recent = db.query(Reservation).filter_by(user_id=user.id)\
               .order_by(Reservation.created_at.desc()).limit(20).all()

    notifications = []
    for r in recent:
        if r.status == 'approved':
            msg  = f'Your booking "{r.title}" has been approved'
            icon = '✅'
        elif r.status == 'rejected':
            msg  = f'Your booking "{r.title}" was rejected'
            icon = '❌'
        elif r.status == 'pending':
            msg  = f'Your booking "{r.title}" is pending approval'
            icon = '⏳'
        else:
            continue
        notifications.append({
            'id':         r.id,
            'message':    f'{icon} {msg}',
            'status':     r.status,
            'booking_id': r.id,
            'created_at': r.created_at.isoformat() if r.created_at else '',
            'is_read':    r.status not in ('pending',),
        })

    return jsonify({'success': True, 'notifications': notifications})


@mobile_api_bp.route('/notifications/<int:notification_id>/read', methods=['PUT'])
@token_required
def mark_notification_read(notification_id):
    # Stateless — client tracks read state locally
    return jsonify({'success': True})


@mobile_api_bp.route('/notifications/read-all', methods=['PUT'])
@token_required
def mark_all_read():
    return jsonify({'success': True})


@mobile_api_bp.route('/register-push-token', methods=['POST'])
@token_required
def register_push_token():
    # Store for future push notification use
    # For now just acknowledge
    return jsonify({'success': True})


# ── Reports ───────────────────────────────────────────────────────────────────

@mobile_api_bp.route('/reports/monthly', methods=['GET'])
@token_required
def monthly_report():
    db    = get_db()
    user  = g.current_mobile_user
    year  = int(request.args.get('year',  datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))

    reservations = db.query(Reservation).filter(
        Reservation.user_id == user.id,
    ).all()

    filtered = [r for r in reservations
                if r.start_time and r.start_time.year == year and r.start_time.month == month]

    by_status = {}
    for r in filtered:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    return jsonify({
        'success': True,
        'year':    year,
        'month':   month,
        'total':   len(filtered),
        'by_status': by_status,
        'bookings': [_reservation_dict(r) for r in filtered],
    })


@mobile_api_bp.route('/reports/yearly', methods=['GET'])
@token_required
def yearly_report():
    db   = get_db()
    user = g.current_mobile_user
    year = int(request.args.get('year', datetime.now().year))

    reservations = db.query(Reservation).filter_by(user_id=user.id).all()
    filtered     = [r for r in reservations if r.start_time and r.start_time.year == year]

    by_month = {}
    for r in filtered:
        m = r.start_time.month
        if m not in by_month:
            by_month[m] = {'total': 0, 'pending': 0, 'approved': 0, 'rejected': 0}
        by_month[m]['total'] += 1
        by_month[m][r.status] = by_month[m].get(r.status, 0) + 1

    return jsonify({
        'success':  True,
        'year':     year,
        'total':    len(filtered),
        'by_month': by_month,
    })


# ═══════════════════════════════════════════════════════════════════════════
#  NEW ENDPOINTS — Register, Forgot Password, Resend OTP
#  Fixes: Problem 1 — Register & Forgot Password not working
# ═══════════════════════════════════════════════════════════════════════════

import random
import string

def _gen_otp(length=6):
    """Generate a numeric OTP."""
    return ''.join(random.choices(string.digits, k=length))


@mobile_api_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new mobile user account.
    Body: { username, password, full_name, email, phone? }
    Returns: { success, message } — user must verify email before login.
    """
    data     = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    full_name= data.get('full_name', '').strip()
    email    = data.get('email', '').strip().lower()
    phone    = data.get('phone', '').strip()

    # Validation
    if not username or not password or not email or not full_name:
        return jsonify({'success': False, 'message': 'الاسم الكامل واسم المستخدم والبريد الإلكتروني وكلمة المرور مطلوبة'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'}), 400

    db = get_db()

    # Check username uniqueness
    if db.query(User).filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'اسم المستخدم مستخدم بالفعل — اختر اسماً آخر'}), 409

    # Check email uniqueness
    if db.query(User).filter(User.email == email).first():
        return jsonify({'success': False, 'message': 'البريد الإلكتروني مسجّل مسبقاً'}), 409

    from werkzeug.security import generate_password_hash
    otp     = _gen_otp(6)
    expiry  = datetime.now() + timedelta(minutes=30)

    # Default role = staff (lowest privilege)
    default_role = db.query(__import__('models.database', fromlist=['Role']).Role).filter_by(name='staff').first()

    new_user = User(
        username          = username,
        full_name         = full_name,
        email             = email,
        phone             = phone or None,
        password_hash     = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16),
        is_verified       = False,
        is_active         = True,
        verification_code  = otp,
        verification_expiry= expiry,
        language          = 'ar',
        role_id           = default_role.id if default_role else None,
    )
    db.add(new_user)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': 'خطأ في إنشاء الحساب — حاول مرة أخرى'}), 500

    # Send verification email
    try:
        from utils.email_helper import send_verification_code
        send_verification_code(email, otp, full_name, lang='ar')
    except Exception:
        pass  # Don't fail registration if email fails

    return jsonify({
        'success': True,
        'message': 'تم إنشاء الحساب — تحقق من بريدك الإلكتروني لتفعيل الحساب',
        'requires_verification': True,
    }), 201


@mobile_api_bp.route('/verify-email', methods=['POST'])
def verify_email():
    """
    Verify email OTP after registration.
    Body: { email, otp }
    """
    data  = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    otp   = data.get('otp', '').strip()

    if not email or not otp:
        return jsonify({'success': False, 'message': 'البريد الإلكتروني والرمز مطلوبان'}), 400

    db   = get_db()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return jsonify({'success': False, 'message': 'البريد الإلكتروني غير موجود'}), 404

    if user.is_verified:
        return jsonify({'success': True, 'message': 'الحساب مفعّل بالفعل'})

    if user.verification_code != otp:
        return jsonify({'success': False, 'message': 'الرمز غير صحيح'}), 400

    if user.verification_expiry and datetime.now() > user.verification_expiry:
        return jsonify({'success': False, 'message': 'انتهت صلاحية الرمز — اطلب رمزاً جديداً'}), 400

    user.is_verified        = True
    user.verification_code  = None
    user.verification_expiry= None
    db.commit()

    # Auto-login after verification
    token = _make_token(user.id)
    return jsonify({'success': True, 'message': 'تم تفعيل الحساب بنجاح', 'token': token, 'user': _user_dict(user)})


@mobile_api_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    """Resend verification OTP. Body: { email }"""
    data  = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'success': False, 'message': 'البريد الإلكتروني مطلوب'}), 400

    db   = get_db()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return jsonify({'success': False, 'message': 'البريد الإلكتروني غير موجود'}), 404
    if user.is_verified:
        return jsonify({'success': True, 'message': 'الحساب مفعّل بالفعل'})

    otp                     = _gen_otp(6)
    user.verification_code  = otp
    user.verification_expiry= datetime.now() + timedelta(minutes=30)
    db.commit()

    try:
        from utils.email_helper import send_verification_code
        send_verification_code(email, otp, user.full_name or user.username, lang='ar')
    except Exception:
        pass

    return jsonify({'success': True, 'message': 'تم إرسال رمز جديد إلى بريدك الإلكتروني'})


@mobile_api_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """
    Request password reset OTP.
    Body: { email }
    """
    data  = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'success': False, 'message': 'البريد الإلكتروني مطلوب'}), 400

    db   = get_db()
    user = db.query(User).filter(User.email == email).first()

    # Always return success to prevent email enumeration
    if not user or not user.is_active:
        return jsonify({'success': True, 'message': 'إذا كان البريد مسجّلاً ستصل رسالة قريباً'})

    otp                  = _gen_otp(6)
    user.reset_code      = otp
    user.reset_code_expiry = datetime.now() + timedelta(minutes=15)
    db.commit()

    try:
        from utils.email_helper import send_reset_code
        send_reset_code(email, otp, lang=user.language or 'ar')
    except Exception:
        pass

    return jsonify({'success': True, 'message': 'تم إرسال رمز إعادة التعيين إلى بريدك الإلكتروني'})


@mobile_api_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """
    Reset password using OTP.
    Body: { email, otp, new_password }
    """
    data         = request.get_json(silent=True) or {}
    email        = data.get('email', '').strip().lower()
    otp          = data.get('otp', '').strip()
    new_password = data.get('new_password', '').strip()

    if not email or not otp or not new_password:
        return jsonify({'success': False, 'message': 'جميع الحقول مطلوبة'}), 400
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'كلمة المرور يجب أن تكون 6 أحرف على الأقل'}), 400

    db   = get_db()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return jsonify({'success': False, 'message': 'البريد الإلكتروني غير موجود'}), 404
    if user.reset_code != otp:
        return jsonify({'success': False, 'message': 'الرمز غير صحيح'}), 400
    if user.reset_code_expiry and datetime.now() > user.reset_code_expiry:
        return jsonify({'success': False, 'message': 'انتهت صلاحية الرمز — اطلب رمزاً جديداً'}), 400

    from werkzeug.security import generate_password_hash
    user.password_hash     = generate_password_hash(new_password, method='pbkdf2:sha256', salt_length=16)
    user.reset_code        = None
    user.reset_code_expiry = None
    db.commit()

    # Auto-login after reset
    token = _make_token(user.id)
    return jsonify({'success': True, 'message': 'تم إعادة تعيين كلمة المرور بنجاح', 'token': token, 'user': _user_dict(user)})


# ═══════════════════════════════════════════════════════════════════════════
#  ADMIN — User Management (JWT-authenticated, admin role required)
# ═══════════════════════════════════════════════════════════════════════════

from models.database import Role

def admin_required_mobile(f):
    """Decorator: must be admin role (wraps token_required)."""
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        user = g.current_mobile_user
        if not user.role or user.role.name.lower() not in ('admin', 'مدير', 'administrator'):
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


def _admin_user_dict(user):
    """Extended user dict for admin views."""
    return {
        'id':          user.id,
        'username':    user.username,
        'full_name':   user.full_name or '',
        'email':       user.email or '',
        'phone':       user.phone or '',
        'role':        user.role.name if user.role else '',
        'role_id':     user.role_id,
        'is_active':   user.is_active,
        'is_verified': getattr(user, 'is_verified', True),
        'department':  getattr(user, 'department', '') or '',
        'job_title':   getattr(user, 'job_title', '') or '',
        'language':    user.language or 'ar',
        'login_count': getattr(user, 'login_count', 0) or 0,
        'last_login':  user.last_login.isoformat() if getattr(user, 'last_login', None) else '',
        'created_at':  user.created_at.isoformat() if getattr(user, 'created_at', None) else '',
    }


# ── List users ───────────────────────────────────────────────────────────
@mobile_api_bp.route('/admin/users', methods=['GET'])
@admin_required_mobile
def admin_list_users():
    db     = get_db()
    search = request.args.get('q', '').strip()
    page   = request.args.get('page', 1, type=int)
    per    = request.args.get('per_page', 25, type=int)

    q = db.query(User)
    if search:
        q = q.filter(
            (User.username.ilike(f'%{search}%')) |
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )

    total = q.count()
    total_pages = max(1, (total + per - 1) // per)
    page = min(page, total_pages)
    users = q.order_by(User.created_at.desc()).offset((page - 1) * per).limit(per).all()

    return jsonify({
        'success':     True,
        'users':       [_admin_user_dict(u) for u in users],
        'total':       total,
        'page':        page,
        'total_pages': total_pages,
    })


# ── Get single user ─────────────────────────────────────────────────────
@mobile_api_bp.route('/admin/users/<int:user_id>', methods=['GET'])
@admin_required_mobile
def admin_get_user(user_id):
    db   = get_db()
    user = db.query(User).get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    return jsonify({'success': True, 'user': _admin_user_dict(user)})


# ── Add user ─────────────────────────────────────────────────────────────
@mobile_api_bp.route('/admin/users', methods=['POST'])
@admin_required_mobile
def admin_add_user():
    data = request.get_json(silent=True) or {}
    db   = get_db()

    username  = data.get('username', '').strip()
    full_name = data.get('full_name', '').strip()
    email     = data.get('email', '').strip()
    phone     = data.get('phone', '').strip()
    password  = data.get('password', '').strip()
    role_id   = data.get('role_id')
    is_active = data.get('is_active', True)

    if not username or not full_name:
        return jsonify({'success': False, 'message': 'Username and full name are required'}), 400
    if not password or len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

    if db.query(User).filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Username already exists'}), 409
    if email and db.query(User).filter(User.email == email).first():
        return jsonify({'success': False, 'message': 'Email already exists'}), 409

    from werkzeug.security import generate_password_hash
    user = User(
        username      = username,
        full_name     = full_name,
        email         = email or None,
        phone         = phone or None,
        password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16),
        role_id       = int(role_id) if role_id else None,
        is_active     = bool(is_active),
        is_verified   = True,
        language      = 'ar',
    )
    # Optional fields
    if data.get('department'): user.department = data['department'].strip()
    if data.get('job_title'):  user.job_title  = data['job_title'].strip()

    db.add(user)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'Error creating user: {e}'}), 500

    return jsonify({'success': True, 'user': _admin_user_dict(user)}), 201


# ── Edit user ────────────────────────────────────────────────────────────
@mobile_api_bp.route('/admin/users/<int:user_id>', methods=['PUT'])
@admin_required_mobile
def admin_edit_user(user_id):
    data = request.get_json(silent=True) or {}
    db   = get_db()
    user = db.query(User).get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    if data.get('full_name'):  user.full_name  = data['full_name'].strip()
    if data.get('email') is not None: user.email = data['email'].strip() or None
    if data.get('phone') is not None: user.phone = data['phone'].strip() or None
    if 'is_active' in data:    user.is_active  = bool(data['is_active'])
    if data.get('role_id'):    user.role_id    = int(data['role_id'])
    if data.get('department') is not None: user.department = data['department'].strip() or None
    if data.get('job_title') is not None:  user.job_title  = data['job_title'].strip() or None

    # Optional password change
    password = data.get('password', '').strip()
    if password:
        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
        from werkzeug.security import generate_password_hash
        user.password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'Error updating user: {e}'}), 500

    return jsonify({'success': True, 'user': _admin_user_dict(user)})


# ── Toggle user active status ────────────────────────────────────────────
@mobile_api_bp.route('/admin/users/<int:user_id>/toggle-active', methods=['PUT'])
@admin_required_mobile
def admin_toggle_user(user_id):
    db   = get_db()
    user = db.query(User).get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Don't allow deactivating yourself
    if user.id == g.current_mobile_user.id:
        return jsonify({'success': False, 'message': 'Cannot deactivate your own account'}), 400

    user.is_active = not user.is_active
    db.commit()
    return jsonify({'success': True, 'is_active': user.is_active, 'user': _admin_user_dict(user)})


# ── Delete user ──────────────────────────────────────────────────────────
@mobile_api_bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required_mobile
def admin_delete_user(user_id):
    db   = get_db()
    user = db.query(User).get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    if user.id == g.current_mobile_user.id:
        return jsonify({'success': False, 'message': 'Cannot delete your own account'}), 400

    uname = user.username
    try:
        # Null out foreign keys pointing to this user
        db.query(Reservation).filter(Reservation.user_id == user_id).update({'user_id': None})
        db.flush()
        db.delete(user)
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'Error deleting user: {e}'}), 500

    return jsonify({'success': True, 'message': f'User {uname} deleted'})


# ── List roles ───────────────────────────────────────────────────────────
@mobile_api_bp.route('/admin/roles', methods=['GET'])
@admin_required_mobile
def admin_list_roles():
    db    = get_db()
    roles = db.query(Role).all()
    return jsonify({
        'success': True,
        'roles':   [{'id': r.id, 'name': r.name, 'name_en': getattr(r, 'name_en', '') or '',
                      'description': getattr(r, 'description', '') or ''} for r in roles],
    })


# ═══════════════════════════════════════════════════════════════════════════════
#  MISSING ENDPOINTS — Added to match all App.jsx screens
# ═══════════════════════════════════════════════════════════════════════════════

from models.database import (
    Contact, ContactGroup, Checklist, ChecklistItem,
    Announcement, AnnouncementDismissal, Rating,
    PIBooking, PISlot, PITeacher, PIEvent,
)


# ── Contacts ──────────────────────────────────────────────────────────────────
@mobile_api_bp.route('/contacts', methods=['GET'])
@token_required
def get_contacts():
    """Return all contacts, optionally filtered by ?q= search query."""
    db  = get_db()
    q   = (request.args.get('q') or '').strip().lower()
    contacts = db.query(Contact).order_by(Contact.first_name).all()

    def _fmt(c):
        full_name = f"{c.first_name or ''} {c.last_name or ''}".strip()
        return {
            'id':         c.id,
            'name':       full_name,
            'email':      c.email or '',
            'phone':      c.phone or '',
            'company':    c.company or '',
            'job_title':  c.job_title or '',
            'department': c.department or '',
            'notes':      c.notes or '',
        }

    result = [_fmt(c) for c in contacts]
    if q:
        result = [
            c for c in result
            if q in c['name'].lower()
            or q in c['email'].lower()
            or q in (c['company'] or '').lower()
        ]

    return jsonify({'success': True, 'contacts': result})


# ── Contact Groups ────────────────────────────────────────────────────────────
@mobile_api_bp.route('/groups', methods=['GET'])
@token_required
def get_groups():
    """Return all active contact groups with member counts."""
    db     = get_db()
    groups = db.query(ContactGroup).filter(ContactGroup.is_active == True).all()

    def _fmt(g):
        return {
            'id':          g.id,
            'name':        g.name or '',
            'description': g.description or '',
            'count':       len(g.contacts) + len(g.users),
            'created_at':  g.created_at.isoformat() if g.created_at else None,
        }

    return jsonify({'success': True, 'groups': [_fmt(g) for g in groups]})


# ── Checklists ────────────────────────────────────────────────────────────────
@mobile_api_bp.route('/checklists', methods=['GET'])
@token_required
def get_checklists():
    """Return public checklists (templates) with their items."""
    db         = get_db()
    user       = g.current_mobile_user
    checklists = (
        db.query(Checklist)
        .filter(
            (Checklist.is_public == True) |
            (Checklist.created_by_id == user.id)
        )
        .order_by(Checklist.created_at.desc())
        .all()
    )

    def _item(it):
        return {
            'id':         it.id,
            'content':    it.content or '',
            'content_en': it.content_en or '',
            'is_checked': it.is_checked,
            'priority':   it.priority or 0,
            'order':      it.order_index or 0,
        }

    def _fmt(cl):
        return {
            'id':       cl.id,
            'name':     cl.name or '',
            'name_en':  cl.name_en or '',
            'color':    cl.color or '#0C67EC',
            'emoji':    cl.emoji or '📋',
            'items':    [_item(it) for it in sorted(cl.items, key=lambda x: x.order_index or 0)],
            'total':    len(cl.items),
            'done':     sum(1 for it in cl.items if it.is_checked),
        }

    return jsonify({'success': True, 'checklists': [_fmt(cl) for cl in checklists]})


@mobile_api_bp.route('/checklists/<int:checklist_id>/items/<int:item_id>/toggle', methods=['PUT'])
@token_required
def toggle_checklist_item(checklist_id, item_id):
    """Toggle the is_checked state of a checklist item."""
    db   = get_db()
    item = db.query(ChecklistItem).filter_by(id=item_id, checklist_id=checklist_id).first()
    if not item:
        return jsonify({'success': False, 'message': 'Item not found'}), 404

    item.is_checked = not item.is_checked
    if item.is_checked:
        item.checked_by_id = g.current_mobile_user.id
        from datetime import datetime as _dt
        item.checked_at = _dt.utcnow()
    else:
        item.checked_by_id = None
        item.checked_at    = None

    db.commit()
    return jsonify({'success': True, 'is_checked': item.is_checked})


# ── Announcements ─────────────────────────────────────────────────────────────
@mobile_api_bp.route('/announcements', methods=['GET'])
@token_required
def get_announcements():
    """Return active announcements visible to this user's role."""
    from datetime import datetime as _dt
    db   = get_db()
    user = g.current_mobile_user
    now  = _dt.utcnow()

    anns = (
        db.query(Announcement)
        .filter(Announcement.is_active == True)
        .filter(
            (Announcement.start_date == None) | (Announcement.start_date <= now)
        )
        .filter(
            (Announcement.end_date == None)   | (Announcement.end_date >= now)
        )
        .order_by(Announcement.created_at.desc())
        .all()
    )

    role_name = user.role.name if user.role else ''

    def _visible(a):
        if a.target == 'all':
            return True
        if a.target == 'role':
            allowed = [r.strip() for r in (a.target_roles or '').split(',') if r.strip()]
            return role_name in allowed
        if a.target == 'users':
            allowed = [s.strip() for s in (a.target_users or '').split(',') if s.strip()]
            return str(user.id) in allowed
        return True

    def _fmt(a):
        return {
            'id':           a.id,
            'title_ar':     a.title_ar or '',
            'title_en':     a.title_en or '',
            'body_ar':      a.body_ar or '',
            'body_en':      a.body_en or '',
            'media_type':   a.media_type or 'none',
            'media_url':    a.media_url or '',
            'header_color': a.header_color or '#0847B0,#0C67EC',
            'is_active':    a.is_active,
            'start_date':   a.start_date.isoformat() if a.start_date else None,
            'end_date':     a.end_date.isoformat()   if a.end_date   else None,
            'created_at':   a.created_at.isoformat() if a.created_at else None,
        }

    visible = [_fmt(a) for a in anns if _visible(a)]
    return jsonify({'success': True, 'announcements': visible})


# ── Ratings ───────────────────────────────────────────────────────────────────
@mobile_api_bp.route('/ratings', methods=['GET'])
@token_required
def get_ratings():
    """Return ratings for bookings made by this user, plus per-venue averages."""
    db   = get_db()
    user = g.current_mobile_user

    ratings = (
        db.query(Rating)
        .filter(Rating.user_id == user.id)
        .order_by(Rating.created_at.desc())
        .limit(50)
        .all()
    )

    def _fmt(r):
        venue_name = ''
        if r.venue:
            venue_name = getattr(r.venue, 'name', '') or ''
        booking_title = ''
        if r.reservation:
            booking_title = getattr(r.reservation, 'title', '') or ''
        return {
            'id':            r.id,
            'rating':        r.rating or 0,
            'comment':       r.comment or '',
            'venue_id':      r.venue_id,
            'venue_name':    venue_name,
            'booking_id':    r.reservation_id,
            'booking_title': booking_title,
            'created_at':    r.created_at.isoformat() if r.created_at else None,
        }

    items     = [_fmt(r) for r in ratings]
    avg       = round(sum(i['rating'] for i in items) / len(items), 1) if items else 0.0
    return jsonify({'success': True, 'ratings': items, 'average': avg, 'total': len(items)})


@mobile_api_bp.route('/ratings', methods=['POST'])
@token_required
def submit_rating():
    """Submit a rating for a completed booking."""
    db   = get_db()
    data = request.get_json(silent=True) or {}
    user = g.current_mobile_user

    booking_id = data.get('booking_id')
    venue_id   = data.get('venue_id')
    score      = data.get('rating')
    comment    = (data.get('comment') or '').strip()

    if not score or not (1 <= int(score) <= 5):
        return jsonify({'success': False, 'message': 'Rating must be 1–5'}), 400

    # Verify the booking belongs to this user
    if booking_id:
        booking = db.query(Reservation).get(booking_id)
        if not booking or booking.user_id != user.id:
            return jsonify({'success': False, 'message': 'Booking not found'}), 404
        venue_id = venue_id or booking.venue_id

    existing = db.query(Rating).filter_by(user_id=user.id, reservation_id=booking_id).first()
    if existing:
        existing.rating  = int(score)
        existing.comment = comment
    else:
        new_rating = Rating(
            user_id        = user.id,
            venue_id       = venue_id,
            reservation_id = booking_id,
            rating         = int(score),
            comment        = comment,
        )
        db.add(new_rating)

    db.commit()
    return jsonify({'success': True, 'message': 'Rating submitted'})


# ── Attendance (today's booking attendance) ────────────────────────────────────
@mobile_api_bp.route('/attendance', methods=['GET'])
@token_required
def get_attendance():
    """
    Return staff attendance derived from today's reservations.
    Users with an approved booking starting before now = present,
    starting within 30 min after now = late, no booking today = absent.
    Admin/supervisor can see all users; staff sees their own department.
    """
    from datetime import datetime as _dt, timedelta as _td
    db      = get_db()
    user    = g.current_mobile_user
    today   = _dt.utcnow().date()
    day_start = _dt(_dt.utcnow().year, _dt.utcnow().month, _dt.utcnow().day, 0, 0, 0)
    day_end   = day_start + _td(days=1)

    # Get all users (limit scope for non-admins)
    role_name = user.role.name if user.role else ''
    users_q = db.query(User).filter(User.is_active == True)
    if role_name not in ('admin', 'supervisor'):
        users_q = users_q.filter(User.id == user.id)
    all_users = users_q.order_by(User.full_name).limit(100).all()

    # Get today's approved reservations
    today_bookings = (
        db.query(Reservation)
        .filter(
            Reservation.start_time >= day_start,
            Reservation.start_time <  day_end,
            Reservation.status.in_(['approved', 'pending']),
        )
        .all()
    )
    booked_user_ids = {b.user_id: b for b in today_bookings if b.user_id}
    now = _dt.utcnow()

    def _status(u):
        booking = booked_user_ids.get(u.id)
        if not booking:
            return {'status': 'absent', 'time': '—'}
        start = booking.start_time
        diff  = (start - now).total_seconds() / 60
        if diff > 30:
            return {'status': 'absent', 'time': '—'}
        if diff > 0:
            return {'status': 'late', 'time': start.strftime('%H:%M')}
        return {'status': 'present', 'time': start.strftime('%H:%M')}

    result = []
    for u in all_users:
        s = _status(u)
        result.append({
            'id':       u.id,
            'name':     u.full_name or u.username,
            'username': u.username,
            'status':   s['status'],
            'time':     s['time'],
            'role':     u.role.name if u.role else '',
        })

    present = sum(1 for r in result if r['status'] == 'present')
    late    = sum(1 for r in result if r['status'] == 'late')
    absent  = sum(1 for r in result if r['status'] == 'absent')

    return jsonify({
        'success': True,
        'attendance': result,
        'summary': {'present': present, 'late': late, 'absent': absent},
        'date': today.isoformat(),
    })


# ── Parent Interviews ─────────────────────────────────────────────────────────
@mobile_api_bp.route('/interviews', methods=['GET'])
@token_required
def get_interviews():
    """
    Return upcoming parent interview bookings from all active PI events.
    Admins/supervisors see all bookings; others see recent ones from active events.
    """
    db        = get_db()
    user      = g.current_mobile_user
    role_name = user.role.name if user.role else ''

    bookings = (
        db.query(PIBooking)
        .join(PISlot,  PIBooking.slot_id  == PISlot.id)
        .join(PIEvent, PIBooking.event_id == PIEvent.id)
        .filter(PIEvent.is_active == True)
        .filter(PIBooking.status  != 'cancelled')
        .order_by(PISlot.slot_date, PISlot.start_time)
        .limit(100)
        .all()
    )

    def _fmt(b):
        slot    = b.slot
        teacher = slot.teacher if slot else None
        return {
            'id':           b.id,
            'ref':          b.booking_ref,
            'parent_name':  b.parent_name,
            'parent_email': b.parent_email or '',
            'parent_phone': b.parent_phone or '',
            'child_name':   b.child_name,
            'status':       b.status,
            'date':         slot.slot_date  if slot else '',
            'start_time':   slot.start_time if slot else '',
            'end_time':     slot.end_time   if slot else '',
            'teacher':      teacher.name    if teacher else '',
            'event_name':   b.event.name    if b.event else '',
            'created_at':   b.created_at.isoformat() if b.created_at else None,
        }

    return jsonify({'success': True, 'interviews': [_fmt(b) for b in bookings]})


# ── Inbox (ReservationComments addressed to this user) ────────────────────────
@mobile_api_bp.route('/inbox', methods=['GET'])
@token_required
def get_inbox():
    """
    Return inbox messages: combines unread Notifications + internal reservation
    comments visible to this user, presented as a unified message feed.
    """
    db   = get_db()
    user = g.current_mobile_user

    notifs = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(30)
        .all()
    )

    def _fmt(n):
        return {
            'id':         n.id,
            'type':       'notification',
            'subject':    n.title or '',
            'body':       n.body  or '',
            'from':       'system@ars',
            'is_read':    n.is_read,
            'created_at': n.created_at.isoformat() if n.created_at else None,
            'link':       n.link or '',
        }

    messages = [_fmt(n) for n in notifs]
    unread   = sum(1 for m in messages if not m['is_read'])
    return jsonify({'success': True, 'messages': messages, 'unread': unread})


# ── Booking Types ─────────────────────────────────────────────────────────────
@mobile_api_bp.route('/booking-types', methods=['GET'])
@token_required
def get_booking_types():
    """
    Return distinct booking types used in the system along with usage counts.
    """
    from sqlalchemy import func as _func
    db = get_db()

    rows = (
        db.query(Reservation.booking_type, _func.count(Reservation.id).label('count'))
        .filter(Reservation.booking_type != None)
        .group_by(Reservation.booking_type)
        .all()
    )

    # Bilingual labels & icons for known types
    TYPE_META = {
        'official':  {'name_ar': 'رسمي',     'name_en': 'Official',  'icon': '📋', 'color': '#1a56db'},
        'meeting':   {'name_ar': 'اجتماع',   'name_en': 'Meeting',   'icon': '🤝', 'color': '#1a56db'},
        'training':  {'name_ar': 'تدريب',    'name_en': 'Training',  'icon': '📚', 'color': '#16a34a'},
        'event':     {'name_ar': 'فعالية',   'name_en': 'Event',     'icon': '🎭', 'color': '#7c3aed'},
        'sports':    {'name_ar': 'رياضة',    'name_en': 'Sports',    'icon': '⚽', 'color': '#d97706'},
        'exam':      {'name_ar': 'اختبار',   'name_en': 'Exam',      'icon': '📝', 'color': '#dc2626'},
        'other':     {'name_ar': 'أخرى',     'name_en': 'Other',     'icon': '📌', 'color': '#64748b'},
    }

    result = []
    for key, count in rows:
        meta = TYPE_META.get(key, {'name_ar': key, 'name_en': key, 'icon': '📌', 'color': '#64748b'})
        result.append({
            'id':      key,
            'name_ar': meta['name_ar'],
            'name_en': meta['name_en'],
            'icon':    meta['icon'],
            'color':   meta['color'],
            'count':   count,
        })

    # Sort by count descending
    result.sort(key=lambda x: x['count'], reverse=True)
    return jsonify({'success': True, 'booking_types': result})


# ── Resources (derived from Venues) ──────────────────────────────────────────
@mobile_api_bp.route('/resources', methods=['GET'])
@token_required
def get_resources():
    """
    Return venue facilities/resources. Derived from Venue records,
    exposing each venue as a bookable resource with availability status.
    """
    from datetime import datetime as _dt
    db   = get_db()
    now  = _dt.utcnow()

    venues = db.query(Venue).filter(Venue.is_active == True).all()

    def _is_busy(v):
        return db.query(Reservation).filter(
            Reservation.venue_id == v.id,
            Reservation.status   == 'approved',
            Reservation.start_time <= now,
            Reservation.end_time   >= now,
        ).first() is not None

    def _fmt(v):
        return {
            'id':          v.id,
            'name':        getattr(v, 'name', '') or '',
            'name_en':     getattr(v, 'name_en', '') or getattr(v, 'name', '') or '',
            'capacity':    getattr(v, 'capacity', 0) or 0,
            'available':   not _is_busy(v),
            'description': getattr(v, 'description', '') or '',
        }

    return jsonify({'success': True, 'resources': [_fmt(v) for v in venues]})


# ── Packages ──────────────────────────────────────────────────────────────────
@mobile_api_bp.route('/packages', methods=['GET'])
@token_required
def get_packages():
    """
    Return available booking packages.
    Packages are not stored in DB yet — returns the standard catalogue.
    Replace with a DB model when packages are managed from admin panel.
    """
    packages = [
        {
            'id':       1,
            'name_ar':  'باقة الأعمال',
            'name_en':  'Business Package',
            'icon':     '💼',
            'price_ar': '500 ريال',
            'price_en': 'SAR 500',
            'includes': ['قاعة', 'بروجيكتر', 'تقرير'],
        },
        {
            'id':       2,
            'name_ar':  'باقة الفعاليات',
            'name_en':  'Events Package',
            'icon':     '🎉',
            'price_ar': '1200 ريال',
            'price_en': 'SAR 1,200',
            'includes': ['ملعب', 'صوتيات', 'تصوير', 'تموين'],
        },
        {
            'id':       3,
            'name_ar':  'باقة التدريب',
            'name_en':  'Training Package',
            'icon':     '🎓',
            'price_ar': '800 ريال',
            'price_en': 'SAR 800',
            'includes': ['قاعة تدريب', 'أجهزة', 'طباعة'],
        },
    ]
    return jsonify({'success': True, 'packages': packages})


# ── Support ───────────────────────────────────────────────────────────────────
@mobile_api_bp.route('/support', methods=['POST'])
@token_required
def submit_support():
    """Log a support message as a SystemLog entry and create an admin notification."""
    from models.database import SystemLog
    db   = get_db()
    data = request.get_json(silent=True) or {}
    user = g.current_mobile_user
    msg  = (data.get('message') or '').strip()

    if not msg:
        return jsonify({'success': False, 'message': 'Message is required'}), 400
    if len(msg) > 2000:
        return jsonify({'success': False, 'message': 'Message too long (max 2000 chars)'}), 400

    # Log to system_logs
    log = SystemLog(
        action      = 'mobile_support',
        description = f'[Mobile Support] {user.username}: {msg}',
        user_id     = user.id,
        level       = 'info',
    )
    db.add(log)

    # Notify all admin users
    admins = (
        db.query(User)
        .join(User.role)
        .filter(User.role.has(name='admin'), User.is_active == True)
        .all()
    )
    for admin in admins:
        notif = Notification(
            user_id = admin.id,
            title   = f'رسالة دعم من {user.full_name or user.username}',
            body    = msg[:300],
        )
        db.add(notif)

    db.commit()
    return jsonify({'success': True, 'message': 'Support message sent successfully'})


# ═══════════════════════════════════════════════════════════════════════════════
#  QUICK-ADD ENDPOINTS — serve the QuickAddSheet in the mobile app
# ═══════════════════════════════════════════════════════════════════════════════

# ── Add Contact ───────────────────────────────────────────────────────────────
@mobile_api_bp.route('/contacts', methods=['POST'])
@token_required
def add_contact():
    db   = get_db()
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Name is required'}), 400

    parts = name.split(' ', 1)
    c = Contact(
        first_name  = parts[0],
        last_name   = parts[1] if len(parts) > 1 else '',
        email       = (data.get('email') or '').strip() or f'contact_{name.replace(" ","_").lower()}@ars.local',
        phone       = (data.get('phone') or '').strip() or None,
        job_title   = (data.get('job_title') or '').strip() or None,
        department  = (data.get('department') or '').strip() or None,
        created_by  = g.current_mobile_user.id,
    )
    db.add(c)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'id': c.id, 'message': 'Contact added'}), 201


# ── Add Group ────────────────────────────────────────────────────────────────
@mobile_api_bp.route('/groups', methods=['POST'])
@token_required
def add_group():
    db   = get_db()
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Group name is required'}), 400

    g_obj = ContactGroup(
        name        = name,
        description = (data.get('description') or '').strip() or None,
        created_by  = g.current_mobile_user.id,
        is_active   = True,
    )
    db.add(g_obj)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'id': g_obj.id, 'message': 'Group created'}), 201


# ── Add Checklist ────────────────────────────────────────────────────────────
@mobile_api_bp.route('/checklists', methods=['POST'])
@token_required
def add_checklist():
    db   = get_db()
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Checklist name is required'}), 400

    cl = Checklist(
        name            = name,
        name_en         = (data.get('name_en') or '').strip() or name,
        emoji           = (data.get('emoji') or '').strip() or '📋',
        is_public       = True,
        is_template     = False,
        created_by_id   = g.current_mobile_user.id,
    )
    db.add(cl)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'id': cl.id, 'message': 'Checklist created'}), 201


# ── Add Announcement (admin/supervisor only) ──────────────────────────────────
@mobile_api_bp.route('/announcements', methods=['POST'])
@token_required
def add_announcement():
    db        = get_db()
    user      = g.current_mobile_user
    role_name = user.role.name if user.role else ''
    if role_name not in ('admin', 'supervisor'):
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    data     = request.get_json(silent=True) or {}
    title_ar = (data.get('title_ar') or '').strip()
    if not title_ar:
        return jsonify({'success': False, 'message': 'Arabic title is required'}), 400

    ann = Announcement(
        title_ar     = title_ar,
        title_en     = (data.get('title_en') or '').strip() or title_ar,
        body_ar      = (data.get('body_ar') or '').strip() or None,
        body_en      = (data.get('body_en') or '').strip() or None,
        target       = 'all',
        is_active    = True,
        display_mode = 'once_session',
        created_by   = user.id,
    )
    db.add(ann)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'id': ann.id, 'message': 'Announcement created'}), 201


# ── Add Interview Booking ─────────────────────────────────────────────────────
@mobile_api_bp.route('/interviews', methods=['POST'])
@token_required
def add_interview():
    """
    Book a parent interview slot for the first available active event.
    Requires parent_name and child_name. Picks the earliest open slot.
    """
    import random, string
    db   = get_db()
    data = request.get_json(silent=True) or {}
    parent_name = (data.get('parent_name') or '').strip()
    child_name  = (data.get('child_name')  or '').strip()
    if not parent_name or not child_name:
        return jsonify({'success': False, 'message': 'Parent name and student name are required'}), 400

    # Find first active, open event
    event = (
        db.query(PIEvent)
        .filter(PIEvent.is_active == True, PIEvent.is_open == True)
        .order_by(PIEvent.created_at.desc())
        .first()
    )
    if not event:
        return jsonify({'success': False, 'message': 'No open interview events available'}), 404

    # Find first available slot
    slot = (
        db.query(PISlot)
        .filter(PISlot.event_id == event.id, PISlot.is_booked == False, PISlot.is_break == False)
        .order_by(PISlot.slot_date, PISlot.start_time)
        .first()
    )
    if not slot:
        return jsonify({'success': False, 'message': 'No available slots in this event'}), 404

    ref = 'MB-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    booking = PIBooking(
        slot_id         = slot.id,
        event_id        = event.id,
        booking_ref     = ref,
        parent_name     = parent_name,
        parent_email    = (data.get('parent_email') or '').strip() or None,
        parent_phone    = (data.get('parent_phone') or '').strip() or None,
        child_name      = child_name,
        booked_by_staff = True,
        status          = 'confirmed',
    )
    slot.is_booked = True
    db.add(booking)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({
        'success':     True,
        'booking_ref': ref,
        'date':        slot.slot_date,
        'start_time':  slot.start_time,
        'end_time':    slot.end_time,
        'message':     'Interview booked successfully',
    }), 201
