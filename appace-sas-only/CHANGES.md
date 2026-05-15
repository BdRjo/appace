# سجل التعديلات — ARS Stable_v20
**تاريخ التعديلات:** 2026-03-18

---

## 1. حقل `job_title` و `department` للمستخدمين

### الملفات المعدّلة:
- `models/database.py` — إضافة العمودين للنموذج + auto-migration
- `routes/users.py` — new / edit / import / export / index (filter)
- `templates/admin/user_form.html` — حقلا الإدخال في النموذج
- `templates/admin/users_mgmt.html` — عمودا الجدول + فلتر الدائرة

### التفاصيل:
- تمت إضافة `job_title VARCHAR(200)` و `department VARCHAR(200)` لجدول `users`
- نموذج إضافة/تعديل المستخدم يشمل الحقلين
- جدول المستخدمين يعرض عمودَي الدائرة والمسمى الوظيفي
- قائمة منسدلة للفلترة حسب الدائرة (تُعبّأ من البيانات الموجودة)
- البحث النصي يشمل الدائرة والمسمى الوظيفي
- استيراد CSV يقرأ الحقلين الجديدين
- تصدير Excel/CSV يشمل الحقلين

---

## 2. حقل `department` لجهات الاتصال

### الملفات المعدّلة:
- `models/database.py` — إضافة العمود للنموذج + auto-migration
- `routes/contacts.py` — new / edit / import / export / csv_template
- `templates/contacts/form.html` — حقل الإدخال في النموذج
- `templates/contacts/index.html` — عمود الدائرة في الجدول

### التفاصيل:
- تمت إضافة `department VARCHAR(200)` لجدول `contacts`
- نموذج إضافة/تعديل جهة الاتصال يشمل الدائرة
- جدول جهات الاتصال يعرض عمود الدائرة
- قالب CSV وعملية الاستيراد والتصدير تشمل الدائرة

---

## 3. إصلاح اتجاه محرر الرسالة الجماعية (RTL/LTR)

### الملفات المعدّلة:
- `templates/admin/bulk_message.html`

### التفاصيل:
- CSS للمحرر `#editor { direction: ... }` يتغير ديناميكياً بحسب `current_lang`
- `quill.format('direction', EDITOR_DIR)` يستخدم قيمة ديناميكية
- محاذاة النص تتغير تلقائياً (يمين للعربية / يسار للإنجليزية)
- نافذة المعاينة (Modal) كذلك تتكيف مع اتجاه اللغة

---

## 4. تقرير لوحة التحكم PDF ثنائي اللغة + إصلاح الألوان

### الملفات المعدّلة:
- `routes/admin.py` — دالة `dashboard_pdf()`

### التفاصيل:
- يكتشف لغة المستخدم من الجلسة ويُصدر التقرير بالعربية أو الإنجليزية
- دالة مساعدة `_t(ar_text, en_text)` لترجمة جميع التسميات
- **إصلاح الألوان:** خانات التسميات: نص أبيض على خلفية زرقاء داكنة `#1565C0`
- خانات القيم: أرقام كبيرة على خلفية زرقاء فاتحة `#E3F2FD` — سهلة القراءة
- اسم الملف المُصدَّر يتضمن اللغة: `dashboard_20260318_1530_ar.pdf`

---

## 5. المخطط الثالث في لوحة التحكم (مخطط XY)

### الملفات المعدّلة:
- `routes/admin.py` — دالة `dashboard()` (استعلام `top_users_xy`)
- `templates/admin/dashboard.html` — HTML + JavaScript للمخطط

### التفاصيل:
- مخطط "أنشط المستخدمين": يقارن إجمالي الحجوزات مقابل الموافقات لأعلى 8 مستخدمين
- نوع مختلط: أعمدة (الإجمالي) + خط (الموافقات)
- Tooltip يُظهر نسبة الموافقة % عند التمرير
- رابط مباشر للمقارنة التفصيلية في صفحة التقارير

---

## 6. تحسين نظام المقارنة التحليلية للمستخدمين

### الملفات المعدّلة:
- `routes/reports.py` — دالة `_user_stats()`

### التفاصيل:
- إضافة **نسبة الموافقة %** محسوبة تلقائياً
- إضافة **القاعة الأكثر استخداماً** لكل مستخدم
- إضافة **الدائرة** و **المسمى الوظيفي** إذا كانا موجودَين
- يعمل في وضع مقارنة متعددة (حتى 5 مستخدمين في آنٍ واحد)

---

## ملخص الملفات المعدّلة

| الملف | التعديل |
|-------|---------|
| `models/database.py` | حقول جديدة + auto-migration |
| `routes/admin.py` | PDF ثنائي اللغة + مخطط XY |
| `routes/users.py` | job_title, department في كل العمليات |
| `routes/contacts.py` | department في كل العمليات |
| `routes/reports.py` | _user_stats() محسّنة |
| `templates/admin/user_form.html` | حقلا القسم والمسمى |
| `templates/admin/users_mgmt.html` | فلتر + أعمدة جديدة |
| `templates/admin/bulk_message.html` | RTL/LTR ديناميكي |
| `templates/admin/dashboard.html` | مخطط XY ثالث |
| `templates/contacts/form.html` | حقل الدائرة |
| `templates/contacts/index.html` | عمود الدائرة |
