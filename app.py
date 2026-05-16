"""STAP Student Tracking & Appointments — Web v4"""
import os
from flask import Flask, g
from flask_cors import CORS
from flask_login import LoginManager
from models.database import get_engine, User, seed_database
from sqlalchemy.orm import sessionmaker, joinedload

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY','ars-dev-secret-2026-CHANGE-THIS')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    app.config['SESSION_PERMANENT'] = False
    app.config['REMEMBER_COOKIE_DURATION'] = __import__('datetime').timedelta(days=1)
    # ── Security config ───────────────────────────────────────────────────────
    app.config['SESSION_COOKIE_HTTPONLY']  = True
    app.config['SESSION_COOKIE_SAMESITE']  = 'Lax'
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
    # Use Secure cookies in production (HTTPS)
    is_prod = os.environ.get('FLASK_ENV', 'production') == 'production'
    app.config['SESSION_COOKIE_SECURE']  = is_prod
    app.config['REMEMBER_COOKIE_SECURE'] = is_prod
    # ── CSRF Protection ───────────────────────────────────────────────────────
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']
    app.config['WTF_CSRF_SSL_STRICT'] = False
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)
    # Exempt mobile API from CSRF (uses JWT instead)
    from routes.mobile_api import mobile_api_bp
    from routes.download_data import dl_bp as _mapi
    csrf.exempt(_mapi)
    # ── Rate Limiter ──────────────────────────────────────────────────────────
    from utils.limiter import limiter
    limiter.init_app(app)
    app.extensions['limiter'] = limiter
    # Enable CORS for mobile app
    CORS(app, resources={r"/mobile-api/*": {"origins": "*"}})
    
    engine  = get_engine()
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    app.config['DB_SESSION_FACTORY'] = Session

    try:
        s = Session(); seed_database(s); s.close()
    except Exception as e:
        current_app.logger.warning(f"⚠️ Seed: {e}")

    # ── Migration: إضافة الأعمدة المفقودة ─────────────────────────────────────
    try:
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            # requested_employee_email
            conn.execute(text("""
                ALTER TABLE reservations
                ADD COLUMN IF NOT EXISTS requested_employee_email VARCHAR(200)
            """))
            # Allow null user_id for public/guest bookings
            conn.execute(text("""
                ALTER TABLE reservations
                ALTER COLUMN user_id DROP NOT NULL
            """))
            conn.commit()
    except Exception as e:
        print(f"⚠️ Column migration: {e}")

    # ── Migration v86: SAS time fields ───────────────────────────────────────
    try:
        from sqlalchemy import text
        with get_engine().connect() as conn:
            conn.execute(text("ALTER TABLE sas_records ADD COLUMN IF NOT EXISTS all_day INTEGER DEFAULT 1"))
            conn.execute(text("ALTER TABLE sas_records ADD COLUMN IF NOT EXISTS time_from VARCHAR(10)"))
            conn.execute(text("ALTER TABLE sas_records ADD COLUMN IF NOT EXISTS time_to VARCHAR(10)"))
            conn.commit()
    except Exception as e:
        print(f"⚠️ SAS v86 migration: {e}")

    # ── DB session per request ────────────────────────────────────────────────
    @app.before_request
    def open_db():
        if 'db' not in g:
            g.db = Session()

    @app.teardown_appcontext
    def close_db(exception):
        db = g.pop('db', None)
        if db is not None:
            if exception:
                db.rollback()
            db.close()

    # ── Login manager ─────────────────────────────────────────────────────────
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = ''
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(uid):
        try:
            db = g.get('db') or Session()
            return (db.query(User)
                      .options(joinedload(User.role_ref))
                      .filter(User.id == int(uid))
                      .first())
        except Exception:
            return None

    # ── Register all blueprints ───────────────────────────────────────────────
    from routes.auth          import auth_bp
    from routes.admin         import admin_bp
    from routes.api           import api_bp
    from routes.users         import users_bp
    from routes.settings      import settings_bp
    from routes.cp            import cp_bp
    from routes.announcements import announcements_bp
    from routes.interviews    import interviews_bp
    from routes.eas import eas_bp
    from routes.sas           import sas_bp
    from routes.mobile_api import mobile_api_bp
    from routes.download_data import dl_bp

    for bp in [auth_bp, admin_bp, api_bp, eas_bp,
               users_bp, settings_bp, cp_bp,
               announcements_bp, interviews_bp, sas_bp, mobile_api_bp, dl_bp]:
        app.register_blueprint(bp)        

    # Jinja filters
    from utils.helpers import status_label, status_class
    def fmt_date(val, fmt='%Y-%m-%d'):
        if val is None: return ''
        if isinstance(val, str): return val[:10]
        return val.strftime(fmt)
    app.jinja_env.filters['fmt_date'] = fmt_date
    app.jinja_env.filters['status_label'] = status_label
    app.jinja_env.filters['status_class'] = status_class

    @app.context_processor
    def inject_globals():
        from flask import current_app, session
        from flask_login import current_user
        from utils.helpers import get_permissions
        import json, os
        def get_maintenance_config():
            try:
                p = os.path.join(os.path.dirname(__file__), 'maintenance_config.json')
                cfg = json.loads(open(p).read()) if os.path.exists(p) else {}
                # Brand defaults — قابلة للتخصيص لكل عميل
                cfg.setdefault('brand_name',    'نظام STAP')
                cfg.setdefault('brand_name_en', 'STAP System')
                cfg.setdefault('brand_tagline',    'نظام إدارة الفعاليات والحجوزات')
                cfg.setdefault('brand_tagline_en', 'Student Tracking & Appointments')
                cfg.setdefault('brand_short',    'STAP')
                cfg.setdefault('brand_short_en', 'STAP')
                return cfg
            except: return {
                'brand_name': 'نظام STAP', 'brand_name_en': 'STAP System',
                'brand_tagline': 'نظام إدارة الفعاليات', 'brand_tagline_en': 'Event Management',
                'brand_short': 'STAP', 'brand_short_en': 'STAP',
            }
        def get_system_colors():
            try:
                p = os.path.join(os.path.dirname(__file__), 'maintenance_config.json')
                cfg = json.loads(open(p).read()) if os.path.exists(p) else {}
                return {
                    'primary':       cfg.get('color_primary',       '#0C67EC'),
                    'primary_dark':  cfg.get('color_primary_dark',  '#0847B0'),
                    'primary_light': cfg.get('color_primary_light', '#3D8EF5'),
                    'accent':        cfg.get('color_accent',        '#D4A853'),
                    'bg':            cfg.get('color_bg',            '#EEF4FD'),
                }
            except: return {'primary':'#0C67EC','primary_dark':'#0847B0','primary_light':'#3D8EF5','accent':'#D4A853','bg':'#EEF4FD'}
        def cp_enabled(page_id, feature_id=None):
            """Check if a page/feature is enabled in CP config"""
            try:
                p = os.path.join(os.path.dirname(__file__), 'cp_config.json')
                if not os.path.exists(p): return True
                cfg = json.loads(open(p).read())
                page_cfg = cfg.get('pages', {}).get(page_id, {})
                if feature_id is None:
                    return page_cfg.get('enabled', True)
                return page_cfg.get('features', {}).get(feature_id, True)
            except: return True
        from utils.i18n import t, get_lang
        def get_ticker_bg():
            try:
                p = os.path.join(os.path.dirname(__file__), 'maintenance_config.json')
                cfg = json.loads(open(p).read()) if os.path.exists(p) else {}
                ticker = cfg.get('ticker', {})
                bg = ticker.get('bg', '#000000')
                op = ticker.get('opacity', 0)
                if op == 0: return 'transparent'
                hex_ = bg.replace('#','')
                r = int(hex_[0:2],16); g = int(hex_[2:4],16); b = int(hex_[4:6],16)
                return f'rgba({r},{g},{b},{op/100:.2f})'
            except: return 'transparent'
        def _build_ticker_cfg(json_path, default_ar, default_en, default_fg, default_bg):
            try:
                lang = get_lang()
                cfg = json.loads(open(json_path).read()) if os.path.exists(json_path) else {}
                # Language-aware feed selection with cross-language fallback
                if lang == 'en':
                    feeds = cfg.get('feeds_en', [])
                    if not feeds:
                        feeds = cfg.get('feeds_ar', [])
                else:
                    feeds = cfg.get('feeds_ar', [])
                    if not feeds:
                        feeds = cfg.get('feeds_en', [])
                sep_img = cfg.get('sep_img_url', '')
                if sep_img:
                    sep_html = f' <img src="{sep_img}" style="width:24px;height:24px;object-fit:contain;vertical-align:middle;border-radius:50%;margin:0 8px;opacity:.85"> '
                else:
                    sep_html = ' ◆ '
                if not feeds:
                    feeds = [default_en if lang == 'en' else default_ar]
                text = sep_html.join(feeds)
                fg = cfg.get('fg', default_fg)
                font = cfg.get('font', 'Tahoma')
                size = cfg.get('size', 15)
                speed = cfg.get('speed', 35)
                opacity = cfg.get('opacity', 0)
                bg_raw = cfg.get('bg', '')
                if opacity <= 0:
                    bg_css = 'transparent'
                elif bg_raw:
                    hex_ = bg_raw.replace('#','')
                    try:
                        r2 = int(hex_[0:2],16); g2 = int(hex_[2:4],16); b2 = int(hex_[4:6],16)
                        bg_css = f'rgba({r2},{g2},{b2},{opacity/100:.2f})'
                    except Exception: bg_css = default_bg
                else: bg_css = default_bg
                logo_url = cfg.get('logo_url', '')
                logo_size = cfg.get('logo_size', 28)
                logo_pulse = cfg.get('logo_pulse', True)
                logo_pulse_speed = cfg.get('logo_pulse_speed', 14)
                sep_img_url = cfg.get('sep_img_url', '')
                mask_fade = cfg.get('mask_fade', 12)
                interview_mode = cfg.get('interview_mode', 'scroll')
                return {'text': text, 'feeds': feeds, 'fg': fg, 'font': font,
                        'size': size, 'speed': speed, 'bg': bg_css, 'logo_url': logo_url,
                        'logo_size': logo_size, 'logo_pulse': logo_pulse,
                        'logo_pulse_speed': logo_pulse_speed,
                        'sep_img_url': sep_img_url, 'mask_fade': mask_fade,
                        'interview_mode': interview_mode}
            except Exception as e:
                current_app.logger.warning(f"{__name__} error: {e}")
                _fb = default_en if get_lang() == 'en' else default_ar
                return {'text': _fb, 'feeds': [_fb], 'fg': default_fg,
                        'font': 'Tahoma', 'size': 15, 'speed': 35, 'bg': default_bg, 'logo_url': '',
                        'logo_size': 28, 'logo_pulse': True, 'logo_pulse_speed': 14,
                        'sep_img_url': '', 'mask_fade': 12, 'interview_mode': 'scroll'}
        def get_ticker_cfg():
            return _build_ticker_cfg(
                os.path.join(os.path.dirname(__file__), 'ticker_config.json'),
                'مرحباً بكم في نظام STAP لالحضور والمقابلات', 'Welcome to STAP Reservation System',
                '#F2C99A', '#28559B')
        def get_auth_ticker_cfg():
            return _build_ticker_cfg(
                os.path.join(os.path.dirname(__file__), 'auth_ticker_config.json'),
                'مرحباً بكم — سجّل دخولك للمتابعة', 'Welcome — Please sign in',
                '#ffffff', '#1a3a6c')
        def get_interview_ticker_cfg():
            cfg = _build_ticker_cfg(
                os.path.join(os.path.dirname(__file__), 'interview_ticker_config.json'),
                'مرحباً بكم في بوابة مقابلات أولياء الأمور', 'Welcome to the Parent Interview Portal',
                '#ffffff', '#2563eb')
            # Interview pages have light background — if bg is transparent, darken text
            if cfg['bg'] == 'transparent' and cfg['fg'].lower() in ('#ffffff', '#fff', 'white'):
                cfg['fg'] = '#1e293b'
            return cfg
        def get_sas_ticker_cfg():
            """Build SAS ticker config from DB (SASConfig.ticker_json) instead of file"""
            try:
                from models.database import SASConfig
                lang = get_lang()
                db = g.get('db')
                sas_cfg = db.query(SASConfig).first() if db else None
                raw = sas_cfg.ticker_json if sas_cfg and sas_cfg.ticker_json else '{}'
                cfg = json.loads(raw)
                # Language-aware feed selection with cross-language fallback
                if lang == 'en':
                    feeds = cfg.get('feeds_en', [])
                    if not feeds:
                        feeds = cfg.get('feeds_ar', [])  # fallback to AR if EN empty
                else:
                    feeds = cfg.get('feeds_ar', [])
                    if not feeds:
                        feeds = cfg.get('feeds_en', [])  # fallback to EN if AR empty
                sep_img = cfg.get('sep_img_url', '')
                sep_html = f' <img src="{sep_img}" style="width:24px;height:24px;object-fit:contain;vertical-align:middle;border-radius:50%;margin:0 8px;opacity:.85"> ' if sep_img else '   '
                if not feeds:
                    feeds = ['Welcome to Student Attendance Management' if lang == 'en' else 'مرحباً بكم في إدارة دوام الطلبة']
                text = sep_html.join(feeds)
                fg = cfg.get('fg', '#1e293b')
                font = cfg.get('font', 'Tahoma')
                size = cfg.get('size', 15)
                speed = cfg.get('speed', 35)
                opacity = cfg.get('opacity', 0)
                bg_raw = cfg.get('bg', '')
                if opacity <= 0:
                    bg_css = 'transparent'
                elif bg_raw:
                    hex_ = bg_raw.replace('#','')
                    try:
                        r2 = int(hex_[0:2],16); g2 = int(hex_[2:4],16); b2 = int(hex_[4:6],16)
                        bg_css = f'rgba({r2},{g2},{b2},{opacity/100:.2f})'
                    except Exception: bg_css = '#0e7490'
                else: bg_css = '#0e7490'
                return {'text': text, 'feeds': feeds, 'fg': fg, 'font': font,
                        'size': size, 'speed': speed, 'bg': bg_css,
                        'logo_url': cfg.get('logo_url', ''),
                        'logo_size': cfg.get('logo_size', 28),
                        'logo_pulse': cfg.get('logo_pulse', True),
                        'logo_pulse_speed': cfg.get('logo_pulse_speed', 6),
                        'sep_img_url': sep_img, 'mask_fade': cfg.get('mask_fade', 12),
                        'interview_mode': 'scroll'}
            except Exception as e:
                current_app.logger.warning(f'SAS ticker config error: {e}')
                lang = session.get('lang', 'ar')
                _default_feed = 'Welcome to Student Attendance Management' if lang == 'en' else 'مرحباً بكم في إدارة دوام الطلبة'
                return {'text': _default_feed, 'feeds': [_default_feed],
                        'fg': '#1e293b', 'font': 'Tahoma', 'size': 15, 'speed': 35,
                        'bg': 'transparent', 'logo_url': '', 'logo_size': 28, 'logo_pulse': True,
                        'logo_pulse_speed': 6, 'sep_img_url': '', 'mask_fade': 12,
                        'interview_mode': 'scroll'}
        def get_sas_config():
            """Get SAS config object for templates"""
            try:
                from models.database import SASConfig
                db = g.get('db')
                return db.query(SASConfig).first() if db else None
            except Exception as e:
                current_app.logger.warning(f"{__name__} error: {e}")
                return None
        # SAS calls wrapped separately so failures never break the main ticker
        try:
            _sas_ticker = get_sas_ticker_cfg()
        except Exception:
            _lang = session.get('lang', 'ar')
            _default_sas_feed = 'Welcome to Student Attendance Management' if _lang == 'en' else 'مرحباً بكم في إدارة دوام الطلبة'
            _sas_ticker = {'text': _default_sas_feed, 'feeds': [_default_sas_feed],
                           'fg': '#1e293b', 'font': 'Tahoma',
                           'size': 15, 'speed': 35, 'bg': 'transparent', 'logo_url': '',
                           'logo_size': 28, 'logo_pulse': True, 'logo_pulse_speed': 6,
                           'sep_img_url': '', 'mask_fade': 12, 'interview_mode': 'scroll'}
        try:
            _sas_cfg = get_sas_config()
        except Exception:
            _sas_cfg = None
        return {
            'app_name': 'STAP — نظام الحضور والمقابلات',
            '_': t,
            'current_lang': get_lang(),
            'current_user': current_user,
            'perms': get_permissions(),
            'get_maintenance_config': get_maintenance_config,
            'ticker_bg_style': get_ticker_bg(),
            'ticker_cfg': get_ticker_cfg(),
            'auth_ticker_cfg': get_auth_ticker_cfg(),
            'interview_ticker_cfg': get_interview_ticker_cfg(),
            'sas_ticker_cfg': _sas_ticker,
            'sas_cfg': _sas_cfg,
            'system_colors': get_system_colors(),
            'cp_enabled': cp_enabled,
        }

    # ── Language toggle route ─────────────────────────────────────────────
    @app.route('/set-lang/<lang>')
    def set_language(lang):
        from utils.i18n import set_lang
        from flask import redirect, request as req, url_for
        # Only allow valid language codes
        if lang not in ('ar', 'en'):
            lang = 'ar'
        set_lang(lang)
        from urllib.parse import urlparse
        # Priority: ?next= param
        next_url = req.args.get('next', '')
        if next_url:
            parsed = urlparse(next_url)
            if not parsed.netloc or parsed.netloc == req.host:
                return redirect(next_url)
        # Fallback: referrer
        referrer = req.referrer or '/'
        parsed = urlparse(referrer)
        if parsed.netloc and parsed.netloc != req.host:
            referrer = '/'
        return redirect(referrer)

    @app.before_request
    def set_default_lang():
        from flask import session
        if 'lang' not in session:
            session['lang'] = 'ar'

    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        return response

    @app.after_request
    def htmx_partial_response(response):
        from flask import request as req
        if not req.headers.get('HX-Request'):
            return response
        if not response.content_type or 'text/html' not in response.content_type:
            return response
        if response.status_code != 200:
            return response
        try:
            full_html = response.get_data(as_text=True)
            # Extract ONLY the inner content of #contentArea
            start_tag = 'id="contentArea"'
            end_tag   = '</div><!-- /content-area -->'
            s = full_html.find(start_tag)
            e = full_html.find(end_tag)
            if s != -1 and e != -1:
                # Skip past the opening div tag
                inner_start = full_html.index('>', s) + 1
                content = full_html[inner_start:e].strip()
                response.set_data(content)
                response.headers['HX-Push-Url'] = req.path
                # Update page title
                title_start = full_html.find('<title>')
                title_end   = full_html.find('</title>')
                if title_start != -1 and title_end != -1:
                    title = full_html[title_start+7:title_end]
                    title_safe = title.replace('"', '\\"').replace('\r','').replace('\n','')
                    response.headers['HX-Trigger'] = '{"updateTitle": "' + title_safe + '"}'
        except Exception:
            pass
        return response

    # ── Health check endpoint — for Render deployment ─────────────────────────
    @app.route('/health')
    def health_check():
        from flask import jsonify
        return jsonify({'status': 'ok', 'app': 'STAP'}), 200

    return app


try:
    app = create_app()
    print('✅ STAP App ready')
except Exception as e:
    import traceback; traceback.print_exc(); raise

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port,
            debug=os.environ.get('FLASK_ENV','production') == 'development')