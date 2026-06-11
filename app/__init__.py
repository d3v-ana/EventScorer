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
    from .utils import get_admin, get_current_tenant, format_time, format_score, generate_csrf_token
    app.jinja_env.globals['admin'] = get_admin
    app.jinja_env.globals['current_tenant'] = get_current_tenant
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

    def _needs_saas_rebuild():
        inspector = db.inspect(db.engine)
        if not inspector.has_table('admin'):
            return False
        admin_cols = {col['name'] for col in inspector.get_columns('admin')}
        return 'email' not in admin_cols or 'role' not in admin_cols

    def _ensure_project_type_config_column():
        inspector = db.inspect(db.engine)
        if not inspector.has_table('project'):
            return
        project_cols = {col['name'] for col in inspector.get_columns('project')}
        if 'type_config' not in project_cols:
            with db.engine.begin() as conn:
                conn.exec_driver_sql('ALTER TABLE project ADD COLUMN type_config TEXT')

    def _backfill_project_type_config():
        from .models import Project
        from .project_types import get_project_type, set_project_config, sync_legacy_columns
        changed = False
        for project in Project.query.all():
            if project.type_config:
                continue
            plugin = get_project_type(project.type)
            config, _ = plugin.build_config_from_form({
                f'config_{field.key}': getattr(project, field.key, field.default)
                for field in plugin.config_fields
            })
            set_project_config(project, config)
            sync_legacy_columns(project)
            changed = True
        if changed:
            db.session.commit()

    def _seed_platform_templates():
        from .models import ActivityType, Department, ProjectCategory
        if not ActivityType.query.filter_by(is_template=True, tenant_id=None).first():
            for name in ('学生', '教职工'):
                at = ActivityType(name=name, sort_order=0, is_template=True)
                at.set_fields(at.get_default_fields())
                db.session.add(at)
        if not Department.query.filter_by(is_template=True, tenant_id=None).first():
            db.session.add(Department(name='体育部', sort_order=0, is_template=True))
        if not ProjectCategory.query.filter_by(is_template=True, tenant_id=None).first():
            db.session.add(ProjectCategory(name='默认分组', sort_order=0, is_template=True))
        db.session.commit()

    def _seed_test_tenant():
        from .models import Admin, ActivityType, Department, Tenant
        from .security import hash_password
        tenant = Tenant.query.filter_by(name='测试学校').first()
        if not tenant:
            tenant = Tenant(name='测试学校', tenant_type='school')
            db.session.add(tenant)
            db.session.flush()
        if not Admin.query.filter_by(email='tenant@example.com').first():
            db.session.add(Admin(email='tenant@example.com', username='测试管理员',
                                 role='tenant_admin', tenant_id=tenant.id,
                                 password_hash=hash_password('admin')))
        if not ActivityType.query.filter_by(tenant_id=tenant.id).first():
            for name in ('学生', '教职工'):
                at = ActivityType(tenant_id=tenant.id, name=name, sort_order=0)
                at.set_fields(at.get_default_fields())
                db.session.add(at)
        if not Department.query.filter_by(tenant_id=tenant.id, name='体育部').first():
            db.session.add(Department(tenant_id=tenant.id, name='体育部', sort_order=0))
        db.session.commit()

    # Init DB + default platform admin + platform templates
    with app.app_context():
        from .models import Admin
        from .security import hash_password
        if _needs_saas_rebuild():
            logger.warning('检测到旧版单租户数据库结构，将按 SaaS 新结构清空重建')
            db.drop_all()
        db.create_all()
        _ensure_project_type_config_column()
        if not Admin.query.filter_by(role='platform_admin').first():
            default_pw = os.environ.get('ADMIN_PASSWORD', secrets.token_hex(8))
            default_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
            db.session.add(Admin(email=default_email, username='平台管理员',
                                 role='platform_admin',
                                 password_hash=hash_password(default_pw)))
            db.session.commit()
            logger.info(f'默认平台管理员: {default_email} / {default_pw}')
        if app.config.get('TESTING'):
            _seed_test_tenant()
        _seed_platform_templates()
        _backfill_project_type_config()

    return app
