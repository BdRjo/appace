#!/bin/bash
# ============================================================
# ARS White Label — سكريبت إنشاء نسخة جديدة لعميل جديد
# الاستخدام: bash new_client.sh
# ============================================================

echo "🚀 ARS White Label — نسخة عميل جديد"
echo "======================================"

read -p "اسم العميل (بالإنجليزية، بدون مسافات): " CLIENT_ID
read -p "اسم النظام بالعربي: " BRAND_NAME_AR
read -p "اسم النظام بالإنجليزي: " BRAND_NAME_EN
read -p "الوصف بالعربي: " TAGLINE_AR
read -p "الوصف بالإنجليزي: " TAGLINE_EN
read -p "اللون الرئيسي (مثال #0C67EC): " PRIMARY_COLOR
read -p "رابط شعار العميل (URL أو اضغط Enter للتخطي): " LOGO_URL

# إنشاء branch جديد
git checkout main
git checkout -b "client-${CLIENT_ID}"

# إنشاء ملف brand config للعميل
cat > maintenance_config.json << EOF
{
  "brand_name":       "${BRAND_NAME_AR}",
  "brand_name_en":    "${BRAND_NAME_EN}",
  "brand_tagline":    "${TAGLINE_AR}",
  "brand_tagline_en": "${TAGLINE_EN}",
  "brand_short":      "${CLIENT_ID}",
  "brand_short_en":   "${CLIENT_ID}",
  "color_primary":    "${PRIMARY_COLOR:-#0C67EC}",
  "color_primary_dark":  "$(python3 -c "c='${PRIMARY_COLOR:-0C67EC}'.replace('#',''); r,g,b=int(c[0:2],16),int(c[2:4],16),int(c[4:6],16); print(f'#{max(0,r-30):02X}{max(0,g-30):02X}{max(0,b-30):02X}')" 2>/dev/null || echo '#0847B0')",
  "color_primary_light": "${PRIMARY_COLOR:-#3D8EF5}",
  "report_header_title":    "${BRAND_NAME_AR}",
  "report_header_subtitle": "${TAGLINE_AR}",
  "report_header_footer":   "${BRAND_NAME_AR} — جميع الحقوق محفوظة"
}
EOF

echo ""
echo "✅ تم إنشاء Branch: client-${CLIENT_ID}"
echo "✅ تم إنشاء maintenance_config.json"
echo ""
echo "الخطوات التالية:"
echo "1. git add maintenance_config.json"
echo "2. git commit -m 'brand: ${CLIENT_ID} configuration'"
echo "3. git push origin client-${CLIENT_ID}"
echo "4. في Render: أنشئ Web Service جديد من هذا الـ branch"
echo "5. في Render: أنشئ PostgreSQL جديد"
echo "6. أضف DATABASE_URL في Environment Variables"
echo ""
echo "رابط الموقع سيكون: https://${CLIENT_ID}.onrender.com"
