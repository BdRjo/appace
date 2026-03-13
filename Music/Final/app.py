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

    for bp in [auth_bp, reservations_bp, venues_bp, admin_bp, api_bp,
               locations_bp, venues_mgmt_bp, users_bp, reports_bp,
               contacts_bp, checklists_bp, blocked_bp, ratings_bp,
               calendar_bp, settings_bp]:
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
        from utils.i18n import t, get_lang
        def get_ticker_bg():
            try:
                import json, os
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
        return {
            'app_name': 'ARS — نظام إدارة الحجوزات',
            '_': t,
            'current_lang': get_lang(),
            'current_user': current_user,
            'perms': get_permissions(),
            'get_maintenance_config': get_maintenance_config,
            'ticker_bg_style': get_ticker_bg(),
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
