"""التقويم التفاعلي — مطابق لـ v54 مع فلاتر كاملة وألوان"""
import io
from flask import Blueprint, render_template, jsonify, request, send_file
from flask_login import login_required, current_user
from models.database import Reservation, Venue, BlockedPeriod, User, Location
from utils.helpers import get_db, get_permissions
from datetime import datetime

calendar_bp = Blueprint('calendar_view', __name__, url_prefix='/calendar')

@calendar_bp.route('/')
@login_required
def index():
    db       = get_db()
    perms    = get_permissions()
    venues   = db.query(Venue).filter_by(is_active=True).order_by(Venue.name).all()
    locations = db.query(Location).filter_by(is_active=True).order_by(Location.name).all()
    return render_template('calendar/index.html', venues=venues, locations=locations, perms=perms)

@calendar_bp.route('/events')
@login_required
def events():
    db    = get_db()
    perms = get_permissions()
    start       = request.args.get('start','')
    end         = request.args.get('end','')
    venue_id    = request.args.get('venue_id','')
    location_id = request.args.get('location_id','')
    fltr        = request.args.get('filter','all')  # all/mine/approved/pending/rejected/blocked

    try:
        start_dt = datetime.fromisoformat(start[:10]) if start else None
        end_dt   = datetime.fromisoformat(end[:10])   if end   else None
    except:
        start_dt = end_dt = None

    # If location filter set but no venue filter, get all venues in that location
    location_venue_ids = []
    if location_id and location_id.isdigit() and not (venue_id and venue_id.isdigit()):
        loc_venues = db.query(Venue.id).filter_by(location_id=int(location_id), is_active=True).all()
        location_venue_ids = [v.id for v in loc_venues]

    result = []

    # ── Blocked periods ───────────────────────────────────────────────────────
    if fltr in ('all','blocked'):
        bq = db.query(BlockedPeriod)
        if start_dt: bq = bq.filter(BlockedPeriod.end_time   >= start_dt)
        if end_dt:   bq = bq.filter(BlockedPeriod.start_time <= end_dt)
        if venue_id and venue_id.isdigit():
            bq = bq.filter(BlockedPeriod.venue_id == int(venue_id))
        elif location_venue_ids:
            bq = bq.filter(BlockedPeriod.venue_id.in_(location_venue_ids))
        for bp in bq.all():
            result.append({
                'id':    f'bp_{bp.id}',
                'title': f'🚫 {bp.reason or "محجوب"} — {bp.venue.name if bp.venue else ""}',
                'start': bp.start_time.isoformat(),
                'end':   bp.end_time.isoformat(),
                'extendedProps': {'type': 'blocked', 'venue': bp.venue.name if bp.venue else ''},
            })

    # ── Reservations ──────────────────────────────────────────────────────────
    if fltr != 'blocked':
        if fltr == 'approved':
            statuses = ['approved']
        elif fltr == 'pending':
            statuses = ['pending']
        elif fltr == 'rejected':
            statuses = ['rejected']
        else:
            statuses = ['approved','pending','rejected','cancelled','completed']

        q = db.query(Reservation).filter(Reservation.status.in_(statuses))

        if fltr == 'mine':
            q = q.filter(Reservation.user_id == current_user.id)
        elif not perms.is_admin_or_manager():
            from sqlalchemy import or_
            q = q.filter(or_(
                Reservation.user_id == current_user.id,
                Reservation.status == 'approved'
            ))

        if start_dt: q = q.filter(Reservation.end_time   >= start_dt)
        if end_dt:   q = q.filter(Reservation.start_time <= end_dt)
        if venue_id and venue_id.isdigit():
            q = q.filter(Reservation.venue_id == int(venue_id))
        elif location_venue_ids:
            q = q.filter(Reservation.venue_id.in_(location_venue_ids))

        for r in q.all():
            is_mine = r.user_id == current_user.id
            result.append({
                'id':    r.id,
                'title': f'{r.title} — {r.venue.name if r.venue else ""}',
                'start': r.start_time.isoformat(),
                'end':   r.end_time.isoformat(),
                'url':   f'/reservations/{r.id}',
                'extendedProps': {
                    'status':    r.status,
                    'type':      'reservation',
                    'is_mine':   is_mine,
                    'user_id':   r.user_id,
                    'user_name': r.user.full_name if r.user else '',
                    'venue':     r.venue.name if r.venue else '',
                },
            })

    return jsonify(result)


@calendar_bp.route('/export-pdf')
@login_required
def export_pdf():
    """Export current month's reservations as PDF"""
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from utils.pdf_helper import arabic_font, ar
    except ImportError:
        return 'reportlab not installed', 500

    db   = get_db()
    now  = datetime.now()
    perms = get_permissions()

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = db.query(Reservation).filter(
        Reservation.start_time >= month_start
    ).order_by(Reservation.start_time)
    if not perms.is_admin_or_manager():
        from sqlalchemy import or_
        q = q.filter(or_(Reservation.user_id == current_user.id, Reservation.status == 'approved'))
    reservations = q.all()

    buf = io.BytesIO()
    orient = request.args.get('orient', 'landscape')
    pagesize = landscape(A4) if orient == 'landscape' else A4
    doc = SimpleDocTemplate(buf, pagesize=pagesize,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    fn = arabic_font()
    elements = []
    title_s = ParagraphStyle('t', fontName=fn, fontSize=16, alignment=1, spaceAfter=12,
                              textColor=colors.HexColor('#0C67EC'))
    sub_s   = ParagraphStyle('s', fontName=fn, fontSize=10, alignment=1, spaceAfter=8,
                              textColor=colors.grey)
    elements.append(Paragraph(ar('تقرير التقويم — الحجوزات الشهرية'), title_s))
    elements.append(Paragraph(ar(f'الفترة: {month_start.strftime("%Y-%m-%d")} — {now.strftime("%Y-%m-%d")}'), sub_s))
    elements.append(Spacer(1, 0.4*cm))

    headers = [ar('رقم الحجز'), ar('العنوان'), ar('القاعة'), ar('البداية'), ar('النهاية'), ar('الحالة')]
    rows = [headers]
    STATUS_MAP = {'pending':'معلق','approved':'موافق','rejected':'مرفوض',
                  'cancelled':'ملغي','completed':'مكتمل'}
    for r in reservations:
        rows.append([
            ar(r.booking_number or ''),
            ar(r.title or ''),
            ar(r.venue.name if r.venue else '—'),
            ar(r.start_time.strftime('%Y-%m-%d %H:%M') if r.start_time else ''),
            ar(r.end_time.strftime('%Y-%m-%d %H:%M') if r.end_time else ''),
            ar(STATUS_MAP.get(r.status, r.status)),
        ])

    if len(rows) == 1:
        rows.append([ar('لا توجد بيانات'), '', '', '', '', ''])

    col_widths = [3.5*cm, 5.5*cm, 4*cm, 4*cm, 4*cm, 3*cm]
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('FONTNAME',  (0,0),(-1,-1), fn),
        ('FONTSIZE',  (0,0),(-1,-1), 9),
        ('ALIGN',     (0,0),(-1,-1), 'CENTER'),
        ('VALIGN',    (0,0),(-1,-1), 'MIDDLE'),
        ('BACKGROUND',(0,0),(-1,0), colors.HexColor('#0C67EC')),
        ('TEXTCOLOR', (0,0),(-1,0), colors.white),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, colors.HexColor('#EBF5FB')]),
        ('GRID',      (0,0),(-1,-1), 0.5, colors.HexColor('#AED6F1')),
        ('ROWHEIGHT', (0,0),(-1,-1), 22),
    ]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    fname = f'calendar_{now.strftime("%Y%m")}.pdf'
    return send_file(buf, as_attachment=True, download_name=fname, mimetype='application/pdf')
