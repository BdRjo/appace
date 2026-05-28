"""
مساعدات مشتركة — مطابق لـ v54 PermissionChecker كاملاً
"""
import functools
from flask import g, current_app, abort
from flask_login import current_user
from models.database import RolePermission, Permission, Location, Venue

def get_db():
    if 'db' not in g:
        Session = current_app.config['DB_SESSION_FACTORY']
        g.db = Session()
    return g.db

def teardown_db(exception):
    db = g.pop('db', None)
    if db is not None:
        if exception:
            db.rollback()
        db.close()


class PermCheck:
    """مطابق حرفياً لـ v54 PermissionChecker"""

    def __init__(self):
        self._cache = {}

    # ── Role helpers — v54 parity ────────────────────────────────────────────
    def is_admin(self):
        if not current_user.is_authenticated: return False
        return bool(current_user.role and current_user.role.name in
                    ('مدير النظام', 'admin', 'Admin', 'System Admin'))

    def is_admin_or_manager(self):
        if not current_user.is_authenticated: return False
        return bool(current_user.role and current_user.role.name in
                    ('مدير النظام', 'admin', 'Admin', 'مشرف', 'Manager'))

    def is_regular_user(self):
        if not current_user.is_authenticated: return False
        return bool(current_user.role and current_user.role.name in ('مستخدم', 'User', 'user'))

    # ── Permission check — مطابق لـ v54 can() ───────────────────────────────
    def can(self, code, action='view'):
        if not current_user.is_authenticated: return False
        if self.is_admin(): return True
        cache_key = f'{code}:{action}'
        if cache_key in self._cache: return self._cache[cache_key]
        db = get_db()
        perm = db.query(Permission).filter_by(code=code).first()
        if not perm:
            self._cache[cache_key] = False
            return False
        rp = db.query(RolePermission).filter_by(
            role_id=current_user.role_id, permission_id=perm.id).first()
        if not rp:
            self._cache[cache_key] = False
            return False
        result = bool(getattr(rp, f'can_{action}', False))
        self._cache[cache_key] = result
        return result

    def can_action(self, code, action):
        """action: view/add/edit/delete/approve"""
        return self.can(code, action)

    def can_view(self, code):   return self.can(code, 'view')
    def can_add(self, code):    return self.can(code, 'add')
    def can_edit(self, code):   return self.can(code, 'edit')
    def can_approve(self, code):return self.can(code, 'approve')
    def can_comment(self, code):return self.is_admin_or_manager() or self.can(code, 'comment')

    def can_delete(self, code):
        # مطابق لـ v54: المستخدم العادي لا يحذف أبداً
        if not current_user.is_authenticated: return False
        if self.is_regular_user(): return False
        return self.can(code, 'delete')

    # ── Location access — مطابق لـ v54 get_allowed_locations ────────────────
    def get_allowed_locations(self):
        if not current_user.is_authenticated: return []
        if self.is_admin_or_manager():
            return get_db().query(Location).filter_by(is_active=True).all()
        # المستخدم العادي: المواقع المعينة له مباشرة + الموروثة من القاعات
        direct_ids = {loc.id for loc in current_user.allowed_locations}
        for venue in current_user.allowed_venues:
            if venue.location_id:
                direct_ids.add(venue.location_id)
        if not direct_ids: return []
        return get_db().query(Location).filter(
            Location.id.in_(direct_ids), Location.is_active == True).all()

    # ── Venue access — مطابق لـ v54 get_allowed_venues ──────────────────────
    def get_allowed_venues(self, location_id=None):
        if not current_user.is_authenticated: return []
        db = get_db()
        if self.is_admin_or_manager():
            q = db.query(Venue).filter_by(is_active=True)
            if location_id: q = q.filter_by(location_id=location_id)
            return q.all()
        allowed_ids = {v.id for v in current_user.allowed_venues}
        if not allowed_ids: return []
        q = db.query(Venue).filter(Venue.id.in_(allowed_ids), Venue.is_active == True)
        if location_id: q = q.filter_by(location_id=location_id)
        return q.all()

    def can_access_venue(self, venue_id):
        if self.is_admin_or_manager(): return True
        return any(v.id == venue_id for v in current_user.allowed_venues)

    # ── can_book_for_others — مطابق لـ v54 ──────────────────────────────────
    def can_book_for_others(self):
        return self.is_admin()


def get_permissions():
    return PermCheck()


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        p = PermCheck()
        if not p.is_admin_or_manager():
            abort(403)
        return f(*args, **kwargs)
    return decorated


def syslog(action, desc, level='info'):
    try:
        from models.database import SystemLog
        db = get_db()
        db.add(SystemLog(action=action, description=desc,
                         user_id=current_user.id if current_user.is_authenticated else None,
                         level=level))
        db.commit()
    except Exception:
        pass


def paginate(query, page, per_page=20):
    total      = query.count()
    items      = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return items, total, total_pages


# ── Jinja helpers ─────────────────────────────────────────────────────────────
STATUS_AR = {
    'pending':   'معلق',
    'approved':  'موافق عليه',
    'rejected':  'مرفوض',
    'cancelled': 'ملغي',
    'completed': 'مكتمل',
}
STATUS_CLS = {
    'pending':   'warning',
    'approved':  'success',
    'rejected':  'danger',
    'cancelled': 'secondary',
    'completed': 'info',
}

def status_label(s): return STATUS_AR.get(s, s)
def status_class(s):  return STATUS_CLS.get(s, 'secondary')


# Pagination compatibility shim (some templates use Pagination object)
class Pagination:
    def __init__(self, query, page, per_page=20):
        self.total      = query.count()
        self.page       = page
        self.per_page   = per_page
        self.items      = query.offset((page-1)*per_page).limit(per_page).all()
        self.total_pages= max(1, (self.total + per_page - 1) // per_page)
        self.has_prev   = page > 1
        self.has_next   = page < self.total_pages
        self.prev_num   = page - 1
        self.next_num   = page + 1
