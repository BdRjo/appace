"""ARS Applied Reservation System — Web v4"""
import os
from flask import Flask, g
from flask_login import LoginManager
from models.database import get_engine, User, seed_database
from sqlalchemy.orm import sessionmaker, joinedload

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY','ars-dev-secret-2026')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    app.config['SESSION_PERMANENT'] = False
    app.config['REMEMBER_COOKIE_DURATION'] = __import__('datetime').timedelta(days=1)

    engine  = get_engine()
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    app.config['DB_SESSION_FACTORY'] = Session

    try:
        s = Session(); seed_database(s); s.close()
    except Exception as e:
        print(f'⚠️ Seed: {e}')

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
    from routes.reservations  import reservations_bp
    from routes.venues        import venues_bp
    from routes.admin         import admin_bp
    from routes.api           import api_bp
    from routes.locations     import locations_bp, venues_mgmt_bp
    from routes.users         import users_bp
    from routes.reports       import reports_bp
    from routes.contacts      import contacts_bp
    from routes.checklists    import checklists_bp
    from routes.blocked       import blocked_bp
    from routes.ratings       import ratings_bp
    from routes.calendar_view import calendar_bp
    from routes.settings      import settings_bp
    from routes.cp            import cp_bp
    from routes.backoffice    import bo_bp
    from routes.groups        import groups_bp

    for bp in [auth_bp, reservations_bp, venues_bp, admin_bp, api_bp,
               locations_bp, venues_mgmt_bp, users_bp, reports_bp,
               contacts_bp, checklists_bp, blocked_bp, ratings_bp,
               calendar_bp, settings_bp, cp_bp, bo_bp, groups_bp]:
        app.register_blueprint(bp)

    # Jinja filters
    from utils.helpers import status_label, status_class
    app.jinja_env.filters['status_label'] = status_label
    app.jinja_env.filters['status_class'] = status_class

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from utils.helpers import get_permissions
        import json, os
        def get_maintenance_config():
            try:
                p = os.path.join(os.path.dirname(__file__), 'maintenance_config.json')
                return json.loads(open(p).read()) if os.path.exists(p) else {}
            except: return {}
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
                feeds = cfg.get('feeds_en' if lang == 'en' else 'feeds_ar', [])
                text = ' ◆ '.join(feeds) if feeds else (default_en if lang == 'en' else default_ar)
                fg = cfg.get('fg', default_fg)
                font = cfg.get('font', 'Tahoma')
                size = cfg.get('size', 15)
                speed = cfg.get('speed', 35)
                opacity = cfg.get('opacity', 0)
                bg_raw = cfg.get('bg', '')
                if bg_raw and opacity > 0:
                    hex_ = bg_raw.replace('#','')
                    try:
                        r2 = int(hex_[0:2],16); g2 = int(hex_[2:4],16); b2 = int(hex_[4:6],16)
                        bg_css = f'rgba({r2},{g2},{b2},{opacity/100:.2f})'
                    except: bg_css = default_bg
                else: bg_css = default_bg
                return {'text': text, 'fg': fg, 'font': font,
                        'size': size, 'speed': speed, 'bg': bg_css}
            except:
                return {'text': default_ar, 'fg': default_fg,
                        'font': 'Tahoma', 'size': 15, 'speed': 35, 'bg': default_bg}
        def get_ticker_cfg():
            return _build_ticker_cfg(
                os.path.join(os.path.dirname(__file__), 'ticker_config.json'),
                'مرحباً بكم في نظام ARS لإدارة الحجوزات', 'Welcome to ARS Reservation System',
                '#F2C99A', '#28559B')
        def get_auth_ticker_cfg():
            return _build_ticker_cfg(
                os.path.join(os.path.dirname(__file__), 'auth_ticker_config.json'),
                'مرحباً بكم — سجّل دخولك للمتابعة', 'Welcome — Please sign in',
                '#ffffff', '#1a3a6c')
        return {
            'app_name': 'ARS — نظام إدارة الحجوزات',
            '_': t,
            'current_lang': get_lang(),
            'current_user': current_user,
            'perms': get_permissions(),
            'get_maintenance_config': get_maintenance_config,
            'ticker_bg_style': get_ticker_bg(),
            'ticker_cfg': get_ticker_cfg(),
            'auth_ticker_cfg': get_auth_ticker_cfg(),
            'system_colors': get_system_colors(),
            'cp_enabled': cp_enabled,
        }

    # ── Language toggle route ─────────────────────────────────────────────
    @app.route('/set-lang/<lang>')
    def set_language(lang):
        from utils.i18n import set_lang
        from flask import redirect, request as req
        set_lang(lang)
        return redirect(req.referrer or '/')

    @app.before_request
    def set_default_lang():
        from flask import session
        if 'lang' not in session:
            session['lang'] = 'ar'

    return app


try:
    app = create_app()
    print('✅ ARS App ready')
except Exception as e:
    import traceback; traceback.print_exc(); raise

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port,
            debug=os.environ.get('FLASK_ENV','production') == 'development')
