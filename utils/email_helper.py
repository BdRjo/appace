"""
مساعد البريد الإلكتروني — يدعم Brevo HTTP API و SMTP
Brevo API: لا يحتاج ports مفتوحة — يعمل على Render.com
"""
import smtplib, json, os, threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

CONFIG_FILE = __import__('os').environ.get('EMAIL_CONFIG_PATH', __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))), 'email_config.json'))

PROVIDERS = {
    'brevo_api':  {'label': 'Brevo API (موصى به على Render)', 'smtp': '',                        'port': 0},
    'gmail':      {'label': 'Gmail',                           'smtp': 'smtp.gmail.com',          'port': 587},
    'office365':  {'label': 'Microsoft 365 / Outlook',        'smtp': 'smtp.office365.com',       'port': 587},
    'outlook':    {'label': 'Outlook.com (Hotmail)',           'smtp': 'smtp-mail.outlook.com',    'port': 587},
    'yahoo':      {'label': 'Yahoo Mail',                      'smtp': 'smtp.mail.yahoo.com',      'port': 587},
    'brevo':      {'label': 'Brevo SMTP',                      'smtp': 'smtp-relay.brevo.com',     'port': 587},
    'custom':     {'label': 'خادم مخصص',                      'smtp': '',                          'port': 587},
}

def _load_config():
    import os
    # ── 1) Environment variables (Render.com) ────────────────────────────────
    env_key = os.environ.get('BREVO_API_KEY', '').strip()
    if env_key:
        return {
            'provider_key':  'brevo_api',
            'brevo_api_key': env_key,
            'sender_email':  os.environ.get('SENDER_EMAIL', 'baderaq@gmail.com'),
            'sender_name':   os.environ.get('SENDER_NAME', 'ARS Applied Reservation System'),
        }
    # ── 2) Hardcoded Brevo (always works) ────────────────────────────────────
    return {
        'provider_key':  'brevo_api',
        'brevo_api_key': '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',
        'sender_email':  'baderaq@gmail.com',
        'sender_name':   'ARS Applied Reservation System',
    }

def _send_via_brevo_api(to_email, to_name, subject, html, text, cfg):
    """إرسال عبر Brevo HTTP API — يعمل على Render.com بدون SMTP"""
    import urllib.request
    api_key = cfg.get('brevo_api_key', '')
    if not api_key:
        raise Exception('Brevo API Key غير محدد')
    sender_email = cfg.get('sender_email', '')
    sender_name  = cfg.get('sender_name', 'ARS')
    payload = json.dumps({
        'sender':   {'name': sender_name, 'email': sender_email},
        'to':       [{'email': to_email, 'name': to_name or to_email}],
        'subject':  subject,
        'htmlContent': html,
        'textContent': text,
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.brevo.com/v3/smtp/email',
        data=payload,
        headers={
            'api-key':       api_key,
            'Content-Type':  'application/json',
            'Accept':        'application/json',
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status not in (200, 201):
            raise Exception(f'Brevo API error: {resp.status}')

def _html_wrapper(content, title=''):
    """Professional email template — new blue theme"""
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ARS — {title or 'Applied Reservation System'}</title>
</head>
<body style="margin:0;padding:0;background:#EEF4FD;font-family:'Segoe UI',Tahoma,Arial,sans-serif;direction:rtl">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#EEF4FD;padding:30px 0">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(12,103,236,.12)">

      <!-- Header -->
      <tr>
        <td style="background:linear-gradient(135deg,#0C67EC 0%,#0847B0 100%);padding:28px 32px;text-align:center">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td align="center">
                <div style="display:inline-block;margin-bottom:10px">
                  <img src="https://appace.onrender.com/static/images/logo.png" alt="ARS" width="160" height="67" style="display:block;border-radius:8px;max-width:160px" />
                </div><br>
                <span style="color:#ffffff;font-size:22px;font-weight:800;letter-spacing:.5px">ARS</span>
                <span style="color:rgba(255,255,255,.7);font-size:13px;margin-right:8px">Applied Reservation System</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Blue accent bar -->
      <tr><td style="background:linear-gradient(90deg,#0C67EC,#3D8EF5);height:4px"></td></tr>

      <!-- Content -->
      <tr>
        <td style="padding:32px 36px;color:#1a2332;font-size:15px;line-height:1.7">
          {content}
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background:#F4F7FF;padding:18px 32px;text-align:center;border-top:1px solid #E0E8F5">
          <p style="color:#6b7c99;font-size:12px;margin:0 0 4px">جميع الحقوق محفوظة © 2026 ARS — Applied Reservation System</p>
          <p style="color:#9aa3b5;font-size:11px;margin:0">هذا بريد إلكتروني تلقائي، الرجاء عدم الرد عليه</p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

def _send(to_email, to_name, subject, html, text, sync=False):
    """إرسال بريد — يستخدم Brevo API أو SMTP حسب الإعدادات"""
    cfg = _load_config()
    if not to_email:
        return False

    def _do_send():
        # ── Brevo API mode (موصى به على Render) ──────────────────────────────
        if cfg.get('provider_key') == 'brevo_api' or cfg.get('brevo_api_key'):
            _send_via_brevo_api(to_email, to_name, subject, html, text, cfg)
            return
        # ── SMTP mode ─────────────────────────────────────────────────────────
        msg = MIMEMultipart('alternative')
        msg['From']    = f"{cfg.get('sender_name','ARS')} <{cfg.get('sender_email','')}>"
        msg['To']      = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(text, 'plain', 'utf-8'))
        msg.attach(MIMEText(html, 'html',  'utf-8'))
        port = int(cfg.get('smtp_port', 587))
        if port == 465:
            import ssl
            ctx = ssl.create_default_context()
            srv = smtplib.SMTP_SSL(cfg['smtp_server'], port, timeout=30, context=ctx)
            srv.ehlo()
        else:
            srv = smtplib.SMTP(cfg['smtp_server'], port, timeout=30)
            srv.ehlo()
            if cfg.get('use_tls', True):
                srv.starttls(); srv.ehlo()
        srv.login(cfg['sender_email'], cfg['sender_password'])
        srv.send_message(msg)
        srv.quit()

    if sync:
        try:
            _do_send()
            return True
        except Exception as e:
            print(f"Email sync error: {e}")
            return False
    else:
        def _thread():
            try:
                _do_send()
            except Exception as e:
                print(f"Email error: {e}")
        threading.Thread(target=_thread, daemon=True).start()
        return True


def _info_row(label, value, bg='#F4F7FF'):
    return f'<tr><td style="padding:9px 14px;font-weight:700;color:#0C67EC;width:38%;background:{bg};border-bottom:1px solid #E0E8F5">{label}</td><td style="padding:9px 14px;color:#1a2332;background:{bg};border-bottom:1px solid #E0E8F5">{value}</td></tr>'

def send_booking_request(user, res):
    name  = user.full_name
    bn    = res.booking_number
    title = res.title
    html  = _html_wrapper(f"""
<h2 style="color:#0C67EC;margin:0 0 6px;font-size:20px">مرحباً {name}،</h2>
<p style="color:#4a5568;margin:0 0 20px">تم استلام طلب الحجز الخاص بك بنجاح، وسيتم مراجعته من قِبل المختصين.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  {_info_row('📋 رقم الحجز', f'<strong style="color:#0C67EC">{bn}</strong>')}
  {_info_row('📌 العنوان', title, '#FAFCFF')}
</table>
<div style="background:linear-gradient(135deg,#EEF4FD,#E8F0FE);border-right:4px solid #0C67EC;border-radius:8px;padding:12px 16px;color:#4a5568;font-size:14px">
  ⏳ سيتم إعلامك بقرار الموافقة في أقرب وقت.
</div>
""", 'طلب حجز جديد')
    text = f"ARS — طلب حجز جديد\n\nمرحباً {name}،\nتم استلام طلب الحجز:\nالرقم المرجعي: {bn}\nالعنوان: {title}\n\nسيتم إعلامك بقرار الموافقة قريباً."
    _send(user.email or '', name, '📋 طلب حجز جديد — ARS', html, text)


def send_booking_approved(res):
    if not res.user: return
    name = res.user.full_name; bn = res.booking_number; title = res.title
    venue = res.venue.name if res.venue else '—'
    start = res.start_time.strftime('%Y-%m-%d  %H:%M') if res.start_time else '—'
    html = _html_wrapper(f"""
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
</div>
""", 'موافقة على الحجز')
    text = f"ARS — تمت الموافقة على الحجز\n\nمرحباً {name}،\nتمت الموافقة على حجزك:\nالرقم المرجعي: {bn}\nالعنوان: {title}\nالقاعة: {venue}\nالوقت: {start}"
    _send(res.user.email or '', name, '✅ تمت الموافقة على حجزك — ARS', html, text)


def send_booking_rejected(res, reason=''):
    if not res.user: return
    name = res.user.full_name; bn = res.booking_number; title = res.title
    html = _html_wrapper(f"""
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
</div>
""", 'رفض الحجز')
    text = f"ARS — تم رفض الحجز\n\nمرحباً {name}،\nتم رفض حجزك:\nالرقم المرجعي: {bn}\nالعنوان: {title}\nالسبب: {reason}"
    _send(res.user.email or '', name, '❌ تم رفض طلب الحجز — ARS', html, text)


def send_invitation(contact, res, message_body=''):
    """مطابق لـ v54 SendInvitationsWindow.send_invitations"""
    name  = contact.first_name or ''
    title = res.title
    venue = res.venue.name if res.venue else ''
    start = res.start_time.strftime('%Y-%m-%d') if res.start_time else ''
    time_ = res.start_time.strftime('%H:%M')    if res.start_time else ''
    html  = _html_wrapper(f"""
<div style="text-align:center;margin:30px 0;">
  <div style="font-size:48px;">📧</div>
  <h2 style="color:#2C3E50;">دعوة: {title}</h2>
  <div style="background:#F5F7FA;padding:20px;border-radius:10px;margin:20px;text-align:right;">
    <p><strong>🏢 القاعة:</strong> {venue}</p>
    <p><strong>🗓 التاريخ:</strong> {start}</p>
    <p><strong>⏰ الوقت:</strong> {time_}</p>
  </div>
  <div style="background:#EDF7EF;padding:20px;border-radius:10px;margin:20px;text-align:right;white-space:pre-wrap;">{message_body}</div>
</div>""")
    text = f"دعوة لحضور {title}\n\n{message_body}"
    _send(contact.email or '', name, f'دعوة لحضور {title}', html, text)


def send_bulk(users, subject, body):
    """مطابق لـ v54 send_bulk_message"""
    for u in users:
        name = u.full_name
        html = _html_wrapper(f"""
<div style="text-align:center;margin:30px 0;">
  <div style="font-size:48px;">📢</div>
  <h2 style="color:#2C3E50;">مرحباً {name}،</h2>
  <div style="background:#F5F7FA;padding:20px;border-radius:10px;margin:20px;">
    <p><strong>{subject}</strong></p>
    <p>{body}</p>
  </div>
</div>""")
        text = f"ARS System - إشعار جديد\n\nمرحباً {name}،\n\n{subject}\n{body}"
        _send(u.email or '', name, subject, html, text)


def send_welcome(user, password, login_url=''):
    """مطابق لـ v54 template welcome — لاستيراد المستخدمين"""
    name = user.full_name; uname = user.username
    html = _html_wrapper(f"""
<div style="text-align:center;margin:30px 0;">
  <div style="font-size:48px;">👋</div>
  <h2 style="color:#2C3E50;">مرحباً بك {name} في ARS Applied Reservation!</h2>
  <p style="font-size:16px;">تم إنشاء حسابك بنجاح. يمكنك الآن تسجيل الدخول باستخدام البيانات التالية:</p>
  <div style="background:#F5F7FA;padding:20px;border-radius:10px;margin:20px;text-align:right;">
    <p><strong>اسم المستخدم:</strong> {uname}</p>
    <p><strong>كلمة المرور:</strong> {password}</p>
    <p><strong>رابط الدخول:</strong> <a href="{login_url}">{login_url}</a></p>
  </div>
  <p>نوصي بتغيير كلمة المرور بعد أول تسجيل دخول.</p>
</div>""")
    text = f"ARS System - مرحباً بك\n\nمرحباً {name}،\n\naسم المستخدم: {uname}\nكلمة المرور: {password}\nرابط الدخول: {login_url}"
    _send(user.email or '', name, 'مرحباً بك في ARS Applied Reservation', html, text)


def test_smtp(smtp_server, smtp_port, email, password, use_tls=True, brevo_api_key=None):
    """اختبار الاتصال — يدعم Brevo API و SMTP"""
    # ── Brevo API test ────────────────────────────────────────────────────────
    if brevo_api_key:
        try:
            import urllib.request
            req = urllib.request.Request(
                'https://api.brevo.com/v3/account',
                headers={'api-key': brevo_api_key, 'Accept': 'application/json'},
                method='GET'
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    import json as _j
                    data = _j.loads(resp.read().decode())
                    plan = data.get('plan', [{}])
                    credits = plan[0].get('credits', '?') if plan else '?'
                    return True, f'✅ Brevo API متصل — Credits: {credits}'
        except Exception as e:
            return False, f'Brevo API Error: {e}'
    # ── SMTP test ─────────────────────────────────────────────────────────────
    try:
        port = int(smtp_port)
        if port == 465:
            import ssl
            ctx = ssl.create_default_context()
            srv = smtplib.SMTP_SSL(smtp_server, port, timeout=15, context=ctx)
            srv.ehlo()
        else:
            srv = smtplib.SMTP(smtp_server, port, timeout=15)
            srv.ehlo()
            if use_tls:
                srv.starttls()
                srv.ehlo()
        srv.login(email, password)
        srv.quit()
        return True, 'تم الاتصال بنجاح ✅'
    except Exception as e:
        return False, str(e)


def send_reset_code(email: str, code: str) -> bool:
    subject = 'ARS — رمز إعادة تعيين كلمة المرور'
    body = _html_wrapper(f"""
<h2 style="color:#0C67EC;margin:0 0 8px;font-size:19px">إعادة تعيين كلمة المرور</h2>
<p style="color:#4a5568;margin:0 0 20px">استخدم الرمز أدناه لإعادة تعيين كلمة مرورك:</p>
<div style="background:linear-gradient(135deg,#EEF4FD,#E8F0FE);border:2px dashed #0C67EC;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;font-weight:900;letter-spacing:12px;color:#0C67EC;font-variant-numeric:tabular-nums">{code}</div>
</div>
<div style="background:#FFF3E0;border-right:4px solid #FB8C00;border-radius:8px;padding:10px 14px;color:#E65100;font-size:13px">
  ⏰ صالح لمدة <strong>10 دقائق</strong> فقط. لا تشاركه مع أحد.
</div>
""", 'إعادة تعيين كلمة المرور')
    return _send(email, '', subject, body, f'Reset code: {code}', sync=True)


def send_verification_code(email: str, code: str, full_name: str = '') -> bool:
    subject = 'ARS — رمز التحقق من البريد الإلكتروني'
    body = _html_wrapper(f"""
<h2 style="color:#0C67EC;margin:0 0 8px;font-size:19px">مرحباً{' ' + full_name if full_name else ''} 👋</h2>
<p style="color:#4a5568;margin:0 0 20px">شكراً لتسجيلك في نظام ARS. أدخل الرمز أدناه لتفعيل حسابك:</p>
<div style="background:linear-gradient(135deg,#EEF4FD,#E8F0FE);border:2px dashed #0C67EC;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;font-weight:900;letter-spacing:12px;color:#0C67EC;font-variant-numeric:tabular-nums">{code}</div>
</div>
<div style="background:#E8F5E9;border-right:4px solid #43A047;border-radius:8px;padding:10px 14px;color:#2E7D32;font-size:13px">
  ⏰ صالح لمدة <strong>15 دقيقة</strong> فقط.
</div>
""", 'تحقق من البريد الإلكتروني')
    return _send(email, full_name, subject, body, f'Verification code: {code}', sync=True)


def send_employee_reservation_notice(employee, res, requester):
    """إشعار الموظف المطلوب بوجود حجز يخصه"""
    name  = employee.full_name or employee.username
    title = res.title
    venue = res.venue.name if res.venue else '—'
    loc   = res.venue.location.name if (res.venue and res.venue.location) else '—'
    start = res.start_time.strftime('%Y-%m-%d  %H:%M') if res.start_time else '—'
    end   = res.end_time.strftime('%H:%M') if res.end_time else '—'
    req_name = requester.full_name or requester.username
    html = _html_wrapper(f"""
<div dir="rtl" style="font-family:Tajawal,Arial;max-width:560px;margin:auto">
  <div style="background:linear-gradient(135deg,#0847B0,#0C67EC);padding:28px;text-align:center;border-radius:14px 14px 0 0">
    <div style="font-size:2.5rem">✉️</div>
    <h2 style="color:#fff;margin:8px 0 4px">إشعار حجز</h2>
    <p style="color:rgba(255,255,255,.7);font-size:.88rem;margin:0">ARS — Applied Reservation System</p>
  </div>
  <div style="background:#fff;padding:28px;border-radius:0 0 14px 14px;border:1px solid #e0ecec">
    <p style="font-size:1rem">مرحباً <strong>{name}</strong>،</p>
    <p>تم تضمينك كموظف مطلوب في الحجز التالي:</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:.9rem">
      <tr style="background:#f4f9fa"><td style="padding:10px 14px;font-weight:700;color:#0C67EC;width:35%">عنوان الحجز</td><td style="padding:10px 14px">{title}</td></tr>
      <tr><td style="padding:10px 14px;font-weight:700;color:#0C67EC">القاعة</td><td style="padding:10px 14px">{venue} — {loc}</td></tr>
      <tr style="background:#f4f9fa"><td style="padding:10px 14px;font-weight:700;color:#0C67EC">الوقت</td><td style="padding:10px 14px">{start} — {end}</td></tr>
      <tr><td style="padding:10px 14px;font-weight:700;color:#0C67EC">رقم الحجز</td><td style="padding:10px 14px;color:#D4A853;font-weight:700">{res.booking_number}</td></tr>
      <tr style="background:#f4f9fa"><td style="padding:10px 14px;font-weight:700;color:#0C67EC">طلب بواسطة</td><td style="padding:10px 14px">{req_name}</td></tr>
    </table>
    <p style="color:#666;font-size:.82rem">يُرجى مراجعة النظام للاطلاع على التفاصيل الكاملة.</p>
  </div>
</div>""")
    text = f"إشعار حجز — ARS\n\nمرحباً {name}،\nتم تضمينك كموظف مطلوب في: {title}\nالقاعة: {venue}\nالوقت: {start} — {end}\nرقم الحجز: {res.booking_number}\nطلب بواسطة: {req_name}"
    _send(employee.email or '', name, f'ARS — إشعار حجز: {title}', html, text)
