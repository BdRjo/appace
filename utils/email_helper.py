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

# ── Template Registry ─────────────────────────────────────────────────────────
TEMPLATE_REGISTRY = {
    'booking_request': {
        'name_ar': 'طلب حجز جديد',
        'name_en': 'Booking Request Received',
        'variables': ['name', 'booking_number', 'title'],
        'default_subject_ar': '📋 طلب حجز جديد — ARS',
        'default_subject_en': '📋 New Booking Request — ARS',
        'default_body_ar': '''<h2 style="color:#0C67EC;margin:0 0 6px;font-size:20px">مرحباً {{name}}،</h2>
<p style="color:#4a5568;margin:0 0 20px">تم استلام طلب الحجز الخاص بك بنجاح، وسيتم مراجعته من قِبل المختصين.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">📋 رقم الحجز</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600"><strong style="color:#0C67EC">{{booking_number}}</strong></td></tr>
  <tr><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#6b7c99;width:35%">📌 العنوان</td><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#2d3748;font-weight:600">{{title}}</td></tr>
</table>
<div style="background:linear-gradient(135deg,#EEF4FD,#E8F0FE);border-right:4px solid #0C67EC;border-radius:8px;padding:12px 16px;color:#4a5568;font-size:14px">
  ⏳ سيتم إعلامك بقرار الموافقة في أقرب وقت.
</div>''',
        'default_body_en': '''<h2 style="color:#0C67EC;margin:0 0 6px;font-size:20px">Hello {{name}},</h2>
<p style="color:#4a5568;margin:0 0 20px">Your booking request has been received and will be reviewed shortly.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">📋 Booking No.</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600"><strong style="color:#0C67EC">{{booking_number}}</strong></td></tr>
  <tr><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#6b7c99;width:35%">📌 Title</td><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#2d3748;font-weight:600">{{title}}</td></tr>
</table>
<div style="background:linear-gradient(135deg,#EEF4FD,#E8F0FE);border-left:4px solid #0C67EC;border-radius:8px;padding:12px 16px;color:#4a5568;font-size:14px">
  ⏳ You will be notified once a decision is made.
</div>''',
    },
    'booking_approved': {
        'name_ar': 'تمت الموافقة على الحجز',
        'name_en': 'Booking Approved',
        'variables': ['name', 'booking_number', 'title', 'venue', 'start_time'],
        'default_subject_ar': '✅ تمت الموافقة على حجزك — ARS',
        'default_subject_en': '✅ Booking Approved — ARS',
        'default_body_ar': '''<div style="background:linear-gradient(135deg,#E8F5E9,#F1F8E9);border-radius:10px;padding:16px 20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;margin-bottom:6px">✅</div>
  <h2 style="color:#1B5E20;margin:0;font-size:18px">تهانينا {{name}}! تمت الموافقة على حجزك</h2>
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #C8E6C9;margin-bottom:20px">
  <tr><td style="padding:10px 14px;background:#F1F8E9;font-size:13px;color:#6b7c99;width:35%">📋 رقم الحجز</td><td style="padding:10px 14px;background:#F1F8E9;font-size:13px;color:#2d3748;font-weight:600"><strong style="color:#0C67EC">{{booking_number}}</strong></td></tr>
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">📌 العنوان</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{title}}</td></tr>
  <tr><td style="padding:10px 14px;background:#F1F8E9;font-size:13px;color:#6b7c99;width:35%">🏢 القاعة</td><td style="padding:10px 14px;background:#F1F8E9;font-size:13px;color:#2d3748;font-weight:600">{{venue}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">🕐 الوقت</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{start_time}}</td></tr>
</table>
<div style="background:#E8F5E9;border-right:4px solid #43A047;border-radius:8px;padding:12px 16px;color:#2E7D32;font-size:14px">
  ✅ حجزك معتمد ومؤكد. نتمنى لك تجربة رائعة!
</div>''',
        'default_body_en': '''<div style="background:linear-gradient(135deg,#E8F5E9,#F1F8E9);border-radius:10px;padding:16px 20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;margin-bottom:6px">✅</div>
  <h2 style="color:#1B5E20;margin:0;font-size:18px">Congratulations {{name}}! Your booking has been approved.</h2>
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #C8E6C9;margin-bottom:20px">
  <tr><td style="padding:10px 14px;background:#F1F8E9;font-size:13px;color:#6b7c99;width:35%">📋 Booking No.</td><td style="padding:10px 14px;background:#F1F8E9;font-size:13px;color:#2d3748;font-weight:600"><strong style="color:#0C67EC">{{booking_number}}</strong></td></tr>
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">📌 Title</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{title}}</td></tr>
  <tr><td style="padding:10px 14px;background:#F1F8E9;font-size:13px;color:#6b7c99;width:35%">🏢 Venue</td><td style="padding:10px 14px;background:#F1F8E9;font-size:13px;color:#2d3748;font-weight:600">{{venue}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">🕐 Time</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{start_time}}</td></tr>
</table>
<div style="background:#E8F5E9;border-left:4px solid #43A047;border-radius:8px;padding:12px 16px;color:#2E7D32;font-size:14px">
  ✅ Your booking is confirmed. We hope you have a great experience!
</div>''',
    },
    'booking_rejected': {
        'name_ar': 'تم رفض الحجز',
        'name_en': 'Booking Rejected',
        'variables': ['name', 'booking_number', 'title', 'reason'],
        'default_subject_ar': '❌ تم رفض طلب الحجز — ARS',
        'default_subject_en': '❌ Booking Not Approved — ARS',
        'default_body_ar': '''<div style="background:linear-gradient(135deg,#FFEBEE,#FCE4EC);border-radius:10px;padding:16px 20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;margin-bottom:6px">❌</div>
  <h2 style="color:#B71C1C;margin:0;font-size:18px">عذراً {{name}}، تم رفض طلب الحجز</h2>
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #FFCDD2;margin-bottom:20px">
  <tr><td style="padding:10px 14px;background:#FFF3F3;font-size:13px;color:#6b7c99;width:35%">📋 رقم الحجز</td><td style="padding:10px 14px;background:#FFF3F3;font-size:13px;color:#2d3748;font-weight:600"><strong>{{booking_number}}</strong></td></tr>
  <tr><td style="padding:10px 14px;background:#FFFAFA;font-size:13px;color:#6b7c99;width:35%">📌 العنوان</td><td style="padding:10px 14px;background:#FFFAFA;font-size:13px;color:#2d3748;font-weight:600">{{title}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FFF3F3;font-size:13px;color:#6b7c99;width:35%">📝 السبب</td><td style="padding:10px 14px;background:#FFF3F3;font-size:13px;color:#2d3748;font-weight:600">{{reason}}</td></tr>
</table>
<div style="background:#FFF3E0;border-right:4px solid #FB8C00;border-radius:8px;padding:12px 16px;color:#E65100;font-size:14px">
  💡 يمكنك التواصل مع الإدارة أو تقديم طلب جديد.
</div>''',
        'default_body_en': '''<div style="background:linear-gradient(135deg,#FFEBEE,#FCE4EC);border-radius:10px;padding:16px 20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;margin-bottom:6px">❌</div>
  <h2 style="color:#B71C1C;margin:0;font-size:18px">Sorry {{name}}, your booking request was not approved.</h2>
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #FFCDD2;margin-bottom:20px">
  <tr><td style="padding:10px 14px;background:#FFF3F3;font-size:13px;color:#6b7c99;width:35%">📋 Booking No.</td><td style="padding:10px 14px;background:#FFF3F3;font-size:13px;color:#2d3748;font-weight:600"><strong>{{booking_number}}</strong></td></tr>
  <tr><td style="padding:10px 14px;background:#FFFAFA;font-size:13px;color:#6b7c99;width:35%">📌 Title</td><td style="padding:10px 14px;background:#FFFAFA;font-size:13px;color:#2d3748;font-weight:600">{{title}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FFF3F3;font-size:13px;color:#6b7c99;width:35%">📝 Reason</td><td style="padding:10px 14px;background:#FFF3F3;font-size:13px;color:#2d3748;font-weight:600">{{reason}}</td></tr>
</table>
<div style="background:#FFF3E0;border-left:4px solid #FB8C00;border-radius:8px;padding:12px 16px;color:#E65100;font-size:14px">
  💡 You may contact the administration or submit a new request.
</div>''',
    },
    'booking_cancelled': {
        'name_ar': 'إلغاء الحجز',
        'name_en': 'Booking Cancelled',
        'variables': ['name', 'booking_number', 'title'],
        'default_subject_ar': '🚫 تم إلغاء الحجز — ARS',
        'default_subject_en': '🚫 Booking Cancelled — ARS',
        'default_body_ar': '''<h2 style="color:#546E7A;margin:0 0 12px">مرحباً {{name}}،</h2>
<p style="color:#4a5568">تم <strong style="color:#c0392b">إلغاء</strong> الحجز رقم <strong style="color:#0C67EC">{{booking_number}}</strong> — "{{title}}".</p>
<div style="background:#f5f5f5;border-right:4px solid #546E7A;border-radius:8px;padding:12px 16px;color:#546E7A;font-size:14px;margin-top:16px">
  إذا كان هذا خطأ، يرجى التواصل مع الإدارة.
</div>''',
        'default_body_en': '''<h2 style="color:#546E7A;margin:0 0 12px">Hello {{name}},</h2>
<p style="color:#4a5568">Booking <strong style="color:#0C67EC">{{booking_number}}</strong> — "{{title}}" has been <strong style="color:#c0392b">cancelled</strong>.</p>
<div style="background:#f5f5f5;border-left:4px solid #546E7A;border-radius:8px;padding:12px 16px;color:#546E7A;font-size:14px;margin-top:16px">
  If you believe this is an error, please contact the administration.
</div>''',
    },
    'invitation': {
        'name_ar': 'دعوة لحضور فعالية',
        'name_en': 'Event Invitation',
        'variables': ['name', 'title', 'venue', 'start_time', 'message_body'],
        'default_subject_en': '📩 Invitation: {{title}}',
        'default_subject_ar': '📩 دعوة: {{title}}',
        'default_body_en': '''<h2 style="color:#0C67EC;margin:0 0 12px">Dear {{name}},</h2>
<p style="color:#4a5568">You are cordially invited to:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin:16px 0">
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">📌 Event</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{title}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#6b7c99;width:35%">🏢 Venue</td><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#2d3748;font-weight:600">{{venue}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">📅 Date & Time</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{start_time}}</td></tr>
</table>
<p style="color:#4a5568;margin-top:12px">{{message_body}}</p>''',
        'default_body_ar': '''<h2 style="color:#0C67EC;margin:0 0 12px">عزيزي {{name}}،</h2>
<p style="color:#4a5568">يسرنا دعوتك لحضور:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin:16px 0">
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">📌 الفعالية</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{title}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#6b7c99;width:35%">🏢 المكان</td><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#2d3748;font-weight:600">{{venue}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">📅 التاريخ والوقت</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{start_time}}</td></tr>
</table>
<p style="color:#4a5568;margin-top:12px">{{message_body}}</p>''',
    },
    'welcome': {
        'name_ar': 'ترحيب بمستخدم جديد',
        'name_en': 'New User Welcome',
        'variables': ['name', 'username', 'password', 'login_url'],
        'default_subject_ar': 'مرحباً بك في ARS — نظام إدارة الحجوزات',
        'default_subject_en': 'Welcome to ARS — Applied Reservation System',
        'default_body_ar': '''<h2 style="color:#0C67EC;margin:0 0 12px">مرحباً بك في ARS، {{name}}! 🎉</h2>
<p style="color:#4a5568;margin:0 0 16px">تم إنشاء حسابك بنجاح. بيانات الدخول الخاصة بك:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">👤 اسم المستخدم</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{username}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#6b7c99;width:35%">🔑 كلمة المرور</td><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#2d3748;font-weight:600"><code style="background:#f4f9ff;padding:2px 6px;border-radius:4px">{{password}}</code></td></tr>
</table>
<p style="color:#999;font-size:12px;margin-top:16px">يُرجى تغيير كلمة المرور بعد أول دخول.</p>''',
        'default_body_en': '''<h2 style="color:#0C67EC;margin:0 0 12px">Welcome to ARS, {{name}}! 🎉</h2>
<p style="color:#4a5568;margin:0 0 16px">Your account has been created. Here are your login credentials:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">👤 Username</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{username}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#6b7c99;width:35%">🔑 Password</td><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#2d3748;font-weight:600"><code style="background:#f4f9ff;padding:2px 6px;border-radius:4px">{{password}}</code></td></tr>
</table>
<p style="color:#999;font-size:12px;margin-top:16px">Please change your password after first login.</p>''',
    },
    'reset_code': {
        'name_ar': 'رمز إعادة تعيين كلمة المرور',
        'name_en': 'Password Reset Code',
        'variables': ['code'],
        'default_subject_ar': 'ARS — رمز إعادة تعيين كلمة المرور',
        'default_subject_en': 'ARS — Password Reset Code',
        'default_body_ar': '''<p style="color:#4a5568;margin:0 0 20px">استخدم الرمز أدناه لإعادة تعيين كلمة مرورك:</p>
<div style="background:#f4f9ff;border:2px dashed #0C67EC;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;font-weight:900;letter-spacing:12px;color:#0C67EC">{{code}}</div>
</div>
<p style="color:#999;font-size:12px">صالح لمدة 15 دقيقة. لا تشاركه مع أحد.</p>''',
        'default_body_en': '''<p style="color:#4a5568;margin:0 0 20px">Use the code below to reset your password:</p>
<div style="background:#f4f9ff;border:2px dashed #0C67EC;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;font-weight:900;letter-spacing:12px;color:#0C67EC">{{code}}</div>
</div>
<p style="color:#999;font-size:12px">This code expires in 15 minutes. Do not share it with anyone.</p>''',
    },
    'verification_code': {
        'name_ar': 'رمز التحقق من البريد',
        'name_en': 'Email Verification Code',
        'variables': ['name', 'code'],
        'default_subject_ar': 'ARS — رمز التحقق من البريد الإلكتروني',
        'default_subject_en': 'ARS — Email Verification Code',
        'default_body_ar': '''<p style="color:#4a5568;margin:0 0 20px">شكراً لتسجيلك في نظام ARS. أدخل الرمز أدناه لتفعيل حسابك:</p>
<div style="background:#f4f9ff;border:2px dashed #0C67EC;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;font-weight:900;letter-spacing:12px;color:#0C67EC">{{code}}</div>
</div>''',
        'default_body_en': '''<p style="color:#4a5568;margin:0 0 20px">Thank you for registering in ARS. Enter the code below to verify your account:</p>
<div style="background:#f4f9ff;border:2px dashed #0C67EC;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:36px;font-weight:900;letter-spacing:12px;color:#0C67EC">{{code}}</div>
</div>''',
    },
    'employee_reservation_notice': {
        'name_ar': 'تعيين في حجز',
        'name_en': 'Reservation Assignment',
        'variables': ['name', 'requester_name', 'booking_number', 'title', 'venue', 'start_time'],
        'default_subject_ar': '📋 تعيين في حجز — {{booking_number}}',
        'default_subject_en': '📋 Reservation Assignment — {{booking_number}}',
        'default_body_ar': '''<h2 style="color:#0C67EC;margin:0 0 12px">مرحباً {{name}}،</h2>
<p style="color:#4a5568">تم تعيينك في الحجز التالي من قِبل <strong>{{requester_name}}</strong>:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin:16px 0">
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">📋 رقم الحجز</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{booking_number}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#6b7c99;width:35%">📌 العنوان</td><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#2d3748;font-weight:600">{{title}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">🏢 القاعة</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{venue}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#6b7c99;width:35%">🕐 الوقت</td><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#2d3748;font-weight:600">{{start_time}}</td></tr>
</table>''',
        'default_body_en': '''<h2 style="color:#0C67EC;margin:0 0 12px">Hello {{name}},</h2>
<p style="color:#4a5568">You have been assigned to the following reservation by <strong>{{requester_name}}</strong>:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin:16px 0">
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">📋 Booking No.</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{booking_number}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#6b7c99;width:35%">📌 Title</td><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#2d3748;font-weight:600">{{title}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#6b7c99;width:35%">🏢 Venue</td><td style="padding:10px 14px;background:#FAFFFE;font-size:13px;color:#2d3748;font-weight:600">{{venue}}</td></tr>
  <tr><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#6b7c99;width:35%">🕐 Time</td><td style="padding:10px 14px;background:#FAFCFF;font-size:13px;color:#2d3748;font-weight:600">{{start_time}}</td></tr>
</table>''',
    },
}

def _resolve_template(template_key, lang, variables_dict):
    """Check DB for custom template override, fall back to defaults."""
    registry = TEMPLATE_REGISTRY.get(template_key)
    if not registry:
        return None, None
    subject = None
    body = None
    try:
        from models.database import EmailTemplate, get_engine
        from sqlalchemy.orm import sessionmaker
        engine = get_engine()
        Session = sessionmaker(bind=engine)
        s = Session()
        tpl = s.query(EmailTemplate).filter_by(key=template_key, is_active=True).first()
        if tpl:
            if lang == 'en':
                subject = tpl.subject_en if tpl.subject_en else None
                body = tpl.body_en if tpl.body_en else None
            else:
                subject = tpl.subject_ar if tpl.subject_ar else None
                body = tpl.body_ar if tpl.body_ar else None
        s.close()
    except Exception as e:
        print(f'Template DB lookup error: {e}')
    if not subject:
        subject = registry.get(f'default_subject_{lang}', '')
    if not body:
        body = registry.get(f'default_body_{lang}', '')
    for key, value in variables_dict.items():
        body = body.replace('{{' + key + '}}', str(value if value else ''))
        subject = subject.replace('{{' + key + '}}', str(value if value else ''))
    return subject, body


def _info_row(label, value, bg='#FAFFFE'):
    return f'<tr><td style="padding:10px 14px;background:{bg};font-size:13px;color:#6b7c99;width:35%">{label}</td><td style="padding:10px 14px;background:{bg};font-size:13px;color:#2d3748;font-weight:600">{value}</td></tr>'


def _send_via_smtp(smtp_host, smtp_port, sender_email, sender_password, use_tls,
                    sender_name, to_email, to_name, subject, html, text):
    """Send one email over real SMTP (Gmail, Office 365, Outlook, Yahoo,
    Brevo SMTP relay, or any custom server) — used for every provider other
    than the Brevo HTTP API."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formataddr

    if not smtp_host:
        raise ValueError('SMTP server address is missing')
    if not sender_email:
        raise ValueError('Sender email is missing')

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = formataddr((sender_name or sender_email, sender_email))
    msg['To'] = formataddr((to_name or to_email, to_email))
    msg.attach(MIMEText(text or subject or 'Notification', 'plain', 'utf-8'))
    msg.attach(MIMEText(html or '', 'html', 'utf-8'))

    smtp_port = int(smtp_port or 587)
    if smtp_port == 465:
        # Implicit TLS from the start of the connection
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
            if sender_password:
                server.login(sender_email, sender_password)
            server.sendmail(sender_email, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            if sender_password:
                server.login(sender_email, sender_password)
            server.sendmail(sender_email, [to_email], msg.as_string())

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
                html_body=html,
                user_id=user_id,
            )
            s.add(log)
            s.commit()
            s.close()
        except Exception as le:
            print(f'EmailLog write error: {le}')

    def _do_send():
        cfg = _get_cfg()
        provider = cfg.get('provider_key', 'brevo_api')
        sender_email = cfg.get('sender_email', '')
        sender_name = cfg.get('sender_name', 'ARS')

        # Any provider other than the Brevo HTTP API goes over real SMTP —
        # Gmail, Office 365 / Outlook, Outlook.com, Yahoo, Brevo's own SMTP
        # relay, or a fully custom server.
        if provider != 'brevo_api':
            smtp_host = cfg.get('smtp_server', '')
            smtp_port = cfg.get('smtp_port', 587)
            sender_password = cfg.get('sender_password', '')
            use_tls = cfg.get('use_tls', True)
            if not sender_email:
                print('Email error: Sender email is missing — configure it in Admin → Email Settings')
                _log_result('failed', 'Sender email missing')
                return False
            try:
                _send_via_smtp(smtp_host, smtp_port, sender_email, sender_password, use_tls,
                                sender_name, to_email, to_name, subject, html, text)
                _log_result('sent')
                return True
            except Exception as e:
                msg = f'SMTP error ({provider}): {e}'
                print(f'Email error: {msg}')
                _log_result('failed', msg)
                return False

        # Brevo HTTP API
        try:
            api_key = cfg.get('api_key') or cfg.get('brevo_api_key', '')
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


def send_email(to_email, to_name='', subject='', html_body='', text_body='', sync=False, email_type='notification'):
    """Generic send email — public wrapper used by interviews module and other callers."""
    return _send(to_email=to_email, to_name=to_name, subject=subject,
                 html=html_body, text=text_body, sync=sync,
                 email_type=email_type)


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
    """Notify user their booking request was received — full details"""
    lang  = _user_lang(user)
    name  = user.full_name or user.username
    bn    = res.booking_number
    title = res.title

    # Custom template override
    _subj, _body = _resolve_template('booking_request', lang, {
        'name': name, 'booking_number': bn, 'title': title})
    if _body:
        _send(user.email or '', name, _subj, _html_wrapper(_body, _subj, lang),
              '', sync=True, email_type='notification')
        return

    detail_rows = _build_reservation_details_rows(res, lang)

    if lang == 'en':
        content = f"""
<h2 style="color:#0C67EC;margin:0 0 6px;font-size:20px">Hello {name},</h2>
<p style="color:#4a5568;margin:0 0 20px">Your booking request has been received and will be reviewed shortly.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  {detail_rows}
</table>
<div style="background:linear-gradient(135deg,#EEF4FD,#E8F0FE);border-left:4px solid #0C67EC;border-radius:8px;padding:12px 16px;color:#4a5568;font-size:14px">
  ⏳ You will be notified once a decision is made.
</div>"""
        subj = '📋 New Booking Request — ARS'
        txt  = f"ARS — Booking Request\n\nHello {name},\nRef: {bn}\nTitle: {title}\n\nYou will be notified soon."
    else:
        content = f"""
<h2 style="color:#0C67EC;margin:0 0 6px;font-size:20px">مرحباً {name}،</h2>
<p style="color:#4a5568;margin:0 0 20px">تم استلام طلب الحجز الخاص بك بنجاح، وسيتم مراجعته من قِبل المختصين.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin-bottom:20px">
  {detail_rows}
</table>
<div style="background:linear-gradient(135deg,#EEF4FD,#E8F0FE);border-right:4px solid #0C67EC;border-radius:8px;padding:12px 16px;color:#4a5568;font-size:14px">
  ⏳ سيتم إعلامك بقرار الموافقة في أقرب وقت.
</div>"""
        subj = '📋 طلب حجز جديد — ARS'
        txt  = f"ARS — طلب حجز جديد\n\nمرحباً {name}،\nالرقم: {bn}\nالعنوان: {title}\n\nسيتم إعلامك قريباً."

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

    # Custom template override
    _subj, _body = _resolve_template('booking_approved', lang, {
        'name': name, 'booking_number': bn, 'title': title,
        'venue': venue, 'start_time': start})
    if _body:
        _send(res.user.email or '', name, _subj, _html_wrapper(_body, _subj, lang),
              '', sync=True, email_type='notification')
        return

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

    # ── إرسال للإيميلات الخارجية (cc_emails) ──────────────────────────────
    import re as _re
    notes_raw = getattr(res, 'requester_notes', '') or ''
    cc_match  = _re.search(r'\[cc_emails:([^\]]+)\]', notes_raw)
    if cc_match:
        cc_list = [e.strip() for e in cc_match.group(1).split(';') if e.strip()]
        cc_subj = f'✅ Booking Approved — {bn}' if lang == 'en' else f'✅ تمت الموافقة على الحجز — {bn}'
        cc_body = f"""
<div style="padding:16px;background:#f0f9f0;border-radius:10px;margin-bottom:16px;text-align:center">
  <div style="font-size:32px">✅</div>
  <h3 style="color:#1B5E20;margin:8px 0">{'Booking Approved' if lang=='en' else 'تمت الموافقة على الحجز'}</h3>
</div>
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #C8E6C9;border-radius:10px;overflow:hidden">
  {_info_row('📋 ' + ('Booking No.' if lang=='en' else 'رقم الحجز'), f'<strong style="color:#0C67EC">{bn}</strong>', '#F1F8E9')}
  {_info_row('📌 ' + ('Title' if lang=='en' else 'العنوان'), title, '#FAFFFE')}
  {_info_row('🏢 ' + ('Venue' if lang=='en' else 'القاعة'), venue, '#F1F8E9')}
  {_info_row('🕐 ' + ('Time' if lang=='en' else 'الوقت'), start, '#FAFFFE')}
</table>"""
        for cc_email in cc_list:
            try:
                _send(cc_email, cc_email, cc_subj, _html_wrapper(cc_body, cc_subj, lang),
                      f"Booking {bn} approved — {title} at {venue} on {start}",
                      sync=False, email_type='notification')
            except Exception:
                pass


def send_booking_rejected(res, reason=''):
    """Notify user their booking was rejected"""
    if not res.user: return
    lang  = _user_lang(res.user)
    name  = res.user.full_name or res.user.username
    bn    = res.booking_number
    title = res.title

    # Custom template override
    _subj, _body = _resolve_template('booking_rejected', lang, {
        'name': name, 'booking_number': bn, 'title': title,
        'reason': reason or '—'})
    if _body:
        _send(res.user.email or '', name, _subj, _html_wrapper(_body, _subj, lang),
              '', sync=True, email_type='notification')
        return

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

    # Custom template override
    _subj, _body = _resolve_template('booking_cancelled', lang, {
        'name': name, 'booking_number': bn, 'title': title})
    if _body:
        _send(res.user.email or '', name, _subj, _html_wrapper(_body, _subj, lang),
              '', sync=True, email_type='notification')
        return

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

    # Custom template override (invitation always sent in English)
    _subj, _body = _resolve_template('invitation', 'en', {
        'name': name, 'title': title, 'venue': venue,
        'start_time': start, 'message_body': message_body or ''})
    if _body:
        _send(contact.email or '', name, _subj, _html_wrapper(_body, _subj, 'en'),
              '', sync=True, email_type='notification')
        return

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

    # Custom template override
    _subj, _body = _resolve_template('welcome', lang, {
        'name': name, 'username': uname, 'password': password,
        'login_url': login_url or ''})
    if _body:
        _send(user.email or '', name, _subj, _html_wrapper(_body, _subj, lang),
              '', sync=True, email_type='notification')
        return

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
    # Custom template override
    _subj, _body = _resolve_template('reset_code', lang, {'code': code})
    if _body:
        return _send(email, '', _subj, _html_wrapper(_body, _subj, lang), '', sync=True)

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


def send_survey_invite_code(email: str, name: str, code: str, survey_name: str,
                              fill_url: str = '', lang: str = 'ar') -> bool:
    """Send an invited respondent their access code for a code-gated survey."""
    display_name = name or email
    link_html = f'<p style="text-align:center;margin:12px 0 0"><a href="{fill_url}" style="color:#7c3aed;font-weight:700;text-decoration:none">{fill_url}</a></p>' if fill_url else ''

    if lang == 'en':
        content = f"""
<p style="color:#4a5568;margin:0 0 20px">Hello {display_name}, you're invited to complete: <strong>{survey_name}</strong></p>
<div style="background:#f5f3ff;border:2px dashed #7c3aed;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:32px;font-weight:900;letter-spacing:6px;color:#6d28d9">{code}</div>
</div>
{link_html}
<p style="color:#999;font-size:12px;margin-top:16px">This code can only be used once. Please keep it private.</p>"""
        subj = f'Survey access code — {survey_name}'
        txt = f'Your access code for {survey_name}: {code}'
    else:
        content = f"""
<p style="color:#4a5568;margin:0 0 20px">مرحباً {display_name}، أنت مدعو لتعبئة: <strong>{survey_name}</strong></p>
<div style="background:#f5f3ff;border:2px dashed #7c3aed;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:32px;font-weight:900;letter-spacing:6px;color:#6d28d9">{code}</div>
</div>
{link_html}
<p style="color:#999;font-size:12px;margin-top:16px">هذا الرمز صالح للاستخدام مرة واحدة فقط. الرجاء المحافظة على سريته.</p>"""
        subj = f'رمز الدخول للاستبيان — {survey_name}'
        txt = f'رمز دخولك لاستبيان {survey_name}: {code}'

    return _send(email, display_name, subj, _html_wrapper(content, subj, lang), txt, sync=True)


def send_event_checkin_code(email: str, name: str, code: str, event_name: str, event_date: str,
                              window_start: str, window_end: str, checkin_url: str = '', lang: str = 'ar') -> bool:
    """Send an attendee their one-time check-in code for a meeting/event."""
    display_name = name or email
    link_html = f'<p style="text-align:center;margin:12px 0 0"><a href="{checkin_url}" style="color:#0891b2;font-weight:700;text-decoration:none">{checkin_url}</a></p>' if checkin_url else ''

    if lang == 'en':
        content = f"""
<p style="color:#4a5568;margin:0 0 20px">Hello {display_name}, you're invited to: <strong>{event_name}</strong></p>
<p style="color:#4a5568;margin:0 0 16px">Date: <strong>{event_date}</strong> — Time: <strong>{window_start}</strong></p>
<div style="background:#ecfeff;border:2px dashed #0891b2;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:32px;font-weight:900;letter-spacing:6px;color:#0e7490">{code}</div>
</div>
{link_html}
<p style="color:#999;font-size:12px;margin-top:16px">Please arrive on time — a short grace period requires stating a reason for lateness.</p>"""
        subj = f'Check-in code — {event_name}'
        txt  = f'Your check-in code for {event_name} ({event_date}, {window_start}): {code}'
    else:
        content = f"""
<p style="color:#4a5568;margin:0 0 20px">مرحباً {display_name}، أنت مدعو إلى: <strong>{event_name}</strong></p>
<p style="color:#4a5568;margin:0 0 16px">التاريخ: <strong>{event_date}</strong> — الساعة: <strong>{window_start}</strong></p>
<div style="background:#ecfeff;border:2px dashed #0891b2;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:32px;font-weight:900;letter-spacing:6px;color:#0e7490">{code}</div>
</div>
{link_html}
<p style="color:#999;font-size:12px;margin-top:16px">الرجاء الحضور بالوقت المحدد — التأخير عن الوقت يتطلب ذكر السبب.</p>"""
        subj = f'رمز تسجيل الحضور — {event_name}'
        txt  = f'رمز تسجيل حضورك لـ {event_name} ({event_date}, {window_start}): {code}'

    return _send(email, display_name, subj, _html_wrapper(content, subj, lang), txt, sync=True)


def send_staff_login_code(email: str, staff_name: str, code: str, portal_url: str = '', lang: str = 'ar') -> bool:
    """Send an SAS staff member their portal login code (manual send, triggered by admin)."""
    name = staff_name or email
    link_html = f'<p style="text-align:center;margin:12px 0 0"><a href="{portal_url}" style="color:#0891b2;font-weight:700;text-decoration:none">{portal_url}</a></p>' if portal_url else ''

    if lang == 'en':
        content = f"""
<p style="color:#4a5568;margin:0 0 20px">Hello {name}, here is your STAP portal login code:</p>
<div style="background:#ecfeff;border:2px dashed #0891b2;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:32px;font-weight:900;letter-spacing:6px;color:#0e7490">{code}</div>
</div>
{link_html}
<p style="color:#999;font-size:12px;margin-top:16px">Keep this code private — do not share it with anyone.</p>"""
        subj = 'STAP — Your Staff Login Code'
        txt  = f'Your STAP login code: {code}'
    else:
        content = f"""
<p style="color:#4a5568;margin:0 0 20px">مرحباً {name}، هذا رمز دخولك إلى بوابة النظام (STAP):</p>
<div style="background:#ecfeff;border:2px dashed #0891b2;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px">
  <div style="font-size:32px;font-weight:900;letter-spacing:6px;color:#0e7490">{code}</div>
</div>
{link_html}
<p style="color:#999;font-size:12px;margin-top:16px">حافظ على سرية هذا الرمز ولا تشاركه مع أحد.</p>"""
        subj = 'STAP — رمز دخول الموظف'
        txt  = f'رمز دخولك: {code}'

    return _send(email, name, subj, _html_wrapper(content, subj, lang), txt, sync=True)


def send_verification_code(email: str, code: str, full_name: str = '', lang: str = 'ar') -> bool:
    name = full_name or email
    # Custom template override
    _subj, _body = _resolve_template('verification_code', lang, {
        'name': name, 'code': code})
    if _body:
        return _send(email, name, _subj, _html_wrapper(_body, _subj, lang), '', sync=True)

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


def _build_reservation_details_rows(res, lang):
    """Build HTML table rows with full reservation details (notes + attachments)"""
    rows = []
    bn    = res.booking_number or '—'
    title = res.title or '—'
    venue = res.venue.name if res.venue else '—'
    loc   = res.venue.location.name if res.venue and res.venue.location else None
    start = res.start_time.strftime('%Y-%m-%d  %H:%M') if res.start_time else '—'
    end   = res.end_time.strftime('%Y-%m-%d  %H:%M') if res.end_time else '—'
    notes = res.requester_notes or ''

    if lang == 'en':
        rows.append(_info_row('📋 Booking No.', f'<strong style="color:#0C67EC">{bn}</strong>'))
        rows.append(_info_row('📌 Title', title, '#FAFCFF'))
        rows.append(_info_row('🏢 Venue', venue))
        if loc: rows.append(_info_row('📍 Location', loc, '#FAFCFF'))
        rows.append(_info_row('📅 Start', start))
        rows.append(_info_row('🏁 End', end, '#FAFCFF'))
        if notes: rows.append(_info_row('📝 Notes', notes))
    else:
        rows.append(_info_row('📋 رقم الحجز', f'<strong style="color:#0C67EC">{bn}</strong>'))
        rows.append(_info_row('📌 العنوان', title, '#FAFCFF'))
        rows.append(_info_row('🏢 القاعة', venue))
        if loc: rows.append(_info_row('📍 الموقع', loc, '#FAFCFF'))
        rows.append(_info_row('📅 البداية', start))
        rows.append(_info_row('🏁 الانتهاء', end, '#FAFCFF'))
        if notes: rows.append(_info_row('📝 ملاحظات', notes))

    # Attachments list
    try:
        atts = res.attachments if hasattr(res, 'attachments') else []
        if not atts:
            from models.database import Attachment, get_engine
            from sqlalchemy.orm import sessionmaker
            engine = get_engine()
            _s = sessionmaker(bind=engine)()
            atts = _s.query(Attachment).filter_by(reservation_id=res.id).all()
            _s.close()
        if atts:
            att_list = ', '.join(a.filename for a in atts)
            label = 'Attachments' if lang == 'en' else 'المرفقات'
            rows.append(_info_row(f'📎 {label}', att_list, '#FAFCFF'))
    except Exception:
        pass

    return ''.join(rows)


def send_employee_reservation_notice(employee, res, requester):
    """Notify employee they were assigned to a reservation — full details"""
    lang  = _user_lang(employee)
    name  = employee.full_name or employee.username
    req_name = requester.full_name or requester.username if requester else '—'
    bn    = res.booking_number

    detail_rows = _build_reservation_details_rows(res, lang)

    # Custom template override
    _subj, _body = _resolve_template('employee_reservation_notice', lang, {
        'name': name, 'requester_name': req_name, 'booking_number': bn,
        'title': res.title, 'venue': res.venue.name if res.venue else '—',
        'start_time': res.start_time.strftime('%Y-%m-%d  %H:%M') if res.start_time else '—'})
    if _body:
        _send(employee.email or '', name, _subj, _html_wrapper(_body, _subj, lang),
              '', sync=True, email_type='notification')
        return

    if lang == 'en':
        content = f"""
<h2 style="color:#0C67EC;margin:0 0 12px">Hello {name},</h2>
<p style="color:#4a5568">You have been assigned to the following reservation by <strong>{req_name}</strong>:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin:16px 0">
  {detail_rows}
</table>"""
        subj = f'📋 Reservation Assignment — {bn}'
        txt  = f"You were assigned to reservation {bn}: {res.title}"
    else:
        content = f"""
<h2 style="color:#0C67EC;margin:0 0 12px">مرحباً {name}،</h2>
<p style="color:#4a5568">تم تعيينك في الحجز التالي من قِبل <strong>{req_name}</strong>:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin:16px 0">
  {detail_rows}
</table>"""
        subj = f'📋 تعيين في حجز — {bn}'
        txt  = f"تم تعيينك في الحجز {bn}: {res.title}"

    _send(employee.email or '', name, subj, _html_wrapper(content, subj, lang), txt, sync=True, email_type='notification')


def send_employee_reservation_notice_to_email(to_email, to_name, res, requester):
    """Notify any external email address about a reservation assignment — full details"""
    # Use Arabic by default for external recipients (fallback)
    lang     = 'ar'
    name     = to_name or to_email
    req_name = requester.full_name or requester.username if requester else '—'
    bn       = res.booking_number

    detail_rows = _build_reservation_details_rows(res, lang)

    content = f"""
<h2 style="color:#0C67EC;margin:0 0 12px">مرحباً {name}،</h2>
<p style="color:#4a5568">تم تعيينك في الحجز التالي من قِبل <strong>{req_name}</strong>:</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px;overflow:hidden;border:1px solid #E0E8F5;margin:16px 0">
  {detail_rows}
</table>
<div style="background:#f4f9ff;border-right:4px solid #0C67EC;border-radius:8px;padding:12px 16px;color:#4a5568;font-size:13px;margin-top:8px">
  📌 للمزيد من التفاصيل أو الاستفسارات، تواصل مع مقدم الطلب.
</div>"""
    subj = f'📋 تعيين في حجز — {bn}'
    txt  = f"تم تعيينك في الحجز {bn}: {res.title}"

    _send(to_email, name, subj, _html_wrapper(content, subj, lang), txt, sync=True, email_type='notification')


def test_smtp(smtp_host='', smtp_port=587, sender_email='', sender_password='',
              use_tls=True, brevo_api_key=None, to_email=None, lang='ar') -> tuple:
    """Test email — tries provided credentials, falls back to saved config.
    Uses real SMTP for Gmail/Office 365/Outlook/Yahoo/Brevo-SMTP/custom, and
    the Brevo HTTP API only when the Brevo API provider was selected
    (brevo_api_key is passed as None, not '', when a different provider is
    selected — the caller in routes/admin.py encodes that distinction)."""
    import json, urllib.request
    en = lang == 'en'
    use_smtp = brevo_api_key is None
    api_key = (brevo_api_key or '').strip()
    from_email = (sender_email or '').strip()
    host = (smtp_host or '').strip()

    if not from_email:
        cfg = _get_cfg()
        from_email = cfg.get('sender_email', '')
    if use_smtp and not host:
        cfg = _get_cfg()
        host = cfg.get('smtp_server', '')
    if not use_smtp and not api_key:
        cfg = _get_cfg()
        api_key = cfg.get('api_key') or cfg.get('brevo_api_key', '')

    test_to = (to_email or from_email or '').strip()

    if not from_email:
        return (False, 'Sender Email is missing — enter the sender email and save settings' if en else 'Sender Email مفقود — أدخل بريد المُرسِل واحفظ الإعدادات')
    if not test_to:
        return (False, 'No recipient email address' if en else 'لا يوجد بريد للاستلام')

    test_html = _html_wrapper(
        '<p style="color:#4a5568;text-align:center;font-size:16px">'
        '✅ Email configuration is working correctly!</p>' if en else
        '<p style="color:#4a5568;text-align:center;font-size:16px">'
        '✅ إعدادات البريد الإلكتروني تعمل بشكل صحيح!</p>',
        'Test', lang)
    test_text = 'ARS email test successful!' if en else 'ARS email test — تم الإرسال بنجاح!'

    # Real SMTP path — Gmail / Office 365 / Outlook / Yahoo / Brevo SMTP / custom
    if use_smtp:
        if not host:
            return (False, 'SMTP server address is missing' if en else 'عنوان خادم SMTP مفقود')
        try:
            _send_via_smtp(host, smtp_port, from_email, sender_password, use_tls,
                            'ARS Test', test_to, 'ARS Test', 'ARS — Email Test ✅', test_html, test_text)
            return (True, f'Test email sent successfully to: {test_to}' if en else f'تم إرسال بريد اختباري بنجاح إلى: {test_to}')
        except Exception as e:
            return (False, f'SMTP error: {e}' if en else f'خطأ SMTP: {e}')

    # Brevo HTTP API path
    try:
        if not api_key:
            return (False, 'API Key is missing — enter your Brevo API Key and save settings first' if en else 'API Key مفقود — أدخل Brevo API Key واحفظ الإعدادات أولاً')

        payload = json.dumps({
            'sender':      {'name': 'ARS Test', 'email': from_email},
            'to':          [{'email': test_to, 'name': 'ARS Test'}],
            'subject':     'ARS — Email Test ✅',
            'htmlContent': test_html,
            'textContent': test_text,
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
