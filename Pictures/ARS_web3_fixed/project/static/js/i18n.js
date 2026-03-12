/**
 * ARS — Complete Bilingual Translation System (mirrors v54 Translator exactly)
 */
const ARS_TRANS = {
  ar: {
    'nav_home':'الرئيسية','nav_dashboard':'لوحة التحكم','nav_calendar':'التقويم',
    'nav_reservations':'الحجوزات','nav_new_res':'حجز جديد','nav_venues':'القاعات',
    'nav_extras':'إضافيات','nav_checklists':'قوائم المهام','nav_contacts':'جهات الاتصال',
    'nav_admin':'الإدارة','nav_locations':'المواقع','nav_venues_mgmt':'إدارة القاعات',
    'nav_users':'المستخدمون','nav_reports':'التقارير','nav_maintenance':'الصيانة',
    'nav_email_cfg':'إعدادات البريد','nav_comparison':'المقارنة','nav_bulk_msg':'رسالة جماعية',
    'nav_account':'الحساب','nav_profile':'ملفي الشخصي','nav_logout':'تسجيل الخروج',
    'nav_news':'أخبار','app_name':'ARS — نظام إدارة الحجوزات','brand_sub':'نظام إدارة الحجوزات',
    'dashboard':'لوحة التحكم','total_reservations':'إجمالي الحجوزات','pending':'معلقة',
    'approved':'موافق عليها','this_month':'هذا الشهر','users_count':'المستخدمون',
    'venues_count':'القاعات','rejected':'مرفوضة','locations_count':'المواقع',
    'monthly_chart':'الحجوزات — آخر 12 شهر','status_dist':'توزيع الحالات',
    'pending_list':'الحجوزات المعلقة','view_all':'عرض الكل','no_pending':'لا توجد حجوزات معلقة ✅',
    'quick_links':'روابط سريعة','new_location':'موقع جديد','new_venue':'قاعة جديدة',
    'new_user':'مستخدم جديد','new_checklist':'قائمة مهام','view_reports':'التقارير',
    'view_calendar':'التقويم','security_log':'سجل الدخول','settings':'الإعدادات',
    'new_reservation':'حجز جديد','manage_venues':'إدارة القاعات',
    'reservations':'الحجوزات','my_reservations':'حجوزاتي','all_reservations':'جميع الحجوزات',
    'other_reservations':'حجوزات أخرى','booking_number':'الرقم المرجعي','title':'العنوان',
    'venue':'القاعة','location':'الموقع','start_time':'البداية','end_time':'النهاية',
    'type':'النوع','status':'الحالة','actions':'إجراءات','approve':'موافقة','reject':'رفض',
    'cancel_booking':'إلغاء','reactivate':'إعادة تفعيل ♻️','edit_res':'تعديل',
    'process_res':'معالجة','invite':'دعوة','export_csv':'تصدير CSV',
    'export_pdf':'تصدير PDF','export_excel':'تصدير Excel','print':'طباعة',
    'filter_status':'تصفية بالحالة','filter_venue':'تصفية بالقاعة','all':'الكل','search':'بحث',
    'status_pending':'معلق','status_approved':'موافق عليه','status_rejected':'مرفوض',
    'status_cancelled':'ملغي','status_completed':'مكتمل',
    'type_personal':'شخصي','type_official':'مؤسسي','type_external':'خارجي',
    'calendar':'التقويم التفاعلي','filter_all':'🗓 عرض الكل','filter_mine':'👤 حجوزاتي',
    'filter_approved_cal':'✅ المعتمدة','filter_pending_cal':'⏳ المعلقة',
    'filter_rejected_cal':'❌ المرفوضة','filter_blocked':'🚫 المحجوبة',
    'all_venues':'كل القاعات','day_details':'تفاصيل اليوم',
    'add_res_day':'إضافة حجز لهذا اليوم','close':'إغلاق',
    'no_bookings_day':'لا توجد حجوزات في هذا اليوم ✅',
    'color_avail':'متاح/موافق','color_mine':'حجوزاتي','color_other':'حجوزات أخرى',
    'color_blocked':'محجوب','color_partial':'جزئي/معلق',
    'venues':'القاعات','venue_name':'الاسم','venue_code':'الكود','venue_location':'الموقع',
    'capacity':'السعة','needs_approval':'يحتاج موافقة','active':'نشط','inactive':'معطل',
    'add_venue':'إضافة قاعة','edit_venue':'تعديل قاعة','delete_venue':'حذف القاعة',
    'import_csv':'استيراد CSV','toggle_status':'تفعيل/تعطيل',
    'locations':'المواقع','location_name_ar':'الاسم بالعربية','location_name_en':'الاسم بالإنجليزية',
    'city':'المدينة','area':'المنطقة','add_location':'إضافة موقع',
    'edit_location':'تعديل موقع','delete_location':'حذف موقع',
    'users':'المستخدمون','full_name':'الاسم الكامل','username':'اسم المستخدم',
    'email':'البريد الإلكتروني','role':'الدور','last_login':'آخر تسجيل دخول',
    'login_count':'عدد مرات الدخول','add_user':'إضافة مستخدم','edit_user':'تعديل مستخدم',
    'change_password':'تغيير كلمة المرور','disable_user':'تعطيل/تفعيل','delete_user':'حذف',
    'send_message':'إرسال رسالة','bulk_message':'رسالة جماعية','import_users':'استيراد CSV',
    'reports':'التقارير','report_type':'نوع التقرير:','report_my_res':'حجوزاتي',
    'report_all_res':'جميع الحجوزات','report_venues':'القاعات','report_locations':'المواقع',
    'report_users':'المستخدمون','filter_label':'الفلتر:','filter_today':'اليوم',
    'filter_week':'الأسبوع','filter_month':'الشهر','filter_custom':'مخصص',
    'from_date':'من:','to_date':'إلى:','apply':'تطبيق','comparison':'المقارنة',
    'maintenance':'الصيانة','db_operations':'🔧 عمليات قاعدة البيانات',
    'backup':'💾 نسخ احتياطي','clean_logs':'🧹 تنظيف السجلات القديمة',
    'optimize_db':'⚡ تحسين قاعدة البيانات','email_settings':'📧 إعداد البريد الإلكتروني',
    'system_log':'🛡️ سجل النظام والأمان','sys_settings':'⚙️ إعدادات النظام',
    'suspend_system':'تعليق النظام','activate_system':'تفعيل النظام',
    'suspend_reg':'تعليق التسجيل','activate_reg':'تفعيل التسجيل',
    'ticker_mgmt':'📢 إدارة شريط الأخبار (Ticker)',
    'ticker_ar_tab':'🇸🇦 عربي','ticker_en_tab':'🇬🇧 English',
    'add':'إضافة','appearance':'🎨 المظهر','font':'الخط','font_size':'حجم الخط',
    'text_color':'لون النص','bg_color':'لون الخلفية','bg_opacity':'شفافية الخلفية %',
    'speed':'السرعة','live_preview':'معاينة حية','save_apply':'💾 حفظ وتطبيق',
    'login':'تسجيل الدخول','register':'إنشاء حساب','logout':'تسجيل الخروج',
    'forgot_password':'نسيت كلمة المرور؟','reset_password':'إعادة تعيين كلمة المرور',
    'password':'كلمة المرور','confirm_password':'تأكيد كلمة المرور','remember_me':'تذكرني',
    'profile':'الملف الشخصي','phone':'رقم الهاتف','save_changes':'حفظ التغييرات',
    'current_password':'كلمة المرور الحالية','new_password':'كلمة المرور الجديدة',
    'save':'حفظ','cancel':'إلغاء','delete':'حذف','edit':'تعديل','add_btn':'إضافة',
    'refresh':'تحديث','yes':'نعم','no':'لا','no_data':'لا توجد بيانات',
    'loading':'جاري التحميل...','error':'خطأ','success':'نجاح','warning':'تحذير',
    'confirm_delete':'هل أنت متأكد من الحذف؟',
    'block_period':'حظر فترة','blocked_periods':'الفترات المحظورة',
    'block_reason':'سبب الحظر','block_start':'بداية الفترة','block_end':'نهاية الفترة',
    'checklists':'قوائم المهام','checklist_name':'اسم القائمة',
    'contacts':'جهات الاتصال','first_name':'الاسم الأول','last_name':'الاسم الأخير',
    'send_invite':'إرسال دعوة بريدية',
    'ratings':'التقييمات','stars':'النجوم','comment':'التعليق',
    'quick_actions':'الإجراءات السريعة',
  },
  en: {
    'nav_home':'Main','nav_dashboard':'Dashboard','nav_calendar':'Calendar',
    'nav_reservations':'Reservations','nav_new_res':'New Reservation','nav_venues':'Venues',
    'nav_extras':'Extras','nav_checklists':'Checklists','nav_contacts':'Contacts',
    'nav_admin':'Administration','nav_locations':'Locations','nav_venues_mgmt':'Manage Venues',
    'nav_users':'Users','nav_reports':'Reports','nav_maintenance':'Maintenance',
    'nav_email_cfg':'Email Settings','nav_comparison':'Compare & Analyze','nav_bulk_msg':'Bulk Message',
    'nav_account':'Account','nav_profile':'My Profile','nav_logout':'Sign Out',
    'nav_news':'News','app_name':'ARS — Applied Reservation System','brand_sub':'Applied Reservation System',
    'dashboard':'Dashboard','total_reservations':'Total Reservations','pending':'Pending',
    'approved':'Approved','this_month':'This Month','users_count':'Users',
    'venues_count':'Venues','rejected':'Rejected','locations_count':'Locations',
    'monthly_chart':'Reservations — Last 12 Months','status_dist':'Status Distribution',
    'pending_list':'Pending Reservations','view_all':'View All','no_pending':'No pending reservations ✅',
    'quick_links':'Quick Links','new_location':'New Location','new_venue':'New Venue',
    'new_user':'New User','new_checklist':'New Checklist','view_reports':'Reports',
    'view_calendar':'Calendar','security_log':'Login Log','settings':'Settings',
    'new_reservation':'New Reservation','manage_venues':'Manage Venues',
    'reservations':'Reservations','my_reservations':'My Reservations','all_reservations':'All Reservations',
    'other_reservations':'Others\' Reservations','booking_number':'Ref. No.','title':'Title',
    'venue':'Venue','location':'Location','start_time':'Start','end_time':'End',
    'type':'Type','status':'Status','actions':'Actions','approve':'Approve','reject':'Reject',
    'cancel_booking':'Cancel','reactivate':'Reactivate ♻️','edit_res':'Edit',
    'process_res':'Process','invite':'Invite','export_csv':'Export CSV',
    'export_pdf':'Export PDF','export_excel':'Export Excel','print':'Print',
    'filter_status':'Filter by Status','filter_venue':'Filter by Venue','all':'All','search':'Search',
    'status_pending':'Pending','status_approved':'Approved','status_rejected':'Rejected',
    'status_cancelled':'Cancelled','status_completed':'Completed',
    'type_personal':'Personal','type_official':'Official','type_external':'External',
    'calendar':'Interactive Calendar','filter_all':'🗓 Show All','filter_mine':'👤 Mine Only',
    'filter_approved_cal':'✅ Approved','filter_pending_cal':'⏳ Pending',
    'filter_rejected_cal':'❌ Rejected','filter_blocked':'🚫 Blocked',
    'all_venues':'All Venues','day_details':'Day Details',
    'add_res_day':'Add Reservation for this Day','close':'Close',
    'no_bookings_day':'No reservations on this day ✅',
    'color_avail':'Available/Approved','color_mine':'My Bookings','color_other':'Others\' Bookings',
    'color_blocked':'Blocked','color_partial':'Partial/Pending',
    'venues':'Venues','venue_name':'Name','venue_code':'Code','venue_location':'Location',
    'capacity':'Capacity','needs_approval':'Needs Approval','active':'Active','inactive':'Inactive',
    'add_venue':'Add Venue','edit_venue':'Edit Venue','delete_venue':'Delete Venue',
    'import_csv':'Import CSV','toggle_status':'Enable/Disable',
    'locations':'Locations','location_name_ar':'Name (Arabic)','location_name_en':'Name (English)',
    'city':'City','area':'Area','add_location':'Add Location',
    'edit_location':'Edit Location','delete_location':'Delete Location',
    'users':'Users','full_name':'Full Name','username':'Username',
    'email':'Email','role':'Role','last_login':'Last Login',
    'login_count':'Login Count','add_user':'Add User','edit_user':'Edit User',
    'change_password':'Change Password','disable_user':'Enable/Disable','delete_user':'Delete',
    'send_message':'Send Message','bulk_message':'Bulk Message','import_users':'Import CSV',
    'reports':'Reports','report_type':'Report Type:','report_my_res':'My Reservations',
    'report_all_res':'All Reservations','report_venues':'Venues','report_locations':'Locations',
    'report_users':'Users','filter_label':'Filter:','filter_today':'Today',
    'filter_week':'Week','filter_month':'Month','filter_custom':'Custom',
    'from_date':'From:','to_date':'To:','apply':'Apply','comparison':'Comparison',
    'maintenance':'Maintenance','db_operations':'🔧 Database Operations',
    'backup':'💾 Backup Database','clean_logs':'🧹 Clean Old Logs',
    'optimize_db':'⚡ Optimize Database','email_settings':'📧 Email Settings',
    'system_log':'🛡️ System & Security Log','sys_settings':'⚙️ System Settings',
    'suspend_system':'Suspend System','activate_system':'Activate System',
    'suspend_reg':'Suspend Registration','activate_reg':'Activate Registration',
    'ticker_mgmt':'📢 News Ticker Management',
    'ticker_ar_tab':'🇸🇦 Arabic','ticker_en_tab':'🇬🇧 English',
    'add':'Add','appearance':'🎨 Appearance','font':'Font','font_size':'Font Size',
    'text_color':'Text Color','bg_color':'Background Color','bg_opacity':'BG Opacity %',
    'speed':'Speed','live_preview':'Live Preview','save_apply':'💾 Save & Apply',
    'login':'Sign In','register':'Create Account','logout':'Sign Out',
    'forgot_password':'Forgot password?','reset_password':'Reset Password',
    'password':'Password','confirm_password':'Confirm Password','remember_me':'Remember me',
    'profile':'My Profile','phone':'Phone','save_changes':'Save Changes',
    'current_password':'Current Password','new_password':'New Password',
    'save':'Save','cancel':'Cancel','delete':'Delete','edit':'Edit','add_btn':'Add',
    'refresh':'Refresh','yes':'Yes','no':'No','no_data':'No data available',
    'loading':'Loading...','error':'Error','success':'Success','warning':'Warning',
    'confirm_delete':'Are you sure you want to delete?',
    'block_period':'Block Period','blocked_periods':'Blocked Periods',
    'block_reason':'Block Reason','block_start':'Period Start','block_end':'Period End',
    'checklists':'Checklists','checklist_name':'Checklist Name',
    'contacts':'Contacts','first_name':'First Name','last_name':'Last Name',
    'send_invite':'Send Email Invitation',
    'ratings':'Ratings','stars':'Stars','comment':'Comment',
    'quick_actions':'Quick Actions',
  }
};

let ARS_LANG = localStorage.getItem('ars_lang') || 'ar';

function arsT(key) {
  return (ARS_TRANS[ARS_LANG] || ARS_TRANS['ar'])[key] || key;
}

function arsTranslateAll(lang) {
  const dict = ARS_TRANS[lang] || ARS_TRANS['ar'];
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key] !== undefined) el.textContent = dict[key];
  });
  document.querySelectorAll('[data-i18n-html]').forEach(el => {
    const key = el.getAttribute('data-i18n-html');
    if (dict[key] !== undefined) el.innerHTML = dict[key];
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    const key = el.getAttribute('data-i18n-ph');
    if (dict[key] !== undefined) el.setAttribute('placeholder', dict[key]);
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.getAttribute('data-i18n-title');
    if (dict[key] !== undefined) el.setAttribute('title', dict[key]);
  });
}

function loadTicker(lang) {
  const tickerText  = document.getElementById('tickerText');
  const tickerTrack = document.getElementById('tickerTrack');
  const tickerWrap  = document.getElementById('tickerWrap');
  if (!tickerText || !tickerTrack) return;
  fetch('/admin/api/ticker?lang=' + (lang || ARS_LANG))
    .then(r => r.json())
    .then(data => {
      tickerText.textContent = data.text || tickerText.textContent;
      // Apply appearance from ticker_config
      if (data.fg)   tickerText.style.color      = data.fg;
      if (data.font) tickerText.style.fontFamily  = data.font;
      if (data.size) tickerText.style.fontSize    = data.size + 'px';
      if (data.speed)tickerTrack.style.animationDuration = data.speed + 's';
      else {
        const len = tickerText.textContent.length;
        tickerTrack.style.animationDuration = Math.max(20, len * 0.22) + 's';
      }
      if (tickerWrap && data.bg) {
        // Apply bg with opacity
        const hex = data.bg.replace('#','');
        const r = parseInt(hex.slice(0,2),16);
        const g = parseInt(hex.slice(2,4),16);
        const b = parseInt(hex.slice(4,6),16);
        const a = (data.opacity || 100) / 100;
        tickerWrap.style.background = `rgba(${r},${g},${b},${a})`;
      }
    }).catch(() => {});
}

function toggleLang() {
  const newLang = ARS_LANG === 'ar' ? 'en' : 'ar';
  ARS_LANG = newLang;
  localStorage.setItem('ars_lang', newLang);
  applyLang(newLang);
}

function applyLang(lang) {
  window._clockLang = lang;  // stable reference for clock
  const html = document.documentElement;
  html.setAttribute('lang', lang);
  html.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');

  const btn = document.getElementById('langBtn');
  if (btn) btn.textContent = lang === 'ar' ? 'EN' : 'ع';

  const bsLink = document.getElementById('bsCSS');
  if (bsLink) {
    if (lang === 'ar' && !bsLink.href.includes('rtl')) {
      bsLink.href = bsLink.href.replace('/bootstrap.min.css', '/bootstrap.rtl.min.css');
    } else if (lang === 'en' && bsLink.href.includes('rtl')) {
      bsLink.href = bsLink.href.replace('/bootstrap.rtl.min.css', '/bootstrap.min.css');
    }
  }

  arsTranslateAll(lang);

  // Sidebar direction
  const sidebar  = document.getElementById('sidebar');
  const mainCont = document.querySelector('.main-content');
  if (sidebar && mainCont) {
    if (lang === 'en') {
      sidebar.style.cssText  += ';right:auto;left:0';
      mainCont.style.marginRight = '0';
      mainCont.style.marginLeft  = 'var(--sidebar-w)';
    } else {
      sidebar.style.cssText  += ';left:auto;right:0';
      mainCont.style.marginLeft  = '0';
      mainCont.style.marginRight = 'var(--sidebar-w)';
    }
  }
  loadTicker(lang);
}

document.addEventListener('DOMContentLoaded', () => {
  applyLang(ARS_LANG);
  // Live clock
  function updateClock() {
    const el = document.getElementById('topbarClock');
    if (!el) return;
    const now  = new Date();
    // Use a fixed locale to prevent blinking on lang switch; update on applyLang
    const loc  = (window._clockLang || ARS_LANG) === 'ar' ? 'ar-SA' : 'en-US';
    const datePart = now.toLocaleDateString(loc, {weekday:'short',month:'short',day:'numeric'});
    const timePart = now.toLocaleTimeString(loc, {hour:'2-digit',minute:'2-digit',second:'2-digit'});
    el.textContent = datePart + ' — ' + timePart;
  }
  updateClock();
  if (window._clockInterval) clearInterval(window._clockInterval);
  window._clockInterval = setInterval(updateClock, 1000);
});

// ── Extra keys added for full coverage ──────────────────────────────────────
Object.assign(ARS_TRANS.ar, {
  't_dashboard':'لوحة التحكم','t_calendar':'التقويم التفاعلي','t_calendar_s':'التقويم',
  't_reservations':'الحجوزات','t_new_res':'حجز جديد','t_venues':'القاعات',
  't_checklists':'قوائم المهام','t_contacts':'جهات الاتصال','t_locations':'المواقع',
  't_venues_mgmt':'إدارة القاعات','t_users':'المستخدمون','t_reports_s':'التقارير',
  't_block_period':'حظر فترة','t_bulk_msg':'رسالة جماعية','t_maintenance':'الصيانة',
  't_email_cfg':'إعدادات البريد','t_logout':'تسجيل الخروج',
  't_res_list':'قائمة الحجوزات','t_res_info':'معلومات الحجز',
  't_booking_no':'رقم الحجز','t_title':'العنوان','t_user':'المستخدم',
  't_venue':'القاعة','t_location':'الموقع','t_start_date':'تاريخ البدء',
  't_end_date':'تاريخ الانتهاء','t_req_notes':'ملاحظات الطالب',
  't_app_notes':'ملاحظات الموافقة','t_created_at':'تاريخ الإنشاء',
  't_venue_info':'معلومات القاعة','t_checklist':'قائمة المهام',
  't_approve':'موافقة','t_reject':'رفض','t_cancel':'إلغاء','t_back':'رجوع',
  't_reactivate':'إعادة تفعيل','t_confirm_approve':'تأكيد الموافقة',
  't_confirm_reject':'تأكيد الرفض','t_cancel_res':'إلغاء الحجز',
  't_opt_note':'ملاحظة (اختياري)','t_rej_reason':'سبب الرفض',
  't_res_detail':'تفاصيل الحجز','t_notes':'ملاحظات',
  't_export_print':'تصدير وطباعة:','t_print':'طباعة',
  't_rating':'التقييم','t_rate_res':'قيّم هذا الحجز','t_sent':'أُرسلت',
  't_filter_cal':'تصفية:','t_all_venues':'كل القاعات','t_day_details':'تفاصيل اليوم',
  't_add_for_day':'إضافة حجز لهذا اليوم','t_close':'إغلاق',
  't_my_res':'حجوزاتي','t_leg_avail':'متاح/موافق','t_leg_other':'حجوزات أخرى',
  't_leg_blocked':'محجوب','t_leg_partial':'جزئي/معلق',
  't_preview':'معاينة','t_add':'إضافة','t_comparison':'المقارنة المتقدمة',
  't_blocked':'الفترات المحظورة','t_live_users':'المستخدمون النشطون',
  't_audit_log':'سجل الأنشطة','t_your_info':'معلوماتك',
});
Object.assign(ARS_TRANS.en, {
  't_dashboard':'Dashboard','t_calendar':'Interactive Calendar','t_calendar_s':'Calendar',
  't_reservations':'Reservations','t_new_res':'New Reservation','t_venues':'Venues',
  't_checklists':'Checklists','t_contacts':'Contacts','t_locations':'Locations',
  't_venues_mgmt':'Manage Venues','t_users':'Users','t_reports_s':'Reports',
  't_block_period':'Block Period','t_bulk_msg':'Bulk Message','t_maintenance':'Maintenance',
  't_email_cfg':'Email Settings','t_logout':'Sign Out',
  't_res_list':'Reservations List','t_res_info':'Reservation Info',
  't_booking_no':'Ref. No.','t_title':'Title','t_user':'User',
  't_venue':'Venue','t_location':'Location','t_start_date':'Start Date',
  't_end_date':'End Date','t_req_notes':'Requester Notes',
  't_app_notes':'Approval Notes','t_created_at':'Created At',
  't_venue_info':'Venue Details','t_checklist':'Checklist',
  't_approve':'Approve','t_reject':'Reject','t_cancel':'Cancel','t_back':'Back',
  't_reactivate':'Reactivate','t_confirm_approve':'Confirm Approval',
  't_confirm_reject':'Confirm Rejection','t_cancel_res':'Cancel Reservation',
  't_opt_note':'Note (optional)','t_rej_reason':'Rejection Reason',
  't_res_detail':'Reservation Details','t_notes':'Notes',
  't_export_print':'Export & Print:','t_print':'Print',
  't_rating':'Rating','t_rate_res':'Rate this Reservation','t_sent':'Sent',
  't_filter_cal':'Filter:','t_all_venues':'All Venues','t_day_details':'Day Details',
  't_add_for_day':'Add Reservation for this Day','t_close':'Close',
  't_my_res':'My Reservations','t_leg_avail':'Available/Approved','t_leg_other':'Others\' Bookings',
  't_leg_blocked':'Blocked','t_leg_partial':'Partial/Pending',
  't_preview':'Preview','t_add':'Add','t_comparison':'Advanced Comparison',
  't_blocked':'Blocked Periods','t_live_users':'Live Users',
  't_audit_log':'Audit Log','t_your_info':'Your Connection Info',
});
