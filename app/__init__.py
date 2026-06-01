import os
import secrets
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.utils import import_string

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name='config.Config'):
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    # Load config
    import_path = config_name
    if import_path.startswith('config.'):
        import_path = f'app.{import_path}'
    cfg = import_string(import_path)()
    for key in dir(cfg):
        if key.isupper():
            app.config[key] = getattr(cfg, key)

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Register Jinja2 globals/filters
    from .project_types import get_project_type
    from .utils import get_admin, format_time, format_score, generate_csrf_token
    app.jinja_env.globals['admin'] = get_admin
    app.jinja_env.globals['csrf_token'] = generate_csrf_token
    app.jinja_env.globals['project_type'] = get_project_type
    app.jinja_env.filters['timefmt'] = format_time
    app.jinja_env.filters['scorefmt'] = format_score

    # Ensure upload dirs exist
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'rules'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), exist_ok=True)
    os.makedirs(os.path.join(app.root_path, 'static', 'qrcodes'), exist_ok=True)

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.admin import admin_bp
    from .routes.recorder import recorder_bp
    from .routes.participant import participant_bp
    from .routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(recorder_bp)
    app.register_blueprint(participant_bp)
    app.register_blueprint(api_bp)

    # Upload serving route
    @app.route('/uploads/<path:filename>')
    def serve_upload(filename):
        from flask import send_from_directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # Init DB + default admin + default activity types
    with app.app_context():
        from .models import Admin, ActivityType
        from werkzeug.security import generate_password_hash
        db.create_all()
        if not Admin.query.first():
            default_pw = os.environ.get('ADMIN_PASSWORD', secrets.token_hex(8))
            db.session.add(Admin(username='admin', password_hash=generate_password_hash(default_pw)))
            db.session.commit()
            logger.info(f'默认管理员: admin / {default_pw}')
        # Seed default activity types
        if not ActivityType.query.first():
            for name in ('学生', '教职工'):
                at = ActivityType(name=name, sort_order=0)
                at.set_fields(at.get_default_fields())
                db.session.add(at)
            db.session.commit()
            logger.info('已创建默认活动类型: 学生, 教职工')

    return app
