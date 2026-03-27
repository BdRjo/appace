"""
ARS Email Helper — Bilingual (Arabic/English)
Sends notifications in the recipient's preferred language
"""
import os, json, time, urllib.request, urllib.error
from threading import Thread

# ── Config ────────────────────────────────────────────────────────────────────
def _get_cfg():
    import os, json
    # Priority 1: Persistent /data disk on Render (survives deploys)
    data_dir = os.environ.get('DATA_DIR', '/data')
    candidates = []
    if os.path.isdir(data_dir):
        candidates.append(os.path.join(data_dir, 'email_config.json'))
    # Priority 2: EMAIL_CONFIG_PATH env var
    env_path = os.environ.get('EMAIL_CONFIG_PATH', '')
    if env_path:
        candidates.append(env_path)
    # Priority 3: App directory (local dev)
    candidates.append(os.path.join(os.path.dirname(__file__), '..', 'email_config.json'))

    for config_path in candidates:
        try:
            cfg = json.loads(open(config_path).read())
            if not cfg.get('api_key') and cfg.get('brevo_api_key'):
                cfg['api_key'] = cfg['brevo_api_key']
            if cfg.get('api_key') or cfg.get('smtp_server'):
                return cfg
        except:
            pass

    # Fallback: maintenance_config.json (legacy)
    try:
        p2 = os.path.join(os.path.dirname(__file__), '..', 'maintenance_config.json')
        cfg2 = json.loads(open(p2).read())
        email_cfg = cfg2.get('email', {})
        if not email_cfg.get('api_key') and email_cfg.get('brevo_api_key'):
            email_cfg['api_key'] = email_cfg['brevo_api_key']
        if email_cfg.get('api_key') or email_cfg.get('smtp_host'):
            return email_cfg
    except:
        pass

    # Final fallback: environment variables
    return {
        'provider_key':  os.environ.get('EMAIL_PROVIDER', 'brevo_api'),
        'api_key':       os.environ.get('BREVO_API_KEY', ''),
        'brevo_api_key': os.environ.get('BREVO_API_KEY', ''),
        'sender_email':  os.environ.get('SENDER_EMAIL', ''),
        'sender_name':   os.environ.get('SENDER_NAME', 'ARS Applied Reservation System'),
    }

def _user_lang(user):
    """Get preferred language for a user object"""
    if user is None:
        return 'ar'
    lang = getattr(user, 'language', None) or 'ar'
    return 'en' if lang == 'en' else 'ar'

def _t(user_or_lang, ar, en):
    """Return text in user's language"""
    if isinstance(user_or_lang, str):
        lang = user_or_lang
    else:
        lang = _user_lang(user_or_lang)
    return en if lang == 'en' else ar

# ── HTML wrapper ──────────────────────────────────────────────────────────────
def _html_wrapper(content, title='', lang='ar'):
    direction = 'ltr' if lang == 'en' else 'rtl'
    sys_title = 'ARS — Applied Reservation System' if lang == 'en' else 'ARS — نظام إدارة الحجوزات'
    logo_url = os.environ.get('APP_URL', 'https://appace.onrender.com') + '/static/images/logo.png'
    return f"""<!DOCTYPE html>
<html dir="{direction}" lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ARS — {title}</title>
</head>
<body style="margin:0;padding:0;background:#EEF4FD;font-family:'Segoe UI',Tahoma,Arial,sans-serif;direction:{direction}">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#EEF4FD;padding:30px 0">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(12,103,236,.12)">
      <tr>
        <td style="background:linear-gradient(135deg,#0C67EC 0%,#0847B0 100%);padding:24px 32px;text-align:center">
          <img src="{logo_url}" alt="ARS" width="140" style="display:block;margin:0 auto 8px;border-radius:8px;max-width:140px" /><br>
          <span style="color:rgba(255,255,255,.8);font-size:12px">{sys_title}</span>
        </td>
      </tr>
      <tr><td style="background:linear-gradient(90deg,#0C67EC,#3D8EF5);height:3px"></td></tr>
      <tr>
        <td style="padding:28px 32px">
          {content}
        </td>
      </tr>
      <tr>
        <td style="background:#f7f9fc;padding:16px 32px;text-align:center;border-top:1px solid #e8edf5">
          <p style="color:#6b7c99;font-size:11px;margin:0">© 2026 ARS — Applied Reservation System</p>
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""

def _info_row(label, value, bg='#FAFFFE'):
    return f'<tr><td style="padding:10px 14px;background:{bg};font-size:13px;color:#6b7c99;width:35%">{label}</td><td style="padding:10px 14px;background:{bg};font-size:13px;color:#2d3748;font-weight:600">{value}</td></tr>'

# ── Send engine ───────────────────────────────────────────────────────────────
def _send(to_email, to_name, subject, html, text='', sync=False,
          email_type='notification', user_id=None):
    if not to_email:
        return False

    def _log_result(status, error_msg=''):
        """Log email result to database EmailLog table"""
        try:
            from models.database import EmailLog, get_engine
            from sqlalchemy.orm import sessionmaker
            engine = get_engine()
            Session = sessionmaker(bind=engine)
            s = Session()
            log = EmailLog(
                recipient=to_email,
                subject=subject,
                type=email_type,
                status=status,
                error_message=error_msg[:500] if error_msg else None,
                user_id=user_id,
            )
            s.add(log)
            s.commit()
            s.close()
        except Exception as le:
            print(f'EmailLog write error: {le}')

    def _do_send():
        try:
            cfg = _get_cfg()
            api_key      = cfg.get('api_key') or cfg.get('brevo_api_key', '')
            sender_email = cfg.get('sender_email', '')
            sender_name  = cfg.get('sender_name', 'ARS')
            if not api_key:
                print('Email error: API key is missing — configure it in Admin → Email Settings')
                _log_result('failed', 'API key missing')
                return False
            if not sender_email:
                print('Email error: Sender email is missing — configure it in Admin → Email Settings')
                _log_result('failed', 'Sender email missing')
                return False
            # Brevo requires non-empty textContent — fallback to subject
            plain_text = text if text and text.strip() else (subject or 'Notification')
            payload = json.dumps({
                'sender':      {'name': sender_name, 'email': sender_email},
                'to':          [{'email': to_email, 'name': to_name or to_email}],
                'subject':     subject,
                'htmlContent': html,
                'textContent': plain_text,
            }).encode('utf-8')
            req = urllib.request.Request(
                'https://api.brevo.com/v3/smtp/email',
                data=payload,
                headers={'Content-Type': 'application/json', 'api-key': api_key}
            )
            urllib.request.urlopen(req, timeout=15)
            _log_result('sent')
            return True
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='ignore')
            try:
                err = json.loads(body).get('message', body[:150])
            except:
                err = body[:150]
            msg = f'Brevo API error {e.code}: {err}'
            print(f'Email error: {msg}')
            _log_result('failed', msg)
            return False
        except Exception as e:
            print(f'Email error: {e}')
            _log_result('failed', str(e))
            return False

    if sync:
        return _do_send()
    Thread(target=_do_send, daemon=True).start()
    return True


def send_email(to_email, to_name='', subject='', html_body='', text_body='', sync=False):
    """Generic send email — public wrapper used by interviews module and other callers."""
    return _send(to_email=to_email, to_name=to_name, subject=subject,
                 html=html_body, text=text_body, sync=sync,
                 email_type='notification')


# ── Push local notification ───────────────────────────────────────────────────
def push_notification(db, user_id, title_ar, title_en, body_ar='', body_en='', link=None, user_lang='ar'):
    """Push bilingual local notification"""
    from models.database import Notification
    try:
        title = title_en if user_lang == 'en' else title_ar
        body  = body_en  if user_lang == 'en' else body_ar
        db.add(Notification(user_id=user_id, title=title, body=body, link=link))
        db.commit()
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# BILINGUAL EMAIL FUNCTIONS
# Each function detects user's preferred language and sends accordingly
# ─────────────────────────────────────────────────────────────────────────────

def send_booking_request(user, res):
    """Notify user their booking request was received"""
    lang  = _user_lang(user)
    name  = user.full_name or user.username
    bn    = res.booking_number
    title = res.title

    if lang == 'en':
        content = f"""
<h2 style="color:#0C67EC;margin:0 0 6px;font-size:20px">Hello {name},</h2>
<p style="color:#4a5568;margin:0 0 20px">Your booking request has been received and will be reviewed shortly.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  {_info_row('📋 Booking No.', f'<strong style="color:#0C67EC">{bn}</strong>')}
  {_info_row('📌 Title', title, '#FAFCFF')}
</table>
<div style="background:linear-gradient(135deg,#EEF4FD,#E8F0FE);border-left:4px solid #0C67EC;border-radius:8px;padding:12px 16px;color:#4a5568;font-size:14px">
  ⏳ You will be notified once a decision is made.
</div>"""
        subj = f'📋 New Booking Request — ARS'
        txt  = f"ARS — Booking Request\n\nHello {name},\nYour booking request has been received.\nRef: {bn}\nTitle: {title}\n\nYou will be notified soon."
    else:
        content = f"""
<h2 style="color:#0C67EC;margin:0 0 6px;font-size:20px">مرحباً {name}،</h2>
<p style="color:#4a5568;margin:0 0 20px">تم استلام طلب الحجز الخاص بك بنجاح، وسيتم مراجعته من قِبل المختصين.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  {_info_row('📋 رقم الحجز', f'<strong style="color:#0C67EC">{bn}</strong>')}
  {_info_row('📌 العنوان', title, '#FAFCFF')}
</table>
<div style="background:linear-gradient(135deg,#EEF4FD,#E8F0FE);border-right:4px solid #0C67EC;border-radius:8px;padding:12px 16px;color:#4a5568;font-size:14px">
  ⏳ سيتم إعلامك بقرار الموافقة في أقرب وقت.
</div>"""
        subj = f'📋 طلب حجز جديد — ARS'
        txt  = f"ARS — طلب حجز جديد\n\nمرحباً {name}،\nتم استلام طلب الحجز:\nالرقم المرجعي: {bn}\nالعنوان: {title}\n\nسيتم إعلامك بقرار الموافقة قريباً."

    _send(user.email or '', name, subj, _html_wrapper(content, subj, lang), txt, sync=True, email_type='notification')


def send_booking_approved(res):
    """Notify user their booking was approved"""
    if not res.user: return
    lang  = _user_lang(res.user)
    name  = res.user.full_name or res.user.username
    bn    = res.booking_number
    title = res.title
    venue = res.venue.name if res.venue else '—'
    start = res.start_time.strftime('%Y-%m-%d  %H:%M') if res.start_time else '—'

    if lang == 'en':
        content = f"""
<div style="background:linear-gradient(135deg,#E8F5E9,#F1F8E9);border-radius:10px;padding:16px 20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;margin-bottom:6px">✅</div>
  <h2 style="color:#1B5E20;margin:0;font-size:18px">Congratulations {name}! Your booking has been approved.</h2>
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #C8E6C9;margin-bottom:20px">
  {_info_row('📋 Booking No.', f'<strong style="color:#0C67EC">{bn}</strong>', '#F1F8E9')}
  {_info_row('📌 Title', title, '#FAFFFE')}
  {_info_row('🏢 Venue', venue, '#F1F8E9')}
  {_info_row('🕐 Time', start, '#FAFFFE')}
</table>
<div style="background:#E8F5E9;border-left:4px solid #43A047;border-radius:8px;padding:12px 16px;color:#2E7D32;font-size:14px">
  ✅ Your booking is confirmed. We hope you have a great experience!
</div>"""
        subj = '✅ Booking Approved — ARS'
        txt  = f"ARS — Booking Approved\n\nHello {name},\nYour booking has been approved.\nRef: {bn}\nTitle: {title}\nVenue: {venue}\nTime: {start}"
    else:
        content = f"""
<div style="background:linear-gradient(135deg,#E8F5E9,#F1F8E9);border-radius:10px;padding:16px 20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;margin-bottom:6px">✅</div>
  <h2 style="color:#1B5E20;margin:0;font-size:18px">تهانينا {name}! تمت الموافقة على حجزك</h2>
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #C8E6C9;margin-bottom:20px">
  {_info_row('📋 رقم الحجز', f'<strong style="color:#0C67EC">{bn}</strong>', '#F1F8E9')}
  {_info_row('📌 العنوان', title, '#FAFFFE')}
  {_info_row('🏢 القاعة', venue, '#F1F8E9')}
  {_info_row('🕐 الوقت', start, '#FAFFFE')}
</table>
<div style="background:#E8F5E9;border-right:4px solid #43A047;border-radius:8px;padding:12px 16px;color:#2E7D32;font-size:14px">
  ✅ حجزك معتمد ومؤكد. نتمنى لك تجربة رائعة!
</div>"""
        subj = '✅ تمت الموافقة على حجزك — ARS'
        txt  = f"ARS — تمت الموافقة\n\nمرحباً {name}،\nتمت الموافقة على حجزك.\nالرقم: {bn}\nالعنوان: {title}\nالقاعة: {venue}\nالوقت: {start}"

    _send(res.user.email or '', name, subj, _html_wrapper(content, subj, lang), txt, sync=True, email_type='notification')


def send_booking_rejected(res, reason=''):
    """Notify user their booking was rejected"""
    if not res.user: return
    lang  = _user_lang(res.user)
    name  = res.user.full_name or res.user.username
    bn    = res.booking_number
    title = res.title

    if lang == 'en':
        content = f"""
<div style="background:linear-gradient(135deg,#FFEBEE,#FCE4EC);border-radius:10px;padding:16px 20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;margin-bottom:6px">❌</div>
  <h2 style="color:#B71C1C;margin:0;font-size:18px">Sorry {name}, your booking request was not approved.</h2>
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #FFCDD2;margin-bottom:20px">
  {_info_row('📋 Booking No.', f'<strong>{bn}</strong>', '#FFF3F3')}
  {_info_row('📌 Title', title, '#FFFAFA')}
  {_info_row('📝 Reason', reason or '—', '#FFF3F3')}
</table>
<div style="background:#FFF3E0;border-left:4px solid #FB8C00;border-radius:8px;padding:12px 16px;color:#E65100;font-size:14px">
  💡 You may contact the administration or submit a new request.
</div>"""
        subj = '❌ Booking Not Approved — ARS'
        txt  = f"ARS — Booking Rejected\n\nHello {name},\nYour booking was not approved.\nRef: {bn}\nTitle: {title}\nReason: {reason or '—'}"
    else:
        content = f"""
<div style="background:linear-gradient(135deg,#FFEBEE,#FCE4EC);border-radius:10px;padding:16px 20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;margin-bottom:6px">❌</div>
  <h2 style="color:#B71C1C;margin:0;font-size:18px">عذراً {name}، تم رفض طلب الحجز</h2>
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #FFCDD2;margin-bottom:20px">
  {_info_row('📋 رقم الحجز', f'<strong>{bn}</strong>', '#FFF3F3')}
  {_info_row('📌 العنوان', title, '#FFFAFA')}
  {_info_row('📝 السبب', reason or '—', '#FFF3F3')}
</table>
<div style="background:#FFF3E0;border-right:4px solid #FB8C00;border-radius:8px;padding:12px 16px;color:#E65100;font-size:14px">
  💡 يمكنك التواصل مع الإدارة أو تقديم طلب جديد.
</div>"""
        subj = '❌ تم رفض طلب الحجز — ARS'
        txt  = f"ARS — رفض الحجز\n\nمرحباً {name}،\nتم رفض حجزك.\nالرقم: {bn}\nالعنوان: {title}\nالسبب: {reason or '—'}"

    _send(res.user.email or '', name, subj, _html_wrapper(content, subj, lang), txt, sync=True, email_type='notification')


def send_booking_cancelled(res, cancelled_by=None):
    """Notify user their booking was cancelled"""
    if not res.user: return
    lang  = _user_lang(res.user)
    name  = res.user.full_name or res.user.username
    bn    = res.booking_number
    title = res.title

    if lang == 'en':
        content = f"""
<h2 style="color:#546E7A;margin:0 0 12px">Hello {name},</h2>
<p style="color:#4a5568">Booking <strong style="color:#0C67EC">{bn}</strong> — "{title}" has been <strong style="color:#c0392b">cancelled</strong>.</p>
<div style="background:#f5f5f5;border-left:4px solid #546E7A;border-radius:8px;padding:12px 16px;color:#546E7A;font-size:14px;margin-top:16px">
  If you believe this is an error, please contact the administration.
</div>"""
        subj = '🚫 Booking Cancelled — ARS'
        txt  = f"ARS — Booking Cancelled\n\nHello {name},\nBooking {bn} has been cancelled."
    else:
        content = f"""
<h2 style="color:#546E7A;margin:0 0 12px">مرحباً {name}،</h2>
<p style="color:#4a5568">تم <strong style="color:#c0392b">إلغاء</strong> الحجز رقم <strong style="color:#0C67EC">{bn}</strong> — "{title}".</p>
<div style="background:#f5f5f5;border-right:4px solid #546E7A;border-radius:8px;padding:12px 16px;color:#546E7A;font-size:14px;margin-top:16px">
  إذا كان هذا خطأ، يرجى التواصل مع الإدارة.
</div>"""
        subj = '🚫 تم إلغاء الحجز — ARS'
        txt  = f"ARS — إلغاء الحجز\n\nمرحباً {name}،\nتم إلغاء الحجز رقم {bn}."

    _send(res.user.email or '', name, subj, _html_wrapper(content, subj, lang), txt, sync=True, email_type='notification')


def send_invitation(contact, res, message_body=''):
    """Invite a contact to a reservation"""
    name  = contact.first_name or ''
    title = res.title
    venue = res.venue.name if res.venue else '—'
    start = res.start_time.strftime('%Y-%m-%d  %H:%M') if res.start_time else '—'

    content = f"""
<h2 style="color:#0C67EC;margin:0 0 12px">{'Dear' if True else 'عزيزي'} {name},</h2>
<p style="color:#4a5568">You are cordially invited to:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin:16px 0">
  {_info_row('📌 Event', title)}
  {_info_row('🏢 Venue', venue, '#FAFCFF')}
  {_info_row('📅 Date & Time', start)}
</table>
{f'<p style="color:#4a5568;margin-top:12px">{message_body}</p>' if message_body else ''}"""
    subj = f'📩 Invitation: {title}'
    txt  = f"Invitation: {title}\nVenue: {venue}\nTime: {start}"
    _send(contact.email or '', name, subj, _html_wrapper(content, subj, 'en'), txt, sync=True, email_type='notification')


def send_bulk(users, subject, body, html=True, attachments=None, interface_lang=None):
    """Send bulk message — interface_lang forces language for all emails."""
    def _bulk_worker():
        for user in users:
            if not user or not user.email:
                continue
            lang = interface_lang if interface_lang else _user_lang(user)
            name = user.full_name or user.username or user.email
            try:
                if html:
                    content = f"""
<h2 style="color:#0C67EC;margin:0 0 12px">{'Hello' if lang=='en' else 'مرحباً'} {name},</h2>
<div style="color:#4a5568;font-size:14px;line-height:1.6">{body}</div>"""
                    html_body = _html_wrapper(content, subject, lang)
                else:
                    html_body = _html_wrapper(
                        f"<pre style='font-family:inherit'>{body}</pre>",
                        subject, lang)
                _send(user.email, name, subject, html_body, body,
                      sync=True, email_type='bulk',
                      user_id=getattr(user, 'id', None))
            except Exception as e:
                print(f'Bulk send error for {user.email}: {e}')
            # ← 0.3s delay between each email — prevents rate-limit blocking
            time.sleep(0.3)

    Thread(target=_bulk_worker, daemon=True).start()


def send_welcome(user, password, login_url=''):
    """Welcome email for new user"""
    lang  = _user_lang(user)
    name  = user.full_name or user.username
    uname = user.username

    if lang == 'en':
        content = f"""
<h2 style="color:#0C67EC;margin:0 0 12px">Welcome to ARS, {name}! 🎉</h2>
<p style="color:#4a5568;margin:0 0 16px">Your account has been created. Here are your login credentials:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  {_info_row('👤 Username', uname)}
  {_info_row('🔑 Password', f'<code style="background:#f4f9ff;padding:2px 6px;border-radius:4px">{password}</code>', '#FAFCFF')}
</table>
{f'<a href="{login_url}" style="background:#0C67EC;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;display:inline-block;font-weight:700;margin-top:8px">Login Now</a>' if login_url else ''}
<p style="color:#999;font-size:12px;margin-top:16px">Please change your password after first login.</p>"""
        subj = 'Welcome to ARS — Applied Reservation System'
        txt  = f"Welcome {name}!\nUsername: {uname}\nPassword: {password}\nLogin: {login_url}"
    else:
        content = f"""
<h2 style="color:#0C67EC;margin:0 0 12px">مرحباً بك في ARS، {name}! 🎉</h2>
<p style="color:#4a5568;margin:0 0 16px">تم إنشاء حسابك بنجاح. بيانات الدخول الخاصة بك:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  {_info_row('👤 اسم المستخدم', uname)}
  {_info_row('🔑 كلمة المرور', f'<code style="background:#f4f9ff;padding:2px 6px;border-radius:4px">{password}</code>', '#FAFCFF')}
</table>
{f'<a href="{login_url}" style="background:#0C67EC;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;display:inline-block;font-weight:700;margin-top:8px">تسجيل الدخول</a>' if login_url else ''}
<p style="color:#999;font-size:12px;margin-top:16px">يُرجى تغيير كلمة المرور بعد أول دخول.</p>"""
        subj = 'مرحباً بك في ARS — نظام إدارة الحجوزات'
        txt  = f"مرحباً {name}!\nاسم المستخدم: {uname}\nكلمة المرور: {password}\nرابط الدخول: {login_url}"

    _send(user.email or '', name, subj, _html_wrapper(content, subj, lang), txt, sync=True, email_type='notification')


def send_reset_code(email: str, code: str, lang: str = 'ar') -> bool:
    if lang == 'en':
        content = f"""
<p style="color:#4a5568;margin:0 0 20px">Use the code below to reset your password:</p>
<div style="background:#f4f9ff;border:2px dashed #0C67EC;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;font-weight:900;letter-spacing:12px;color:#0C67EC">{code}</div>
</div>
<p style="color:#999;font-size:12px">This code expires in 15 minutes. Do not share it with anyone.</p>"""
        subj = 'ARS — Password Reset Code'
        txt  = f'Reset code: {code}'
    else:
        content = f"""
<p style="color:#4a5568;margin:0 0 20px">استخدم الرمز أدناه لإعادة تعيين كلمة مرورك:</p>
<div style="background:#f4f9ff;border:2px dashed #0C67EC;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;font-weight:900;letter-spacing:12px;color:#0C67EC">{code}</div>
</div>
<p style="color:#999;font-size:12px">صالح لمدة 15 دقيقة. لا تشاركه مع أحد.</p>"""
        subj = 'ARS — رمز إعادة تعيين كلمة المرور'
        txt  = f'Reset code: {code}'

    return _send(email, '', subj, _html_wrapper(content, subj, lang), txt, sync=True)


def send_verification_code(email: str, code: str, full_name: str = '', lang: str = 'ar') -> bool:
    name = full_name or email
    if lang == 'en':
        content = f"""
<p style="color:#4a5568;margin:0 0 20px">Thank you for registering in ARS. Enter the code below to verify your account:</p>
<div style="background:#f4f9ff;border:2px dashed #0C67EC;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;font-weight:900;letter-spacing:12px;color:#0C67EC">{code}</div>
</div>"""
        subj = 'ARS — Email Verification Code'
        txt  = f'Verification code: {code}'
    else:
        content = f"""
<p style="color:#4a5568;margin:0 0 20px">شكراً لتسجيلك في نظام ARS. أدخل الرمز أدناه لتفعيل حسابك:</p>
<div style="background:#f4f9ff;border:2px dashed #0C67EC;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;font-weight:900;letter-spacing:12px;color:#0C67EC">{code}</div>
</div>"""
        subj = 'ARS — رمز التحقق من البريد الإلكتروني'
        txt  = f'Verification code: {code}'

    return _send(email, name, subj, _html_wrapper(content, subj, lang), txt, sync=True)


def send_employee_reservation_notice(employee, res, requester):
    """Notify employee they were assigned to a reservation"""
    lang  = _user_lang(employee)
    name  = employee.full_name or employee.username
    req_name = requester.full_name or requester.username if requester else '—'
    bn    = res.booking_number
    title = res.title
    venue = res.venue.name if res.venue else '—'
    start = res.start_time.strftime('%Y-%m-%d  %H:%M') if res.start_time else '—'

    if lang == 'en':
        content = f"""
<h2 style="color:#0C67EC;margin:0 0 12px">Hello {name},</h2>
<p style="color:#4a5568">You have been assigned to the following reservation by <strong>{req_name}</strong>:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin:16px 0">
  {_info_row('📋 Booking No.', bn)}
  {_info_row('📌 Title', title, '#FAFCFF')}
  {_info_row('🏢 Venue', venue)}
  {_info_row('🕐 Time', start, '#FAFCFF')}
</table>"""
        subj = f'📋 Reservation Assignment — {bn}'
        txt  = f"You were assigned to reservation {bn}: {title}"
    else:
        content = f"""
<h2 style="color:#0C67EC;margin:0 0 12px">مرحباً {name}،</h2>
<p style="color:#4a5568">تم تعيينك في الحجز التالي من قِبل <strong>{req_name}</strong>:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin:16px 0">
  {_info_row('📋 رقم الحجز', bn)}
  {_info_row('📌 العنوان', title, '#FAFCFF')}
  {_info_row('🏢 القاعة', venue)}
  {_info_row('🕐 الوقت', start, '#FAFCFF')}
</table>"""
        subj = f'📋 تعيين في حجز — {bn}'
        txt  = f"تم تعيينك في الحجز {bn}: {title}"

    _send(employee.email or '', name, subj, _html_wrapper(content, subj, lang), txt, sync=True, email_type='notification')


def test_smtp(smtp_host='', smtp_port=587, sender_email='', sender_password='',
              use_tls=True, brevo_api_key=None, to_email=None, lang='ar') -> tuple:
    """Test email — tries provided credentials, falls back to saved config"""
    import json, urllib.request
    en = lang == 'en'
    try:
        api_key   = (brevo_api_key or '').strip()
        from_email = (sender_email or '').strip()

        if not api_key or not from_email:
            cfg = _get_cfg()
            if not api_key:
                api_key = cfg.get('api_key') or cfg.get('brevo_api_key', '')
            if not from_email:
                from_email = cfg.get('sender_email', '')

        test_to = (to_email or from_email or '').strip()

        if not api_key:
            return (False, 'API Key is missing — enter your Brevo API Key and save settings first' if en else 'API Key مفقود — أدخل Brevo API Key واحفظ الإعدادات أولاً')
        if not from_email:
            return (False, 'Sender Email is missing — enter the sender email and save settings' if en else 'Sender Email مفقود — أدخل بريد المُرسِل واحفظ الإعدادات')
        if not test_to:
            return (False, 'No recipient email address' if en else 'لا يوجد بريد للاستلام')

        payload = json.dumps({
            'sender':      {'name': 'ARS Test', 'email': from_email},
            'to':          [{'email': test_to, 'name': 'ARS Test'}],
            'subject':     'ARS — Email Test ✅',
            'htmlContent': _html_wrapper(
                '<p style="color:#4a5568;text-align:center;font-size:16px">'
                '✅ Email configuration is working correctly!</p>'
                '<p style="color:#888;text-align:center;font-size:13px">'
                'ARS Email configuration is working correctly.</p>' if en else
                '<p style="color:#4a5568;text-align:center;font-size:16px">'
                '✅ إعدادات البريد الإلكتروني تعمل بشكل صحيح!</p>'
                '<p style="color:#888;text-align:center;font-size:13px">'
                'ARS Email configuration is working correctly.</p>',
                'Test', lang),
            'textContent': 'ARS email test successful!' if en else 'ARS email test — تم الإرسال بنجاح!'
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.brevo.com/v3/smtp/email',
            data=payload,
            headers={'Content-Type': 'application/json', 'api-key': api_key}
        )
        urllib.request.urlopen(req, timeout=15)
        return (True, f'Test email sent successfully to: {test_to}' if en else f'تم إرسال بريد اختباري بنجاح إلى: {test_to}')

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        try:
            err_obj = json.loads(body)
            err = err_obj.get('message', body[:200])
        except:
            err = body[:200]
        if e.code == 401:
            return (False, f'API Key is invalid or expired (401) — check brevo.com' if en else f'API Key غير صحيح أو منتهي الصلاحية (401) — تحقق من brevo.com')
        if e.code == 400:
            return (False, f'Data error (400): {err} — make sure sender email is verified in Brevo' if en else f'خطأ في البيانات (400): {err} — تأكد أن بريد المُرسِل موثّق في Brevo')
        return (False, f'Brevo API error {e.code}: {err}' if en else f'Brevo API خطأ {e.code}: {err}')
    except Exception as e:
        return (False, f'Connection error: {e}' if en else f'خطأ في الاتصال: {e}')
