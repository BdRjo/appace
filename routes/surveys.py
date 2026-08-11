"""
routes/surveys.py — Survey / Form Builder
Google-Forms-style form builder: admin creates a survey (blank or from a
template), adds questions of various types, publishes it either open to
anyone with the link or gated behind an access code (same idea as the
event check-in codes), and reviews/export responses afterward.
"""
import json
import random
import string
from datetime import datetime

from flask import (Blueprint, render_template, redirect, url_for, request,
                    flash, jsonify, abort, session, Response)

from utils.helpers import get_db, admin_required
from utils.i18n import t, get_lang
from models.database import Survey, SurveyQuestion, SurveyResponse, SurveyAnswer, SurveyInvite, SASConfig

surveys_bp = Blueprint('surveys', __name__, url_prefix='/surveys')

QUESTION_TYPES = ['short_text', 'paragraph', 'multiple_choice', 'checkboxes',
                   'dropdown', 'linear_scale', 'date', 'time']
CHOICE_TYPES = {'multiple_choice', 'checkboxes', 'dropdown'}


def _t(ar_text, en_text):
    return ar_text if get_lang() == 'ar' else en_text


def _gen_code(length=6):
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(random.choices(alphabet, k=length))


def _get_school_config():
    db = get_db()
    return db.query(SASConfig).first()


# ===========================================================================
# READY-MADE TEMPLATES
# ===========================================================================

SURVEY_TEMPLATES = {
    'employee_satisfaction': {
        'name_ar': 'استبيان رضا الموظفين', 'name_en': 'Employee Satisfaction Survey',
        'desc_ar': 'قياس رضا الموظفين عن بيئة العمل وجوانب التحسين الممكنة.',
        'desc_en': 'Measure employee satisfaction and identify areas to improve.',
        'questions': [
            {'type': 'short_text', 'text_ar': 'القسم / الإدارة', 'text_en': 'Department', 'required': False},
            {'type': 'linear_scale', 'text_ar': 'ما مدى رضاك العام عن بيئة العمل؟', 'text_en': 'Overall, how satisfied are you with the work environment?',
             'required': True, 'scale_min': 1, 'scale_max': 5,
             'min_label_ar': 'غير راضٍ', 'max_label_ar': 'راضٍ جداً', 'min_label_en': 'Not satisfied', 'max_label_en': 'Very satisfied'},
            {'type': 'multiple_choice', 'text_ar': 'هل تشعر أن جهودك مُقدَّرة؟', 'text_en': 'Do you feel your efforts are recognized?',
             'required': True, 'options_ar': ['نعم دائماً', 'أحياناً', 'نادراً', 'أبداً'],
             'options_en': ['Always', 'Sometimes', 'Rarely', 'Never']},
            {'type': 'checkboxes', 'text_ar': 'أي الجوانب تحتاج تحسيناً؟ (اختر كل ما ينطبق)', 'text_en': 'Which areas need improvement? (select all that apply)',
             'required': False,
             'options_ar': ['التواصل الداخلي', 'فرص التطوير المهني', 'بيئة العمل المادية', 'التقدير والمكافآت', 'التوازن بين العمل والحياة'],
             'options_en': ['Internal communication', 'Professional development', 'Physical workspace', 'Recognition & rewards', 'Work-life balance']},
            {'type': 'multiple_choice', 'text_ar': 'هل توصي بالعمل هنا لصديق؟', 'text_en': 'Would you recommend working here to a friend?',
             'required': True, 'options_ar': ['نعم', 'ربما', 'لا'], 'options_en': ['Yes', 'Maybe', 'No']},
            {'type': 'paragraph', 'text_ar': 'أي ملاحظات أو اقتراحات إضافية؟', 'text_en': 'Any additional comments or suggestions?', 'required': False},
        ],
    },
    'event_evaluation': {
        'name_ar': 'تقييم فعالية', 'name_en': 'Event Evaluation',
        'desc_ar': 'تقييم فعالية أو اجتماع بعد انتهائه.',
        'desc_en': 'Evaluate an event or meeting after it ends.',
        'questions': [
            {'type': 'linear_scale', 'text_ar': 'كيف تقيّم الفعالية بشكل عام؟', 'text_en': 'How would you rate the event overall?',
             'required': True, 'scale_min': 1, 'scale_max': 5,
             'min_label_ar': 'ضعيف', 'max_label_ar': 'ممتاز', 'min_label_en': 'Poor', 'max_label_en': 'Excellent'},
            {'type': 'multiple_choice', 'text_ar': 'هل كان تنظيم الوقت مناسباً؟', 'text_en': 'Was the timing well organized?',
             'required': True, 'options_ar': ['نعم', 'إلى حد ما', 'لا'], 'options_en': ['Yes', 'Somewhat', 'No']},
            {'type': 'checkboxes', 'text_ar': 'ما الذي أعجبك بالفعالية؟', 'text_en': 'What did you like about the event?',
             'required': False,
             'options_ar': ['المحتوى', 'المتحدثون', 'التنظيم', 'المكان', 'التفاعل'],
             'options_en': ['Content', 'Speakers', 'Organization', 'Venue', 'Interaction']},
            {'type': 'dropdown', 'text_ar': 'هل ستحضر فعالية مشابهة مستقبلاً؟', 'text_en': 'Would you attend a similar event in the future?',
             'required': True, 'options_ar': ['بالتأكيد', 'ربما', 'غير محتمل'], 'options_en': ['Definitely', 'Maybe', 'Unlikely']},
            {'type': 'paragraph', 'text_ar': 'أي اقتراحات لتحسين الفعاليات القادمة؟', 'text_en': 'Suggestions to improve future events?', 'required': False},
        ],
    },
    'general_feedback': {
        'name_ar': 'استبيان عام', 'name_en': 'General Feedback',
        'desc_ar': 'استبيان بسيط لجمع ملاحظات عامة.',
        'desc_en': 'A simple form to collect general feedback.',
        'questions': [
            {'type': 'short_text', 'text_ar': 'الاسم (اختياري)', 'text_en': 'Name (optional)', 'required': False},
            {'type': 'linear_scale', 'text_ar': 'تقييمك العام', 'text_en': 'Overall rating',
             'required': True, 'scale_min': 1, 'scale_max': 5,
             'min_label_ar': 'ضعيف', 'max_label_ar': 'ممتاز', 'min_label_en': 'Poor', 'max_label_en': 'Excellent'},
            {'type': 'paragraph', 'text_ar': 'ملاحظاتك', 'text_en': 'Your feedback', 'required': True},
        ],
    },
}


# ===========================================================================
# ADMIN
# ===========================================================================

@surveys_bp.route('/admin')
@admin_required
def admin_list():
    db = get_db()
    surveys = db.query(Survey).order_by(Survey.created_at.desc()).all()
    return render_template('surveys/admin/list.html', surveys=surveys)


@surveys_bp.route('/admin/new', methods=['GET', 'POST'])
@admin_required
def admin_new():
    if request.method == 'GET':
        return render_template('surveys/admin/new.html', templates=SURVEY_TEMPLATES)

    db = get_db()
    lang = get_lang()
    name = request.form.get('name', '').strip()
    template_key = request.form.get('template', '')

    if template_key and template_key in SURVEY_TEMPLATES:
        tpl = SURVEY_TEMPLATES[template_key]
        survey = Survey(
            name=name or (tpl['name_ar'] if lang == 'ar' else tpl['name_en']),
            description=tpl['desc_ar'] if lang == 'ar' else tpl['desc_en'],
        )
        db.add(survey)
        db.flush()
        for i, q in enumerate(tpl['questions']):
            options = q.get('options_ar' if lang == 'ar' else 'options_en')
            db.add(SurveyQuestion(
                survey_id=survey.id, order_num=i,
                question_type=q['type'],
                question_text=q['text_ar'] if lang == 'ar' else q['text_en'],
                required=q.get('required', False),
                options_json=json.dumps(options, ensure_ascii=False) if options else None,
                scale_min=q.get('scale_min', 1), scale_max=q.get('scale_max', 5),
                scale_min_label=(q.get('min_label_ar') if lang == 'ar' else q.get('min_label_en')) or None,
                scale_max_label=(q.get('max_label_ar') if lang == 'ar' else q.get('max_label_en')) or None,
            ))
    else:
        if not name:
            flash(_t('يرجى إدخال اسم الاستمارة', 'Please enter a form name'), 'danger')
            return redirect(url_for('surveys.admin_new'))
        survey = Survey(name=name)
        db.add(survey)

    db.commit()
    flash(_t('تم إنشاء الاستمارة', 'Form created'), 'success')
    return redirect(url_for('surveys.admin_builder', survey_id=survey.id))


@surveys_bp.route('/admin/<int:survey_id>')
@admin_required
def admin_builder(survey_id):
    db = get_db()
    survey = db.get(Survey, survey_id)
    if not survey:
        abort(404)
    fill_url = url_for('surveys.public_survey', survey_id=survey.id, _external=True)
    return render_template('surveys/admin/builder.html', survey=survey, fill_url=fill_url,
                            question_types=QUESTION_TYPES)


@surveys_bp.route('/admin/<int:survey_id>/save', methods=['POST'])
@admin_required
def admin_save(survey_id):
    db = get_db()
    survey = db.get(Survey, survey_id)
    if not survey:
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'ok': False, 'error': 'Invalid data'}), 400

    survey.name = (data.get('name') or '').strip() or survey.name
    survey.description = (data.get('description') or '').strip()
    survey.is_published = bool(data.get('is_published', False))
    survey.require_code = bool(data.get('require_code', False))
    survey.collect_name = bool(data.get('collect_name', False))
    if survey.require_code and not survey.access_code:
        survey.access_code = _gen_code()

    # Update existing questions in place (preserves their id, so existing
    # responses stay correctly linked), add new ones, delete removed ones.
    incoming_ids = set()
    for idx, q in enumerate(data.get('questions', [])):
        qid = q.get('id')
        options = q.get('options') or []
        options_json = json.dumps(options, ensure_ascii=False) if options else None
        sq = None
        if qid:
            sq = db.get(SurveyQuestion, qid)
            if not sq or sq.survey_id != survey.id:
                sq = None
        if not sq:
            sq = SurveyQuestion(survey_id=survey.id)
            db.add(sq)
            db.flush()
        sq.order_num = idx
        sq.question_type = q.get('type', 'short_text')
        sq.question_text = (q.get('text') or '').strip()
        sq.required = bool(q.get('required', False))
        sq.options_json = options_json
        sq.scale_min = q.get('scale_min', 1)
        sq.scale_max = q.get('scale_max', 5)
        sq.scale_min_label = q.get('scale_min_label') or None
        sq.scale_max_label = q.get('scale_max_label') or None
        incoming_ids.add(sq.id)

    for sq in list(survey.questions):
        if sq.id not in incoming_ids:
            db.delete(sq)

    db.commit()
    return jsonify({'ok': True})


def _normalize_text(s):
    """Lowercase, collapse whitespace, and strip invisible Unicode marks
    that often sneak into text copy-pasted from Excel/Word."""
    if not s:
        return ''
    for ch in ('\u200b', '\u200c', '\u200d', '\u200e', '\u200f', '\ufeff'):
        s = s.replace(ch, '')
    return ' '.join(s.split()).lower()


def _parse_name_email_rows(uploaded_file, bulk_text):
    """Parse either an uploaded .xlsx/.xls/.csv file or pasted 'Name,Email'
    lines into a list of (name, email) pairs. Accepts the Arabic comma "،"
    and semicolon "؛" as separators too."""
    if uploaded_file and uploaded_file.filename:
        filename = uploaded_file.filename.lower()
        rows = []
        if filename.endswith('.csv'):
            import csv as csv_mod
            text_stream = uploaded_file.stream.read().decode('utf-8-sig', errors='ignore')
            for parts in csv_mod.reader(text_stream.splitlines()):
                if parts:
                    rows.append(parts)
        elif filename.endswith('.xlsx') or filename.endswith('.xls'):
            import openpyxl
            wb = openpyxl.load_workbook(uploaded_file, data_only=True, read_only=True)
            ws = wb.worksheets[0]
            for row in ws.iter_rows(values_only=True):
                rows.append(['' if c is None else str(c) for c in row])
        else:
            return []
        pairs = []
        for r in rows:
            name = (r[0] if len(r) > 0 else '').strip()
            email = (r[1] if len(r) > 1 else '').strip()
            if not name:
                continue
            if email and '@' not in email:
                continue  # looks like a header row
            pairs.append((name, email))
        return pairs

    pairs = []
    for line in (bulk_text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        normalized = line.replace('\t', ',').replace('،', ',').replace('؛', ',')
        parts = [p.strip() for p in normalized.split(',')]
        name = parts[0] if parts else ''
        email = parts[1] if len(parts) > 1 else ''
        if name:
            pairs.append((name, email))
    return pairs


@surveys_bp.route('/admin/<int:survey_id>/invites/add', methods=['POST'])
@admin_required
def admin_invites_add(survey_id):
    db = get_db()
    survey = db.get(Survey, survey_id)
    if not survey:
        abort(404)

    try:
        pairs = _parse_name_email_rows(request.files.get('file'), request.form.get('bulk_text', ''))
    except Exception as e:
        flash(_t(f'تعذرت قراءة الملف: {e}', f'Could not read the file: {e}'), 'danger')
        return redirect(url_for('surveys.admin_builder', survey_id=survey.id))

    existing_codes = {i.code for i in survey.invites}
    seen_emails = {_normalize_text(i.email) for i in survey.invites if i.email}
    seen_names = {_normalize_text(i.name) for i in survey.invites if not i.email}

    added = 0
    skipped_duplicates = 0
    for name, email in pairs:
        email_key = _normalize_text(email)
        name_key = _normalize_text(name)
        if email_key and email_key in seen_emails:
            skipped_duplicates += 1
            continue
        if not email_key and name_key in seen_names:
            skipped_duplicates += 1
            continue
        if email_key:
            seen_emails.add(email_key)
        else:
            seen_names.add(name_key)
        code = _gen_code()
        while code in existing_codes:
            code = _gen_code()
        existing_codes.add(code)
        db.add(SurveyInvite(survey_id=survey.id, name=name, email=email, code=code))
        added += 1
    db.commit()

    msg = _t(f'تمت إضافة {added} مدعو', f'Added {added} invitees')
    if skipped_duplicates:
        msg += _t(f' (تم تجاهل {skipped_duplicates} صف مكرر)', f' ({skipped_duplicates} duplicate rows skipped)')
    flash(msg, 'success')
    return redirect(url_for('surveys.admin_builder', survey_id=survey.id))


@surveys_bp.route('/admin/<int:survey_id>/invites/<int:iid>/delete', methods=['POST'])
@admin_required
def admin_invite_delete(survey_id, iid):
    db = get_db()
    inv = db.get(SurveyInvite, iid)
    if inv and inv.survey_id == survey_id:
        db.delete(inv)
        db.commit()
    return jsonify({'ok': True})


@surveys_bp.route('/admin/<int:survey_id>/invites/bulk-delete', methods=['POST'])
@admin_required
def admin_invites_bulk_delete(survey_id):
    db = get_db()
    survey = db.get(Survey, survey_id)
    if not survey:
        abort(404)
    selected_ids = request.form.getlist('invite_ids', type=int)
    if not selected_ids:
        flash(_t('لم يتم تحديد أي مدعو', 'No invitees selected'), 'danger')
        return redirect(url_for('surveys.admin_builder', survey_id=survey.id))
    deleted = (
        db.query(SurveyInvite)
        .filter(SurveyInvite.survey_id == survey.id, SurveyInvite.id.in_(selected_ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    flash(_t(f'تم حذف {deleted} مدعو', f'{deleted} invitees deleted'), 'success')
    return redirect(url_for('surveys.admin_builder', survey_id=survey.id))


@surveys_bp.route('/admin/<int:survey_id>/invites/send-codes', methods=['POST'])
@admin_required
def admin_invites_send_codes(survey_id):
    db = get_db()
    survey = db.get(Survey, survey_id)
    if not survey:
        abort(404)

    from utils.email_helper import send_survey_invite_code
    lang = get_lang()
    fill_url = url_for('surveys.public_survey', survey_id=survey.id, _external=True)

    selected_ids = request.form.getlist('invite_ids', type=int)
    if selected_ids:
        targets = [i for i in survey.invites if i.id in selected_ids and i.email]
    else:
        only_unsent = request.form.get('only_unsent', '1') == '1'
        targets = [i for i in survey.invites if (not only_unsent or not i.code_sent) and i.email]

    sent, failed = 0, 0
    for inv in targets:
        try:
            ok = send_survey_invite_code(inv.email, inv.name, inv.code, survey.name, fill_url, lang)
        except Exception:
            ok = False
        if ok:
            inv.code_sent = True
            sent += 1
        else:
            failed += 1
    db.commit()

    msg = _t(f'تم إرسال {sent} رمز بنجاح', f'{sent} codes sent successfully')
    if failed:
        msg += _t(f'، وفشل إرسال {failed}', f', {failed} failed')
        msg += _t(' — راجع صفحة سجل البريد لسبب الفشل', ' — check Email Logs for the reason')
    flash(msg, 'success' if not failed else 'warning')
    return redirect(url_for('surveys.admin_builder', survey_id=survey.id))


@surveys_bp.route('/admin/<int:survey_id>/delete', methods=['POST'])
@admin_required
def admin_delete(survey_id):
    db = get_db()
    survey = db.get(Survey, survey_id)
    if not survey:
        abort(404)
    db.delete(survey)
    db.commit()
    flash(_t('تم حذف الاستمارة', 'Form deleted'), 'success')
    return redirect(url_for('surveys.admin_list'))


@surveys_bp.route('/admin/<int:survey_id>/responses')
@admin_required
def admin_responses(survey_id):
    db = get_db()
    survey = db.get(Survey, survey_id)
    if not survey:
        abort(404)
    responses = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.survey_id == survey.id)
        .order_by(SurveyResponse.submitted_at.desc())
        .all()
    )

    def _display_value(answer_text):
        if not answer_text:
            return ''
        if answer_text.startswith('['):
            try:
                return ', '.join(json.loads(answer_text))
            except Exception:
                return answer_text
        return answer_text

    # Pre-build a {question_id: display string} map per response, so the
    # template never needs to parse JSON itself.
    response_rows = []
    for r in responses:
        ans_map = {a.question_id: _display_value(a.answer_text) for a in r.answers}
        response_rows.append((r, ans_map))

    summary = {}
    for q in survey.questions:
        if q.question_type in CHOICE_TYPES or q.question_type == 'linear_scale':
            counts = {}
            for r in responses:
                for a in r.answers:
                    if a.question_id != q.id or not a.answer_text:
                        continue
                    if a.answer_text.startswith('['):
                        try:
                            vals = json.loads(a.answer_text)
                        except Exception:
                            vals = [a.answer_text]
                    else:
                        vals = [a.answer_text]
                    for v in vals:
                        counts[v] = counts.get(v, 0) + 1
            summary[q.id] = counts
    return render_template('surveys/admin/responses.html', survey=survey, response_rows=response_rows, summary=summary)


@surveys_bp.route('/admin/<int:survey_id>/responses/export')
@admin_required
def admin_responses_export(survey_id):
    import csv
    import io

    db = get_db()
    survey = db.get(Survey, survey_id)
    if not survey:
        abort(404)
    responses = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.survey_id == survey.id)
        .order_by(SurveyResponse.submitted_at.asc())
        .all()
    )

    buf = io.StringIO()
    buf.write('\ufeff')
    writer = csv.writer(buf)
    writer.writerow(['Respondent', 'Submitted At'] + [q.question_text for q in survey.questions])
    for r in responses:
        ans_by_q = {a.question_id: a.answer_text for a in r.answers}
        row = [r.respondent_name or '', r.submitted_at.strftime('%Y-%m-%d %H:%M') if r.submitted_at else '']
        for q in survey.questions:
            val = ans_by_q.get(q.id, '') or ''
            if val.startswith('['):
                try:
                    val = ', '.join(json.loads(val))
                except Exception:
                    pass
            row.append(val)
        writer.writerow(row)

    filename = f'survey_export_{survey.id}.csv'
    return Response(buf.getvalue(), mimetype='text/csv',
                     headers={'Content-Disposition': f'attachment; filename="{filename}"'})


# ===========================================================================
# PUBLIC (no login)
# ===========================================================================

@surveys_bp.route('/<int:survey_id>', methods=['GET', 'POST'])
def public_survey(survey_id):
    db = get_db()
    survey = db.get(Survey, survey_id)
    if not survey or not survey.is_published:
        abort(404)
    cfg = _get_school_config()

    session_key = f'survey_{survey.id}_invite_id'
    if survey.require_code and not session.get(session_key):
        error = None
        if request.method == 'POST':
            code = request.form.get('code', '').strip().upper()
            invite = (
                db.query(SurveyInvite)
                .filter(SurveyInvite.survey_id == survey.id, SurveyInvite.code == code)
                .first()
            )
            if not invite:
                error = _t('الرمز غير صحيح', 'Invalid code')
            elif invite.used_at:
                error = _t('تم استخدام هذا الرمز مسبقاً', 'This code has already been used')
            else:
                session[session_key] = invite.id
                return redirect(url_for('surveys.public_survey', survey_id=survey.id))
        return render_template('surveys/gate.html', survey=survey, config=cfg, error=error)

    return render_template('surveys/fill.html', survey=survey, config=cfg, error=None)


@surveys_bp.route('/<int:survey_id>/submit', methods=['POST'])
def public_submit(survey_id):
    db = get_db()
    survey = db.get(Survey, survey_id)
    if not survey or not survey.is_published:
        abort(404)

    session_key = f'survey_{survey.id}_invite_id'
    invite = None
    if survey.require_code:
        invite_id = session.get(session_key)
        invite = db.get(SurveyInvite, invite_id) if invite_id else None
        if not invite or invite.survey_id != survey.id or invite.used_at:
            abort(403)

    respondent_name = invite.name if invite else (
        request.form.get('respondent_name', '').strip() if survey.collect_name else None
    )
    response = SurveyResponse(survey_id=survey.id, respondent_name=respondent_name or None)
    db.add(response)
    db.flush()

    missing_required = False
    for q in survey.questions:
        field_name = f'q_{q.id}'
        if q.question_type == 'checkboxes':
            values = request.form.getlist(field_name)
            answer_text = json.dumps(values, ensure_ascii=False) if values else None
        else:
            val = request.form.get(field_name, '').strip()
            answer_text = val or None
        if q.required and not answer_text:
            missing_required = True
        if answer_text:
            db.add(SurveyAnswer(response_id=response.id, question_id=q.id, answer_text=answer_text))

    if missing_required:
        db.rollback()
        cfg = _get_school_config()
        return render_template('surveys/fill.html', survey=survey, config=cfg,
                                error=_t('يرجى تعبئة كل الأسئلة الإجبارية', 'Please fill in all required questions'))

    if invite:
        invite.used_at = datetime.now()
        session.pop(session_key, None)

    db.commit()
    cfg = _get_school_config()
    return render_template('surveys/thanks.html', survey=survey, config=cfg)
