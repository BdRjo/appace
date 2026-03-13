"""
مساعد البريد الإلكتروني — مطابق لـ v54 EmailSystem._get_template
جميع القوالب مطابقة حرفياً للـ v54
"""
import smtplib, json, os, threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

CONFIG_FILE = __import__('os').environ.get('EMAIL_CONFIG_PATH', __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))), 'email_config.json'))

PROVIDERS = {
    'gmail':     {'label': 'Gmail',                  'smtp': 'smtp.gmail.com',          'port': 587},
    'office365': {'label': 'Microsoft 365 / Outlook','smtp': 'smtp.office365.com',       'port': 587},
    'outlook':   {'label': 'Outlook.com (Hotmail)',  'smtp': 'smtp-mail.outlook.com',    'port': 587},
    'yahoo':     {'label': 'Yahoo Mail',             'smtp': 'smtp.mail.yahoo.com',      'port': 587},
    'brevo':     {'label': 'Brevo (Sendinblue)',      'smtp': 'smtp-relay.brevo.com',     'port': 587},
    'custom':    {'label': 'خادم مخصص',              'smtp': '',                          'port': 587},
}

def _load_config():
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    except:
        return {
            'smtp_server':    'smtp.gmail.com',
            'smtp_port':      587,
            'sender_email':   'baderaq@gmail.com',
            'sender_password':'daqr uxbv pzee pwug',
            'sender_name':    'ARS Applied Reservation System',
            'use_tls':        True,
            'provider_key':   'gmail',
        }

def _html_wrapper(content):
    """HTML wrapper — مطابق لـ v54 EmailSystem._get_template"""
    return f"""<!DOCTYPE html>
<html dir="rtl">
<head>
<meta charset="UTF-8">
<title>ARS Applied Reservation</title>
<style>
body{{font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:linear-gradient(135deg,#2C3E50 0%,#3498DB 100%);margin:0;padding:20px;direction:rtl;}}
.container{{max-width:600px;margin:0 auto;background:white;border-radius:20px;box-shadow:0 10px 40px rgba(0,0,0,.1);overflow:hidden;}}
.header{{background:#2C3E50;padding:30px;text-align:center;}}
.header h1{{color:white;margin:0;font-size:28px;}}
.content{{padding:40px 30px;}}
.footer{{background:#F5F7FA;padding:20px;text-align:center;color:#7F8C8D;font-size:12px;}}
</style>
</head>
<body>
<div class="container">
  <div class="header"><h1>👑 ARS Applied Reservation</h1></div>
  <div class="content">{content}</div>
  <div class="footer">
    <p>جميع الحقوق محفوظة © 2026 ARS</p>
    <p>هذا بريد إلكتروني تلقائي، الرجاء عدم الرد عليه</p>
  </div>
</div>
</body>
</html>"""

def _send(to_email, to_name, subject, html, text, sync=False):
    """إرسال بريد — مطابق لـ v54 EmailSystem.send_email
    sync=True  → ينتظر النتيجة ويرجع True/False (للـ reset code والـ verification)
    sync=False → يرسل في background thread (للإشعارات العادية)
    """
    cfg = _load_config()

    def _do_send():
        msg = MIMEMultipart('alternative')
        msg['From']    = f"{cfg.get('sender_name','ARS')} <{cfg.get('sender_email','')}>"
        msg['To']      = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(text, 'plain', 'utf-8'))
        msg.attach(MIMEText(html, 'html',  'utf-8'))
        srv = smtplib.SMTP(cfg['smtp_server'], int(cfg['smtp_port']), timeout=30)
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


def send_booking_request(user, res):
    """مطابق لـ v54 template booking_request"""
    name  = user.full_name
    bn    = res.booking_number
    title = res.title
    html  = _html_wrapper(f"""
<div style="text-align:center;margin:30px 0;">
  <div style="font-size:48px;">📅</div>
  <h2 style="color:#2C3E50;">مرحباً {name}،</h2>
  <p style="font-size:16px;">تم استلام طلب الحجز الخاص بك:</p>
  <div style="background:#F5F7FA;padding:20px;border-radius:10px;margin:20px;">
    <p><strong>الرقم المرجعي:</strong> {bn}</p>
    <p><strong>العنوان:</strong> {title}</p>
  </div>
  <p>سيتم إعلامك بقرار الموافقة قريباً.</p>
</div>""")
    text = f"ARS System - طلب حجز جديد\n\nمرحباً {name}،\n\nتم استلام طلب الحجز:\nالرقم المرجعي: {bn}\nالعنوان: {title}\n\nسيتم إعلامك بقرار الموافقة قريباً."
    _send(user.email or '', name, 'طلب حجز جديد - ARS', html, text)


def send_booking_approved(res):
    """مطابق لـ v54 template approval"""
    if not res.user: return
    name = res.user.full_name; bn = res.booking_number; title = res.title
    html = _html_wrapper(f"""
<div style="text-align:center;margin:30px 0;">
  <div style="font-size:48px;">✅</div>
  <h2 style="color:#2C3E50;">تهانينا {name}،</h2>
  <p style="font-size:16px;">تمت الموافقة على حجزك:</p>
  <div style="background:#D4EDDA;padding:20px;border-radius:10px;margin:20px;">
    <p><strong>الرقم المرجعي:</strong> {bn}</p>
    <p><strong>العنوان:</strong> {title}</p>
  </div>
</div>""")
    text = f"ARS System - تمت الموافقة على الحجز\n\nمرحباً {name}،\nتمت الموافقة على حجزك:\nالرقم المرجعي: {bn}\nالعنوان: {title}"
    _send(res.user.email or '', name, 'تمت الموافقة على حجزك - ARS', html, text)


def send_booking_rejected(res, reason=''):
    """مطابق لـ v54 template rejection"""
    if not res.user: return
    name = res.user.full_name; bn = res.booking_number; title = res.title
    html = _html_wrapper(f"""
<div style="text-align:center;margin:30px 0;">
  <div style="font-size:48px;">❌</div>
  <h2 style="color:#2C3E50;">عذراً {name}،</h2>
  <p style="font-size:16px;">تم رفض حجزك:</p>
  <div style="background:#F8D7DA;padding:20px;border-radius:10px;margin:20px;">
    <p><strong>الرقم المرجعي:</strong> {bn}</p>
    <p><strong>العنوان:</strong> {title}</p>
    <p><strong>السبب:</strong> {reason}</p>
  </div>
</div>""")
    text = f"ARS System - تم رفض الحجز\n\nمرحباً {name}،\nتم رفض حجزك:\nالرقم المرجعي: {bn}\nالعنوان: {title}\nالسبب: {reason}"
    _send(res.user.email or '', name, 'تم رفض حجزك - ARS', html, text)


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
    <p><strong>📅 التاريخ:</strong> {start}</p>
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


def test_smtp(smtp_server, smtp_port, email, password, use_tls=True):
    """مطابق لـ v54 EmailConfigWindow test button"""
    try:
        srv = smtplib.SMTP(smtp_server, int(smtp_port), timeout=10)
        srv.ehlo()
        if use_tls: srv.starttls(); srv.ehlo()
        srv.login(email, password)
        srv.quit()
        return True, 'تم الاتصال بنجاح ✅'
    except Exception as e:
        return False, str(e)


def send_reset_code(email: str, code: str) -> bool:
    """إرسال كود إعادة تعيين كلمة المرور"""
    subject = f'ARS — رمز إعادة تعيين كلمة المرور: {code}'
    body = f"""
    <div dir="rtl" style="font-family:Tajawal,Arial;max-width:480px;margin:auto;
         border:1px solid #e0eaeb;border-radius:12px;overflow:hidden">
      <div style="background:#1A555C;padding:20px;text-align:center">
        <h2 style="color:#fff;margin:0">ARS — Applied Reservation System</h2>
      </div>
      <div style="padding:28px">
        <h3 style="color:#1A555C">إعادة تعيين كلمة المرور</h3>
        <p>رمز التحقق الخاص بك هو:</p>
        <div style="background:#F4F7F8;border:2px dashed #1A555C;border-radius:8px;
             padding:16px;text-align:center;font-size:2.2rem;font-weight:800;
             letter-spacing:.8rem;color:#1A555C">{code}</div>
        <p style="color:#666;font-size:.88rem;margin-top:16px">
          صالح لمدة <strong>10 دقائق</strong>. لا تشاركه مع أحد.
        </p>
      </div>
    </div>
    """
    return _send(email, '', subject, body, f'Reset code: {code}', sync=True)


def send_verification_code(email: str, code: str, full_name: str = '') -> bool:
    """إرسال كود التحقق عند التسجيل"""
    subject = f'ARS — رمز التحقق من البريد الإلكتروني: {code}'
    body = f"""
    <div dir="rtl" style="font-family:Tajawal,Arial;max-width:480px;margin:auto;
         border:1px solid #e0eaeb;border-radius:12px;overflow:hidden">
      <div style="background:#1A555C;padding:20px;text-align:center">
        <h2 style="color:#fff;margin:0">ARS — Applied Reservation System</h2>
      </div>
      <div style="padding:28px">
        <h3 style="color:#1A555C">مرحباً{' ' + full_name if full_name else ''}!</h3>
        <p>رمز التحقق من البريد الإلكتروني:</p>
        <div style="background:#F4F7F8;border:2px dashed #1A555C;border-radius:8px;
             padding:16px;text-align:center;font-size:2.2rem;font-weight:800;
             letter-spacing:.8rem;color:#1A555C">{code}</div>
        <p style="color:#666;font-size:.88rem;margin-top:16px">صالح لمدة 10 دقائق.</p>
      </div>
    </div>
    """
    return _send(email, full_name, subject, body, f'Verification code: {code}', sync=True)
