import secrets
import os
from dataclasses import dataclass
from functools import wraps
from flask import abort, session, request, g, redirect, url_for
from . import db
from werkzeug.utils import secure_filename
from .models import Admin, ActivityProject, Project, Tenant


def log_action(action, detail=None, recorder_id=None, participant_id=None, activity_id=None):
    """记录系统操作日志"""
    from app.models import SystemLog
    from datetime import datetime, timezone
    tenant_id = current_tenant_id()
    if tenant_id is None and activity_id:
        from app.models import Activity
        activity = db.session.get(Activity, activity_id)
        tenant_id = activity.tenant_id if activity else None
    log = SystemLog(action=action, detail=detail,
                    tenant_id=tenant_id,
                    recorder_id=recorder_id, participant_id=participant_id,
                    activity_id=activity_id,
                    created_at=datetime.now(timezone.utc))
    if tenant_id is None:
        log._allow_null_tenant = True
    db.session.add(log)
    db.session.commit()



def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_admin():
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def tenant_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = get_current_admin()
        if not admin:
            return redirect(url_for('auth.login'))
        if not get_current_tenant():
            return redirect(url_for('admin.platform_tenants'))
        return f(*args, **kwargs)
    return decorated


def platform_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = get_current_admin()
        if not admin:
            return redirect(url_for('auth.login'))
        if not admin.is_platform_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def get_current_admin():
    if session.get('admin_id'):
        return db.session.get(Admin, session['admin_id'])
    return None


def get_admin():
    return get_current_admin()


def get_current_tenant():
    admin = get_current_admin()
    if not admin:
        return None
    if admin.is_platform_admin:
        tenant_id = session.get('active_tenant_id')
        tenant = db.session.get(Tenant, tenant_id) if tenant_id else None
        return tenant if tenant and tenant.is_active else None
    return admin.tenant if admin.tenant and admin.tenant.is_active else None


def current_tenant_id():
    tenant = get_current_tenant()
    return tenant.id if tenant else None


def tenant_query(model):
    tenant_id = current_tenant_id()
    if tenant_id is None:
        abort(403)
    return model.query.filter_by(tenant_id=tenant_id)


def tenant_get_or_404(model, ident):
    item = db.session.get(model, ident)
    tenant_id = current_tenant_id()
    if item is None or tenant_id is None or getattr(item, 'tenant_id', None) != tenant_id:
        abort(404)
    return item


def get_or_404(model, ident):
    item = db.session.get(model, ident)
    if item is None:
        abort(404)
    return item


@dataclass
class PaginationResult:
    items: list
    page: int
    total: int
    pages: int


def paginate_query(query, page, per_page):
    page = max(page, 1)
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    pages = (total + per_page - 1) // per_page
    return items, total, pages


def paginate_request_query(query, page_arg, per_page):
    page = request.args.get(page_arg, 1, type=int)
    items, total, pages = paginate_query(query, page, per_page)
    return PaginationResult(items=items, page=max(page, 1),
                            total=total, pages=pages)


def format_time(seconds):
    if seconds is None:
        return '-'
    total_ms = int(round(seconds * 1000))
    minutes = total_ms // 60000
    sec = (total_ms % 60000) // 1000
    ms = total_ms % 1000
    return f"{minutes}:{sec:02d}.{ms:03d}"


def format_score(value):
    """格式化分数显示，舍入到2位小数，消除浮点精度问题"""
    if value is None:
        return '-'
    return f'{round(float(value), 2):g}'


def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']


def validate_csrf():
    from flask import current_app
    if current_app.testing:
        return True
    token = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token', '')
    if not token or token != session.get('_csrf_token'):
        return False
    return True


def csrf_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'POST':
            if not validate_csrf():
                return 'CSRF token无效或已过期', 400
        return f(*args, **kwargs)
    return decorated


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def truncate_str(val, max_len=100):
    if not val:
        return ''
    return str(val)[:max_len]


def save_uploaded_file(file_field, subdir, prefix, obj_id):
    from flask import current_app
    if not file_field or not file_field.filename:
        return None
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], subdir)
    os.makedirs(upload_dir, exist_ok=True)
    fname = f'{prefix}_{obj_id}_{secure_filename(file_field.filename)}'
    file_field.save(os.path.join(upload_dir, fname))
    return os.path.join('uploads', subdir, fname)


def get_activity_projects(activity_id):
    cache_key = f'_proj_cache_{activity_id}'
    if cache_key not in g:
        aps = ActivityProject.query.filter_by(activity_id=activity_id).all()
        query = Project.query.filter(Project.id.in_([ap.project_id for ap in aps])) if aps else None
        tenant_id = current_tenant_id()
        if query is not None and tenant_id is not None:
            query = query.filter_by(tenant_id=tenant_id)
        setattr(g, cache_key, query.all() if query is not None else [])
    return getattr(g, cache_key)
