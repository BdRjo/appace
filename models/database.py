"""
ARS - قاعدة البيانات الكاملة — مطابقة لـ v54
"""
import os, hashlib
try:
    from werkzeug.security import generate_password_hash as _wph
    def _h(pw): return _wph(pw, method='pbkdf2:sha256', salt_length=16)
except ImportError:
    def _h(pw): return hashlib.sha256(pw.encode()).hexdigest()
from datetime import datetime
from sqlalchemy import (create_engine, Column, Integer, String, DateTime,
                        Boolean, ForeignKey, Text, Table, text)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.pool import StaticPool

Base = declarative_base()

user_locations_table = Table('user_locations', Base.metadata,
    Column('user_id',    Integer, ForeignKey('users.id')),
    Column('location_id',Integer, ForeignKey('locations.id')))

user_venues_table = Table('user_venues', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('venue_id',Integer, ForeignKey('venues.id')))

class Role(Base):
    __tablename__ = 'roles'
    id=Column(Integer,primary_key=True); name=Column(String(50),unique=True,nullable=False)
    name_en=Column(String(50)); description=Column(Text); is_default=Column(Boolean,default=False)
    is_active=Column(Boolean,default=True); created_at=Column(DateTime,default=datetime.now)
    users=relationship('User',back_populates='role_ref')
    role_permissions=relationship('RolePermission',back_populates='role',cascade='all, delete-orphan')

class Permission(Base):
    __tablename__ = 'permissions'
    id=Column(Integer,primary_key=True); code=Column(String(50),unique=True,nullable=False)
    name=Column(String(100),nullable=False); name_en=Column(String(100))
    module=Column(String(50)); category=Column(String(50)); description=Column(Text)
    is_active=Column(Boolean,default=True); created_at=Column(DateTime,default=datetime.now)
    role_permissions=relationship('RolePermission',back_populates='permission',cascade='all, delete-orphan')

class RolePermission(Base):
    __tablename__ = 'role_permissions'
    id=Column(Integer,primary_key=True); role_id=Column(Integer,ForeignKey('roles.id'))
    permission_id=Column(Integer,ForeignKey('permissions.id'))
    can_view=Column(Boolean,default=False); can_add=Column(Boolean,default=False)
    can_edit=Column(Boolean,default=False); can_delete=Column(Boolean,default=False)
    can_approve=Column(Boolean,default=False); can_comment=Column(Boolean,default=False)
    role=relationship('Role',back_populates='role_permissions')
    permission=relationship('Permission',back_populates='role_permissions')

class User(Base):
    __tablename__ = 'users'
    id=Column(Integer,primary_key=True); username=Column(String(50),unique=True,nullable=False)
    email=Column(String(100),unique=True,nullable=True); password_hash=Column(String(200),nullable=False)
    role_id=Column(Integer,ForeignKey('roles.id')); full_name=Column(String(100))
    job_title=Column(String(200)); department=Column(String(200))
    phone=Column(String(20)); verification_code=Column(String(10)); verification_expiry=Column(DateTime)
    reset_code=Column(String(10)); reset_code_expiry=Column(DateTime)
    is_verified=Column(Boolean,default=False); is_active=Column(Boolean,default=True)
    language=Column(String(10),default='ar'); last_login=Column(DateTime)
    login_count=Column(Integer,default=0); created_at=Column(DateTime,default=datetime.now)
    role_ref=relationship('Role',back_populates='users')
    allowed_locations=relationship('Location',secondary=user_locations_table,back_populates='allowed_users')
    allowed_venues=relationship('Venue',secondary=user_venues_table,back_populates='allowed_users')
    reservations=relationship('Reservation',foreign_keys='Reservation.user_id',back_populates='user')
    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False
    def get_id(self): return str(self.id)
    @property
    def role(self): return self.role_ref

class Location(Base):
    __tablename__ = 'locations'
    id=Column(Integer,primary_key=True); name=Column(String(100),nullable=False,unique=True)
    name_en=Column(String(100)); city=Column(String(100)); area=Column(String(100))
    is_active=Column(Boolean,default=True); created_at=Column(DateTime,default=datetime.now)
    venues=relationship('Venue',back_populates='location')
    allowed_users=relationship('User',secondary=user_locations_table,back_populates='allowed_locations')

class Venue(Base):
    __tablename__ = 'venues'
    id=Column(Integer,primary_key=True); name=Column(String(100),nullable=False)
    name_en=Column(String(100)); code=Column(String(20),unique=True,nullable=True)
    location_id=Column(Integer,ForeignKey('locations.id')); capacity=Column(Integer)
    equipment=Column(Text); notes=Column(Text); notes_en=Column(Text)
    is_active=Column(Boolean,default=True); requires_approval=Column(Boolean,default=True)
    created_at=Column(DateTime,default=datetime.now)
    location=relationship('Location',back_populates='venues')
    reservations=relationship('Reservation',back_populates='venue')
    blocked_periods=relationship('BlockedPeriod',back_populates='venue')
    allowed_users=relationship('User',secondary=user_venues_table,back_populates='allowed_venues')
    ratings=relationship('Rating',back_populates='venue')

class Contact(Base):
    __tablename__ = 'contacts'
    id=Column(Integer,primary_key=True); first_name=Column(String(100),nullable=False)
    last_name=Column(String(100)); email=Column(String(200),nullable=False)
    phone=Column(String(50)); company=Column(String(200)); job_title=Column(String(200))
    department=Column(String(200)); notes=Column(Text)
    created_by=Column(Integer,ForeignKey('users.id'))
    created_at=Column(DateTime,default=datetime.now)
    creator=relationship('User',foreign_keys=[created_by])

class BookingContact(Base):
    __tablename__='booking_contacts'
    id=Column(Integer,primary_key=True); booking_id=Column(Integer,ForeignKey('reservations.id'),nullable=True)
    contact_id=Column(Integer,ForeignKey('contacts.id'))
    invitation_sent=Column(Boolean,default=False); sent_at=Column(DateTime)
    booking=relationship('Reservation'); contact=relationship('Contact')

class Reservation(Base):
    __tablename__ = 'reservations'
    id=Column(Integer,primary_key=True); booking_number=Column(String(50),unique=True,nullable=False)
    title=Column(String(200),nullable=False); title_en=Column(String(200))
    start_time=Column(DateTime,nullable=False); end_time=Column(DateTime,nullable=False)
    status=Column(String(20),default='pending'); booking_type=Column(String(30),default='official')
    user_id=Column(Integer,ForeignKey('users.id'))
    venue_id=Column(Integer,ForeignKey('venues.id')); approver_id=Column(Integer,ForeignKey('users.id'))
    approval_date=Column(DateTime); approver_notes=Column(Text); requester_notes=Column(Text)
    cancellation_reason=Column(Text); cancelled_by=Column(Integer,ForeignKey('users.id'))
    cancelled_at=Column(DateTime); created_at=Column(DateTime,default=datetime.now)
    requested_employee_id=Column(Integer,ForeignKey('users.id'),nullable=True)
    user=relationship('User',foreign_keys=[user_id],back_populates='reservations')
    venue=relationship('Venue',back_populates='reservations')
    approver=relationship('User',foreign_keys=[approver_id])
    canceller=relationship('User',foreign_keys=[cancelled_by])
    requested_employee=relationship('User',foreign_keys=[requested_employee_id])
    checklist_items=relationship('ChecklistItem',back_populates='reservation',cascade='all, delete-orphan',foreign_keys='ChecklistItem.reservation_id')
    approvals=relationship('Approval',back_populates='reservation',cascade='all, delete-orphan')
    booking_contacts=relationship('BookingContact',cascade='all, delete-orphan',overlaps='booking')
    ratings=relationship('Rating',back_populates='reservation')

class Approval(Base):
    __tablename__='approvals'
    id=Column(Integer,primary_key=True); reservation_id=Column(Integer,ForeignKey('reservations.id'))
    approver_id=Column(Integer,ForeignKey('users.id')); status=Column(String(20))
    comments=Column(Text); created_at=Column(DateTime,default=datetime.now)
    reservation=relationship('Reservation',back_populates='approvals')
    approver=relationship('User',foreign_keys=[approver_id])

class Checklist(Base):
    __tablename__='checklists'
    id=Column(Integer,primary_key=True); name=Column(String(200),nullable=False)
    name_en=Column(String(200)); description=Column(Text)
    is_template=Column(Boolean,default=False); is_public=Column(Boolean,default=True)
    color=Column(String(20),default='#0C67EC'); emoji=Column(String(10),default='📋')
    created_by_id=Column(Integer,ForeignKey('users.id')); created_at=Column(DateTime,default=datetime.now)
    creator=relationship('User',foreign_keys=[created_by_id])
    items=relationship('ChecklistItem',back_populates='checklist',cascade='all, delete-orphan',
                       foreign_keys='ChecklistItem.checklist_id')

class ChecklistShare(Base):
    __tablename__ = 'checklist_shares'
    id           = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey('checklists.id', ondelete='CASCADE'), nullable=False)
    user_id      = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    permission   = Column(String(10), default='view')  # 'view' or 'edit'
    shared_at    = Column(DateTime, default=datetime.now)
    checklist    = relationship('Checklist', foreign_keys=[checklist_id])
    user         = relationship('User', foreign_keys=[user_id])

class ChecklistComment(Base):
    __tablename__ = 'checklist_comments'
    id           = Column(Integer, primary_key=True)
    checklist_id = Column(Integer, ForeignKey('checklists.id', ondelete='CASCADE'), nullable=False)
    item_id      = Column(Integer, ForeignKey('checklist_items.id', ondelete='CASCADE'), nullable=True)
    user_id      = Column(Integer, ForeignKey('users.id'), nullable=False)
    content      = Column(Text, nullable=False)
    created_at   = Column(DateTime, default=datetime.now)
    checklist    = relationship('Checklist', foreign_keys=[checklist_id])
    item         = relationship('ChecklistItem', foreign_keys=[item_id])
    user         = relationship('User', foreign_keys=[user_id])

class ChecklistItem(Base):
    __tablename__='checklist_items'
    id=Column(Integer,primary_key=True); checklist_id=Column(Integer,ForeignKey('checklists.id'),nullable=True)
    reservation_id=Column(Integer,ForeignKey('reservations.id'),nullable=True)
    content=Column(String(500),nullable=False); content_en=Column(String(500))
    note=Column(Text)
    is_checked=Column(Boolean,default=False); checked_by_id=Column(Integer,ForeignKey('users.id'))
    checked_at=Column(DateTime); due_date=Column(DateTime); priority=Column(Integer,default=0)
    order_index=Column(Integer,default=0)
    checklist=relationship('Checklist',back_populates='items',foreign_keys=[checklist_id])
    reservation=relationship('Reservation',back_populates='checklist_items',foreign_keys=[reservation_id])
    checked_by=relationship('User',foreign_keys=[checked_by_id])


class ReservationComment(Base):
    __tablename__ = 'reservation_comments'
    id             = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey('reservations.id', ondelete='CASCADE'), nullable=False)
    user_id        = Column(Integer, ForeignKey('users.id'), nullable=False)
    content        = Column(Text, nullable=False)
    is_internal    = Column(Boolean, default=False)  # True = admin only
    created_at     = Column(DateTime, default=datetime.now)
    reservation    = relationship('Reservation', foreign_keys=[reservation_id])
    user           = relationship('User', foreign_keys=[user_id])

class ReservationLog(Base):
    __tablename__ = 'reservation_logs'
    id             = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey('reservations.id', ondelete='CASCADE'), nullable=False)
    user_id        = Column(Integer, ForeignKey('users.id'), nullable=True)
    action         = Column(String(50), nullable=False)  # created/approved/rejected/cancelled/edited/commented
    description    = Column(Text)
    created_at     = Column(DateTime, default=datetime.now)
    reservation    = relationship('Reservation', foreign_keys=[reservation_id])
    user           = relationship('User', foreign_keys=[user_id])

class Rating(Base):
    __tablename__='ratings'
    id=Column(Integer,primary_key=True); user_id=Column(Integer,ForeignKey('users.id'))
    venue_id=Column(Integer,ForeignKey('venues.id')); reservation_id=Column(Integer,ForeignKey('reservations.id'))
    rating=Column(Integer); comment=Column(Text); created_at=Column(DateTime,default=datetime.now)
    user=relationship('User'); venue=relationship('Venue',back_populates='ratings')
    reservation=relationship('Reservation',back_populates='ratings')

class BlockedPeriod(Base):
    __tablename__='blocked_periods'
    id=Column(Integer,primary_key=True); venue_id=Column(Integer,ForeignKey('venues.id'))
    location_id=Column(Integer,ForeignKey('locations.id'))
    start_time=Column(DateTime,nullable=False); end_time=Column(DateTime,nullable=False)
    reason=Column(String(500)); reason_en=Column(String(500))
    created_by_id=Column(Integer,ForeignKey('users.id')); created_at=Column(DateTime,default=datetime.now)
    venue=relationship('Venue',back_populates='blocked_periods')
    location=relationship('Location',foreign_keys=[location_id])
    created_by=relationship('User',foreign_keys=[created_by_id])

class EmailLog(Base):
    __tablename__='email_logs'
    id=Column(Integer,primary_key=True); recipient=Column(String(200)); subject=Column(String(500))
    type=Column(String(50)); status=Column(String(20)); error_message=Column(Text)
    sent_at=Column(DateTime,default=datetime.now); user_id=Column(Integer,ForeignKey('users.id'))

class Notification(Base):
    __tablename__ = 'notifications'
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title      = Column(String(200), nullable=False)
    body       = Column(Text)
    link       = Column(String(300))
    is_read    = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    user       = relationship('User', foreign_keys=[user_id])

class SystemLog(Base):
    __tablename__='system_logs'
    id=Column(Integer,primary_key=True); action=Column(String(100)); description=Column(Text)
    user_id=Column(Integer,ForeignKey('users.id')); level=Column(String(20),default='info')
    created_at=Column(DateTime,default=datetime.now)
    user=relationship('User',foreign_keys=[user_id])

class LoginLog(Base):
    __tablename__='login_logs'
    id=Column(Integer,primary_key=True); user_id=Column(Integer,ForeignKey('users.id'),nullable=True)
    username=Column(String(100)); ip_address=Column(String(60)); hostname=Column(String(200))
    platform=Column(String(200)); success=Column(Boolean,default=False); reason=Column(String(200))
    created_at=Column(DateTime,default=datetime.now); login_time=Column(DateTime,default=datetime.now)
    user=relationship('User',foreign_keys=[user_id])

_engine = None
_Session = None


# ── Contact Group (Distribution List) ─────────────────────────────────────────
group_contacts_table = Table('group_contacts', Base.metadata,
    Column('group_id',   Integer, ForeignKey('contact_groups.id')),
    Column('contact_id', Integer, ForeignKey('contacts.id')),
)

group_users_table = Table('group_users', Base.metadata,
    Column('group_id', Integer, ForeignKey('contact_groups.id')),
    Column('user_id',  Integer, ForeignKey('users.id')),
)

class ContactGroup(Base):
    __tablename__ = 'contact_groups'
    id          = Column(Integer, primary_key=True)
    name        = Column(String(100), nullable=False)
    description = Column(String(300))
    created_by  = Column(Integer, ForeignKey('users.id'))
    created_at  = Column(DateTime, default=datetime.now)
    is_active   = Column(Boolean, default=True)
    creator     = relationship('User', foreign_keys=[created_by])
    contacts    = relationship('Contact', secondary=group_contacts_table, backref='groups')
    users       = relationship('User',    secondary=group_users_table,    backref='contact_groups')

def get_engine():
    global _engine, _Session
    if _engine is not None:
        return _engine
    db_url = os.environ.get('DATABASE_URL','')
    if db_url.startswith('postgres://'): db_url='postgresql://'+db_url[11:]
    if db_url and db_url.startswith('postgresql'):
        _engine=create_engine(db_url,pool_size=10,max_overflow=20,pool_pre_ping=True,pool_recycle=300)
        print('✅ قاعدة البيانات: PostgreSQL')
    else:
        db_path=os.environ.get('DB_PATH','ars_venues.db')
        _engine=create_engine(
            f'sqlite:///{db_path}',
            connect_args={'check_same_thread':False, 'timeout': 30},
            poolclass=StaticPool
        )
        from sqlalchemy import event
        @event.listens_for(_engine,'connect')
        def set_wal(conn,rec):
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA cache_size=10000')
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA busy_timeout=30000')
        print(f'✅ قاعدة البيانات: SQLite WAL ({db_path})')
    Base.metadata.create_all(_engine)
    # ── Safe column migration ─────────────────────────────────────────────────
    _safe_cols = [
        ('reservations', 'requested_employee_id', 'INTEGER REFERENCES users(id)'),
        ('contacts', 'company',   'VARCHAR(200)'),
        ('contacts', 'job_title', 'VARCHAR(200)'),
        ('contacts',        'notes',      'TEXT'),
        ('contacts',        'department', 'VARCHAR(200)'),
        ('checklist_items', 'note',       'TEXT'),
        ('users',           'job_title',  'VARCHAR(200)'),
        ('users',           'department', 'VARCHAR(200)'),
        ('checklists',      'color',      "VARCHAR(20) DEFAULT '#0C67EC'"),
        ('checklists',      'emoji',      "VARCHAR(10) DEFAULT '📋'"),
        ('role_permissions', 'can_comment', 'INTEGER DEFAULT 0'),
    ]
    # ── Create all new tables + safe column migrations in ONE transaction ────
    with _engine.connect() as conn:
        # New tables
        conn.execute(text('''CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient VARCHAR(200), subject VARCHAR(500),
            type VARCHAR(50), status VARCHAR(20), error_message TEXT,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER REFERENCES users(id))'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS checklist_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checklist_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            permission VARCHAR(10) DEFAULT 'view',
            shared_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS checklist_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checklist_id INTEGER NOT NULL, item_id INTEGER,
            user_id INTEGER NOT NULL, content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS reservation_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            content TEXT NOT NULL, is_internal INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS reservation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL, user_id INTEGER,
            action VARCHAR(50) NOT NULL, description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, title VARCHAR(200) NOT NULL,
            body TEXT, link VARCHAR(300), is_read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title_ar VARCHAR(300) NOT NULL, title_en VARCHAR(300) DEFAULT '',
            body_ar TEXT, body_en TEXT,
            media_type VARCHAR(20) DEFAULT 'none',
            media_url TEXT, media_b64 TEXT,
            target VARCHAR(20) DEFAULT 'all',
            target_roles TEXT DEFAULT '', target_users TEXT DEFAULT '',
            display_mode VARCHAR(20) DEFAULT 'once_session',
            modal_size VARCHAR(20) DEFAULT 'medium',
            modal_pos VARCHAR(20) DEFAULT 'center',
            header_color VARCHAR(30) DEFAULT '#0847B0,#0C67EC',
            is_active INTEGER DEFAULT 1,
            start_date DATETIME, end_date DATETIME,
            created_by INTEGER REFERENCES users(id),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS announcement_dismissals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            announcement_id INTEGER NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            dismissed_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        # Parent Interview tables (safe migration for older databases)
        conn.execute(text('''CREATE TABLE IF NOT EXISTS pi_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(200) NOT NULL, event_code VARCHAR(20) UNIQUE NOT NULL,
            school_name VARCHAR(200), school_logo_url VARCHAR(500),
            brand_color VARCHAR(10) DEFAULT '#0d6efd', description TEXT,
            event_date VARCHAR(200), slot_duration INTEGER DEFAULT 5,
            break_duration INTEGER DEFAULT 0, allow_comments INTEGER DEFAULT 1,
            allow_multiple_children INTEGER DEFAULT 0,
            send_reminders INTEGER DEFAULT 1, reminder_hours INTEGER DEFAULT 24,
            is_active INTEGER DEFAULT 1, is_open INTEGER DEFAULT 1,
            created_by INTEGER REFERENCES users(id),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS pi_teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES pi_events(id),
            name VARCHAR(200) NOT NULL, email VARCHAR(200),
            subjects VARCHAR(500), room VARCHAR(100),
            teacher_code VARCHAR(30), is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS pi_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL REFERENCES pi_teachers(id),
            event_id INTEGER NOT NULL REFERENCES pi_events(id),
            slot_date VARCHAR(20) NOT NULL, start_time VARCHAR(10) NOT NULL,
            end_time VARCHAR(10) NOT NULL, is_break INTEGER DEFAULT 0,
            is_booked INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS pi_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL REFERENCES pi_slots(id),
            event_id INTEGER NOT NULL REFERENCES pi_events(id),
            booking_ref VARCHAR(30) UNIQUE NOT NULL,
            parent_name VARCHAR(200) NOT NULL, parent_email VARCHAR(200),
            parent_phone VARCHAR(50), child_name VARCHAR(200) NOT NULL,
            comment TEXT, session_id VARCHAR(100),
            booked_by_staff INTEGER DEFAULT 0, reminder_sent INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'confirmed',
            cancelled_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS pi_appointment_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES pi_events(id),
    request_code VARCHAR(30) UNIQUE NOT NULL,
    parent_name VARCHAR(200) NOT NULL, parent_email VARCHAR(200),
    parent_phone VARCHAR(50), child_name VARCHAR(200) NOT NULL,
    child_grade VARCHAR(50), reason TEXT NOT NULL,
    preferred_date VARCHAR(20), preferred_time VARCHAR(20),
    status VARCHAR(20) DEFAULT 'pending', admin_notes TEXT,
    assigned_slot_id INTEGER REFERENCES pi_slots(id),
    assigned_date VARCHAR(20), assigned_time VARCHAR(10),
    approved_by INTEGER REFERENCES users(id),
    approved_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS pi_calendar_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_date VARCHAR(20) NOT NULL, start_time VARCHAR(10) NOT NULL,
            end_time VARCHAR(10) NOT NULL, status VARCHAR(20) DEFAULT 'available',
            note TEXT, created_by INTEGER REFERENCES users(id),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS pi_calendar_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER REFERENCES pi_calendar_slots(id),
            booking_date VARCHAR(20), start_time VARCHAR(10), end_time VARCHAR(10),
            request_code VARCHAR(30) UNIQUE NOT NULL,
            requester_name VARCHAR(200) NOT NULL, requester_email VARCHAR(200),
            requester_phone VARCHAR(50), person_to_meet VARCHAR(200) NOT NULL,
            reason TEXT NOT NULL, status VARCHAR(20) DEFAULT 'pending',
            admin_notes TEXT, approved_by INTEGER REFERENCES users(id),
            approved_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
        conn.commit()
        # Safe column migrations — all in one go, ignore errors (column exists)
        safe_cols = [
            ('reservations',    'requested_employee_id', 'INTEGER REFERENCES users(id)'),
            ('contacts',        'company',               'VARCHAR(200)'),
            ('contacts',        'job_title',             'VARCHAR(200)'),
            ('contacts',        'notes',                 'TEXT'),
            ('contacts',        'department',            'VARCHAR(200)'),
            ('checklist_items', 'note',                  'TEXT'),
            ('users',           'job_title',             'VARCHAR(200)'),
            ('users',           'department',            'VARCHAR(200)'),
            ('checklists',      'color',                 "VARCHAR(20) DEFAULT '#0C67EC'"),
            ('checklists',      'emoji',                 "VARCHAR(10) DEFAULT '📋'"),
            ('role_permissions','can_comment',           'INTEGER DEFAULT 0'),
            # Announcement new columns (v60)
            ('announcements',   'modal_size',            "VARCHAR(20) DEFAULT 'medium'"),
            ('announcements',   'modal_pos',             "VARCHAR(20) DEFAULT 'center'"),
            ('announcements',   'header_color',          "VARCHAR(30) DEFAULT '#0847B0,#0C67EC'"),
            # Calendar bookings — free-form date/time columns (v65)
            ('pi_calendar_bookings', 'booking_date',     'VARCHAR(20)'),
            ('pi_calendar_bookings', 'start_time',       'VARCHAR(10)'),
            ('pi_calendar_bookings', 'end_time',         'VARCHAR(10)'),
        ]
        for tbl, col, cdef in safe_cols:
            try:
                conn.execute(text(f'ALTER TABLE {tbl} ADD COLUMN {col} {cdef}'))
                conn.commit()
            except Exception:
                pass  # column already exists
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine

def get_session():
    get_engine()
    return _Session()

class Attachment(Base):
    __tablename__ = 'attachments'
    id            = Column(Integer, primary_key=True)
    reservation_id= Column(Integer, ForeignKey('reservations.id', ondelete='CASCADE'), nullable=True)
    filename      = Column(String(255))
    mimetype      = Column(String(100), default='application/octet-stream')
    filedata      = Column(Text)  # base64
    uploaded_at   = Column(DateTime, default=datetime.now)
    uploaded_by   = Column(Integer, ForeignKey('users.id'), nullable=True)
    uploader      = relationship('User', foreign_keys=[uploaded_by])


# ── Announcements ─────────────────────────────────────────────────────────────
class Announcement(Base):
    __tablename__ = 'announcements'
    id           = Column(Integer, primary_key=True)
    title_ar     = Column(String(300), nullable=False)
    title_en     = Column(String(300), nullable=False, default='')
    body_ar      = Column(Text)
    body_en      = Column(Text)
    media_type   = Column(String(20), default='none')   # none / image / video_url / video_file
    media_url    = Column(Text)                          # URL or base64
    media_b64    = Column(Text)                          # uploaded image base64
    target       = Column(String(20), default='all')    # all / role / users
    target_roles = Column(Text, default='')             # comma-separated role names
    target_users = Column(Text, default='')             # comma-separated user IDs
    display_mode = Column(String(20), default='once_session')  # once_session / once_ever / always
    modal_size   = Column(String(20), default='medium')        # small / medium / large / fullscreen
    modal_pos    = Column(String(20), default='center')        # center / top / bottom
    header_color = Column(String(30), default='#0847B0,#0C67EC')  # gradient start,end
    is_active    = Column(Boolean, default=True)
    start_date   = Column(DateTime, nullable=True)
    end_date     = Column(DateTime, nullable=True)
    created_by   = Column(Integer, ForeignKey('users.id'))
    created_at   = Column(DateTime, default=datetime.now)
    creator      = relationship('User', foreign_keys=[created_by])
    dismissals   = relationship('AnnouncementDismissal', back_populates='announcement',
                                cascade='all, delete-orphan')


class AnnouncementDismissal(Base):
    """Tracks which users have dismissed which announcements"""
    __tablename__ = 'announcement_dismissals'
    id              = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey('announcements.id', ondelete='CASCADE'))
    user_id         = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    dismissed_at    = Column(DateTime, default=datetime.now)
    announcement    = relationship('Announcement', back_populates='dismissals')
    user            = relationship('User', foreign_keys=[user_id])

def seed_database(session):
    if session.query(User).count() > 0:
        return
    print('🌱 بذر قاعدة البيانات...')

    # ── الخطوة 1: الصلاحيات ─────────────────────────────────────────────────
    perms_data = [
        ('dashboard_view','عرض لوحة التحكم','رئيسي'),
        ('calendar_view','عرض التقويم','رئيسي'),
        ('locations_view','عرض المواقع','مواقع'),
        ('locations_add','إضافة مواقع','مواقع'),
        ('locations_edit','تعديل مواقع','مواقع'),
        ('locations_delete','حذف مواقع','مواقع'),
        ('venues_view','عرض القاعات','قاعات'),
        ('venues_add','إضافة قاعات','قاعات'),
        ('venues_edit','تعديل قاعات','قاعات'),
        ('venues_delete','حذف قاعات','قاعات'),
        ('reservations_view','عرض الحجوزات','حجوزات'),
        ('reservations_add','إضافة حجوزات','حجوزات'),
        ('reservations_edit','تعديل حجوزات','حجوزات'),
        ('reservations_delete','حذف حجوزات','حجوزات'),
        ('reservations_approve','الموافقة على الحجوزات','حجوزات'),
        ('users_view','عرض المستخدمين','مستخدمين'),
        ('users_add','إضافة مستخدمين','مستخدمين'),
        ('users_edit','تعديل مستخدمين','مستخدمين'),
        ('users_delete','حذف مستخدمين','مستخدمين'),
        ('reports_view','عرض التقارير','تقارير'),
        ('reports_export','تصدير التقارير','تقارير'),
        ('checklists_view','عرض قوائم المهام','مهام'),
        ('checklists_add','إضافة قوائم مهام','مهام'),
        ('checklists_edit','تعديل قوائم مهام','مهام'),
        ('checklists_delete','حذف قوائم مهام','مهام'),
        ('contacts_view','عرض جهات الاتصال','اتصال'),
        ('contacts_add','إضافة جهات اتصال','اتصال'),
        ('contacts_edit','تعديل جهات اتصال','اتصال'),
        ('maintenance_access','الوصول للصيانة','إدارة'),
        ('settings_access','الوصول للإعدادات','إدارة'),
    ]
    perm_objs = {}
    for code, name, module in perms_data:
        p = Permission(code=code, name=name, module=module, category=module)
        session.add(p)
        perm_objs[code] = p
    session.flush()

    # ── الخطوة 2: الأدوار ───────────────────────────────────────────────────
    admin_role   = Role(name='مدير النظام', name_en='Admin',   description='كامل الصلاحيات',    is_default=True)
    manager_role = Role(name='مشرف',        name_en='Manager', description='صلاحيات إشرافية',   is_default=True)
    user_role    = Role(name='مستخدم',      name_en='User',    description='صلاحيات أساسية',    is_default=True)
    session.add_all([admin_role, manager_role, user_role])
    session.flush()

    for p in perm_objs.values():
        session.add(RolePermission(role_id=admin_role.id, permission_id=p.id,
            can_view=True, can_add=True, can_edit=True, can_delete=True, can_approve=True))
    for p in perm_objs.values():
        session.add(RolePermission(role_id=manager_role.id, permission_id=p.id,
            can_view=True, can_add='add' in p.code, can_edit='edit' in p.code,
            can_delete=False, can_approve='approve' in p.code))
    for code in ['dashboard_view','calendar_view','venues_view','reservations_view',
                 'reservations_add','checklists_view','reports_view','contacts_view']:
        if code in perm_objs:
            session.add(RolePermission(role_id=user_role.id, permission_id=perm_objs[code].id,
                can_view=True, can_add=(code == 'reservations_add'),
                can_edit=False, can_delete=False, can_approve=False))

    # ── الخطوة 3: المستخدمون الأساسيون ─────────────────────────────────────
    def _h(pw): return hashlib.sha256(pw.encode()).hexdigest()
    session.add(User(username='admin',   email='admin@ars.local',
        password_hash=_h('admin'),   role_id=admin_role.id,
        full_name='مدير النظام',  is_verified=True, is_active=True))
    session.add(User(username='manager', email='manager@ars.local',
        password_hash=_h('manager'), role_id=manager_role.id,
        full_name='المشرف العام', is_verified=True, is_active=True))
    session.add(User(username='user',    email='user@ars.local',
        password_hash=_h('user'),    role_id=user_role.id,
        full_name='مستخدم عادي', is_verified=True, is_active=True))

    # ✅ حفظ المستخدمين الأساسيين أولاً — هذا الأهم
    session.commit()
    print('✅ تم إنشاء المستخدمين: admin / manager / user')

    # ── الخطوة 4: البيانات التجريبية (اختيارية — لا تؤثر على الدخول) ────────
    try:
        from datetime import timedelta
        admin_user   = session.query(User).filter_by(username='admin').first()
        manager_user = session.query(User).filter_by(username='manager').first()
        regular_user = session.query(User).filter_by(username='user').first()

        loc1 = Location(name='المبنى الرئيسي',  name_en='Main Building',    city='الرياض', area='حي الملك عبدالله', is_active=True)
        loc2 = Location(name='مركز المؤتمرات', name_en='Conference Center', city='الرياض', area='حي السفارات',      is_active=True)
        session.add_all([loc1, loc2])
        session.flush()

        venue1 = Venue(name='قاعة الاجتماعات الكبرى',    code='MH-01',  capacity=50,  location_id=loc1.id, is_active=True, requires_approval=True)
        venue2 = Venue(name='قاعة التدريب A',             code='TR-A',   capacity=20,  location_id=loc1.id, is_active=True, requires_approval=False)
        venue3 = Venue(name='قاعة المؤتمرات الدولية',   code='CC-INT', capacity=200, location_id=loc2.id, is_active=True, requires_approval=True)
        session.add_all([venue1, venue2, venue3])
        session.flush()

        import random, string
        def _res(title, user, venue, days_offset, duration_h=2, status='approved', rtype='official'):
            sd = datetime.now() + timedelta(days=days_offset)
            sd = sd.replace(hour=9, minute=0, second=0, microsecond=0)
            bn = 'RES-' + ''.join(random.choices(string.digits, k=6))
            return Reservation(booking_number=bn, title=title, user_id=user.id,
                               venue_id=venue.id, start_time=sd,
                               end_time=sd + timedelta(hours=duration_h),
                               status=status, booking_type=rtype,
                               requester_notes='ملاحظة تجريبية')

        reservations = [
            _res('اجتماع مجلس الإدارة',       admin_user,   venue1,  0,  3),
            _res('دورة تدريبية متقدمة',        manager_user, venue2,  1,  4),
            _res('مؤتمر التقنية السنوي',       admin_user,   venue3,  2,  8,  'approved', 'external'),
            _res('اجتماع فريق التطوير',        regular_user, venue2,  3,  2,  'pending'),
            _res('ورشة عمل القيادة',           manager_user, venue1,  5,  3),
            _res('اجتماع المستخدمين',          regular_user, venue2, -2,  2),
            _res('عرض تقديمي للمشروع',         regular_user, venue1,  7,  1,  'pending'),
            _res('لقاء الإدارة العليا',        admin_user,   venue3, -5,  4,  'completed'),
            _res('تدريب الموظفين الجدد',       manager_user, venue2, 10,  5),
            _res('حجز مؤجل',                   regular_user, venue1, -1,  2,  'rejected'),
        ]
        for r in reservations:
            session.add(r)
        session.flush()

        bp = BlockedPeriod(
            venue_id=venue3.id,
            start_time=(datetime.now() + timedelta(days=14)).replace(hour=0,  minute=0),
            end_time  =(datetime.now() + timedelta(days=16)).replace(hour=23, minute=59),
            reason='صيانة دورية للقاعة',
            created_by_id=admin_user.id
        )
        session.add(bp)
        session.commit()
        print(f'✅ بيانات تجريبية: {len(reservations)} حجز + فترة محظورة + 3 قاعات + موقعان')

    except Exception as e:
        session.rollback()
        print(f'⚠️ البيانات التجريبية فشلت (التطبيق يعمل بشكل طبيعي): {e}')


# ══════════════════════════════════════════════════════════════════════════════
# PARENT INTERVIEWS MODULE
# ══════════════════════════════════════════════════════════════════════════════

class PIEvent(Base):
    """Interview Event (e.g. Term 1 Parent-Teacher Interviews)"""
    __tablename__ = 'pi_events'
    id              = Column(Integer, primary_key=True)
    name            = Column(String(200), nullable=False)
    event_code      = Column(String(20), unique=True, nullable=False)
    school_name     = Column(String(200))
    school_logo_url = Column(String(500))
    brand_color     = Column(String(10), default='#0d6efd')
    description     = Column(Text)
    event_date      = Column(String(200))
    slot_duration   = Column(Integer, default=5)
    break_duration  = Column(Integer, default=0)
    allow_comments  = Column(Boolean, default=True)
    allow_multiple_children = Column(Boolean, default=False)
    send_reminders  = Column(Boolean, default=True)
    reminder_hours  = Column(Integer, default=24)
    is_active       = Column(Boolean, default=True)
    is_open         = Column(Boolean, default=True)
    created_by      = Column(Integer, ForeignKey('users.id'))
    created_at      = Column(DateTime, default=datetime.now)
    teachers        = relationship('PITeacher', back_populates='event', cascade='all, delete-orphan')
    creator         = relationship('User', foreign_keys=[created_by])

class PITeacher(Base):
    """Teacher participating in an interview event"""
    __tablename__ = 'pi_teachers'
    id          = Column(Integer, primary_key=True)
    event_id    = Column(Integer, ForeignKey('pi_events.id'), nullable=False)
    name        = Column(String(200), nullable=False)
    email       = Column(String(200))
    subjects    = Column(String(500))
    room        = Column(String(100))
    teacher_code = Column(String(30))
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.now)
    event       = relationship('PIEvent', back_populates='teachers')
    slots       = relationship('PISlot', back_populates='teacher', cascade='all, delete-orphan')

class PISlot(Base):
    """Individual time slot for a teacher"""
    __tablename__ = 'pi_slots'
    id          = Column(Integer, primary_key=True)
    teacher_id  = Column(Integer, ForeignKey('pi_teachers.id'), nullable=False)
    event_id    = Column(Integer, ForeignKey('pi_events.id'), nullable=False)
    slot_date   = Column(String(20), nullable=False)
    start_time  = Column(String(10), nullable=False)
    end_time    = Column(String(10), nullable=False)
    is_break    = Column(Boolean, default=False)
    is_booked   = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.now)
    teacher     = relationship('PITeacher', back_populates='slots')
    booking     = relationship('PIBooking', back_populates='slot', uselist=False)

class PIBooking(Base):
    """Parent booking record"""
    __tablename__ = 'pi_bookings'
    id              = Column(Integer, primary_key=True)
    slot_id         = Column(Integer, ForeignKey('pi_slots.id'), nullable=False)
    event_id        = Column(Integer, ForeignKey('pi_events.id'), nullable=False)
    booking_ref     = Column(String(30), unique=True, nullable=False)
    parent_name     = Column(String(200), nullable=False)
    parent_email    = Column(String(200))
    parent_phone    = Column(String(50))
    child_name      = Column(String(200), nullable=False)
    comment         = Column(Text)
    session_id      = Column(String(100))
    booked_by_staff = Column(Boolean, default=False)
    reminder_sent   = Column(Boolean, default=False)
    status          = Column(String(20), default='confirmed')
    cancelled_at    = Column(DateTime)
    created_at      = Column(DateTime, default=datetime.now)
    slot            = relationship('PISlot', back_populates='booking')
    event           = relationship('PIEvent')

class PIAppointmentRequest(Base):
    """General appointment request — parent requests a meeting, admin assigns"""
    __tablename__ = 'pi_appointment_requests'
    id              = Column(Integer, primary_key=True)
    event_id        = Column(Integer, ForeignKey('pi_events.id'), nullable=False)
    request_code    = Column(String(30), unique=True, nullable=False)
    parent_name     = Column(String(200), nullable=False)
    parent_email    = Column(String(200))
    parent_phone    = Column(String(50))
    child_name      = Column(String(200), nullable=False)
    child_grade     = Column(String(50))
    reason          = Column(Text, nullable=False)
    preferred_date  = Column(String(20))
    preferred_time  = Column(String(20))  # e.g. "morning" / "afternoon" or specific HH:MM
    status          = Column(String(20), default='pending')  # pending/approved/rejected/amended
    admin_notes     = Column(Text)
    assigned_slot_id = Column(Integer, ForeignKey('pi_slots.id'), nullable=True)
    assigned_date   = Column(String(20))
    assigned_time   = Column(String(10))
    approved_by     = Column(Integer, ForeignKey('users.id'), nullable=True)
    approved_at     = Column(DateTime)
    created_at      = Column(DateTime, default=datetime.now)
    event           = relationship('PIEvent')
    assigned_slot   = relationship('PISlot')
    approver        = relationship('User', foreign_keys=[approved_by])

class PICalendarSlot(Base):
    """General appointment calendar — blocked periods / breaks managed by admin"""
    __tablename__ = 'pi_calendar_slots'
    id          = Column(Integer, primary_key=True)
    slot_date   = Column(String(20), nullable=False)
    start_time  = Column(String(10), nullable=False)
    end_time    = Column(String(10), nullable=False)
    status      = Column(String(20), default='available')  # available/blocked
    note        = Column(Text)
    created_by  = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at  = Column(DateTime, default=datetime.now)
    creator     = relationship('User', foreign_keys=[created_by])
    bookings    = relationship('PICalendarBooking', back_populates='slot', cascade='all, delete-orphan')

class PICalendarBooking(Base):
    """Public appointment request — user picks any time within work hours"""
    __tablename__ = 'pi_calendar_bookings'
    id              = Column(Integer, primary_key=True)
    slot_id         = Column(Integer, ForeignKey('pi_calendar_slots.id'), nullable=True)  # kept for backwards compat
    booking_date    = Column(String(20))   # date picked by user (YYYY-MM-DD)
    start_time      = Column(String(10))   # from time picked by user (HH:MM)
    end_time        = Column(String(10))   # to time picked by user (HH:MM)
    request_code    = Column(String(30), unique=True, nullable=False)
    requester_name  = Column(String(200), nullable=False)
    requester_email = Column(String(200))
    requester_phone = Column(String(50))
    person_to_meet  = Column(String(200), nullable=False)
    reason          = Column(Text, nullable=False)
    status          = Column(String(20), default='pending')  # pending/approved/rejected
    admin_notes     = Column(Text)
    approved_by     = Column(Integer, ForeignKey('users.id'), nullable=True)
    approved_at     = Column(DateTime)
    created_at      = Column(DateTime, default=datetime.now)
    slot            = relationship('PICalendarSlot', back_populates='bookings')
    approver        = relationship('User', foreign_keys=[approved_by])
