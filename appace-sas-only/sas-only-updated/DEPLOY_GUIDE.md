# دليل نشر ARS على الإنترنت — خطوة بخطوة

## الطريقة المجانية المضمونة: Oracle Cloud + GitHub + Render

---

## الجزء الأول: تجهيز الكود على GitHub (5 دقائق)

### 1. أنشئ حساب GitHub
- اذهب إلى https://github.com واضغط **Sign up**
- اختر اسم مستخدم وكلمة مرور وأكد بريدك

### 2. أنشئ مستودع جديد
- اضغط **New repository**
- الاسم: `ars-reservation-system`
- اختر **Private** (سري — لا أحد يراه)
- اضغط **Create repository**

### 3. ارفع ملفات الويب
افتح CMD أو Terminal في مجلد `ARS_web` ونفّذ:

```bash
git init
git add .
git commit -m "ARS Web App v1"
git branch -M main
git remote add origin https://github.com/اسمك/ars-reservation-system.git
git push -u origin main
```

---

## الجزء الثاني: النشر على Render.com (10 دقائق)

### 1. أنشئ حساب Render
- اذهب إلى https://render.com
- اضغط **Sign up with GitHub** (يربطه بحسابك تلقائياً)

### 2. أنشئ قاعدة بيانات PostgreSQL (مجاناً)
- اضغط **New** → **PostgreSQL**
- الاسم: `ars-db`
- Plan: **Free**
- اضغط **Create Database**
- انتظر دقيقة حتى تنشأ
- **انسخ** الـ `Internal Database URL` — ستحتاجه لاحقاً

### 3. أنشئ Web Service
- اضغط **New** → **Web Service**
- اختر مستودع `ars-reservation-system`
- الإعدادات:
  ```
  Name:          ars-reservation-system
  Runtime:       Python 3
  Build Command: pip install -r requirements.txt
  Start Command: gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 4
  Plan:          Free
  ```

### 4. أضف متغيرات البيئة
في قسم **Environment Variables** أضف:

| Key | Value |
|-----|-------|
| `DATABASE_URL` | (الصق الـ Internal Database URL من الخطوة 2) |
| `SECRET_KEY` | اكتب أي نص عشوائي طويل مثل: `abc123xyz!@#2026ars` |
| `FLASK_ENV` | `production` |

### 5. اضغط Create Web Service
- انتظر 3-5 دقائق حتى ينتهي البناء
- ستحصل على رابط مثل: `https://ars-reservation-system.onrender.com`
- **افتح الرابط** — النظام شغّال! 🎉

---

## الجزء الثالث: ربط التطبيق المكتبي بنفس قاعدة البيانات

### الخيار أ: كل شيء على الويب (الأبسط)
- المستخدمون يدخلون عبر المتصفح
- المدراء يدخلون عبر التطبيق المكتبي على جهازهم
- قاعدة البيانات على Render (PostgreSQL)

لربط التطبيق المكتبي بـ PostgreSQL على Render:
1. احفظ الـ `External Database URL` من Render
2. أنشئ ملف `db_config.json` بجانب التطبيق المكتبي:
```json
{
  "database_url": "postgresql://user:pass@host/dbname"
}
```

### الخيار ب: الشبكة الداخلية (للمؤسسات)
- التطبيق المكتبي على سيرفر داخلي
- الويب يتصل بنفس قاعدة البيانات الداخلية
- يحتاج إعداد PostgreSQL على السيرفر الداخلي

---

## الجزء الرابع: تحديثات مستقبلية

عند أي تعديل في الكود:
```bash
git add .
git commit -m "وصف التعديل"
git push
```
Render يعيد النشر تلقائياً خلال 2-3 دقائق ✅

---

## الجزء الخامس: Oracle Cloud (للمستوى المتقدم — 24/7 بدون نوم)

إذا أردت سيرفراً دائماً بدون قيود Render:

### 1. أنشئ حساب Oracle Cloud
- https://cloud.oracle.com → **Start for free**
- يحتاج بطاقة ائتمان للتحقق (لا يُحسب عليك شيء)
- اختر منطقة: **Germany Central (Frankfurt)** أو **UAE East**

### 2. أنشئ VM مجانية
- Compute → Instances → **Create Instance**
- Image: **Ubuntu 22.04**
- Shape: **VM.Standard.A1.Flex** (ARM — هذا المجاني الدائم)
  - OCPUs: 4
  - Memory: 24 GB
- أضف SSH key (أو أنشئ واحدة)

### 3. بعد إنشاء VM، اتصل بها
```bash
ssh ubuntu@IP_ADDRESS
```

### 4. نفّذ سكريبت التثبيت التلقائي
```bash
curl -s https://raw.githubusercontent.com/اسمك/ars-reservation-system/main/install.sh | bash
```

أو يدوياً:
```bash
# تحديث النظام
sudo apt update && sudo apt upgrade -y

# تثبيت Python و PostgreSQL و Nginx
sudo apt install -y python3-pip python3-venv postgresql nginx git

# إعداد قاعدة البيانات
sudo -u postgres psql -c "CREATE USER ars_user WITH PASSWORD 'كلمة_سر_قوية';"
sudo -u postgres psql -c "CREATE DATABASE ars_venues OWNER ars_user;"

# نسخ الكود
git clone https://github.com/اسمك/ars-reservation-system.git /opt/ars
cd /opt/ars

# البيئة الافتراضية
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# إعداد المتغيرات
echo "DATABASE_URL=postgresql://ars_user:كلمة_سر_قوية@localhost/ars_venues" > .env
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
echo "FLASK_ENV=production" >> .env

# تشغيل تلقائي عند إعادة التشغيل
sudo tee /etc/systemd/system/ars.service << 'EOF'
[Unit]
Description=ARS Web Application
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/ars
EnvironmentFile=/opt/ars/.env
ExecStart=/opt/ars/venv/bin/gunicorn "app:create_app()" --bind 127.0.0.1:5000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable ars
sudo systemctl start ars

# Nginx كـ Reverse Proxy + HTTPS مجاني
sudo apt install -y certbot python3-certbot-nginx
```

---

## ملاحظات مهمة

⚠️ **تغيير كلمة المرور الافتراضية**: بعد أول تشغيل على الإنترنت، غيّر كلمة admin فوراً

⚠️ **لا ترفع ملف .env على GitHub**: مضاف لـ .gitignore تلقائياً

✅ **النسخ الاحتياطي**: Render يحتفظ بنسخ قاعدة البيانات تلقائياً (Free plan: 7 أيام)

✅ **HTTPS**: مفعّل تلقائياً على Render بدون أي إعداد

---

## روابط مفيدة
- Render Dashboard: https://dashboard.render.com
- GitHub: https://github.com
- Oracle Cloud: https://cloud.oracle.com
- مجتمع الدعم: https://community.render.com
