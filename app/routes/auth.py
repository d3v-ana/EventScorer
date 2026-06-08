from flask import Blueprint, flash, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from .. import db, logger
from ..models import Admin
from ..security import hash_password
from ..utils import csrf_required, get_current_admin, get_or_404, current_tenant_id, truncate_str

auth_bp = Blueprint('auth', __name__, url_prefix='')


@auth_bp.route('/')
def index():
    return render_template('index.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@csrf_required
def login():
    if request.method == 'POST':
        email = truncate_str(request.form.get('email') or request.form.get('username', ''), 120).lower()
        password = request.form.get('password', '')
        admin = Admin.query.filter_by(email=email).first()
        if admin and check_password_hash(admin.password_hash, password):
            if admin.is_tenant_admin and (not admin.tenant or not admin.tenant.is_active):
                return render_template('login.html', error='所属学校/单位已停用')
            session.permanent = True
            session['admin_id'] = admin.id
            session.pop('active_tenant_id', None)
            logger.info(f'管理员登录: {admin.email}')
            if admin.is_platform_admin:
                return redirect(url_for('admin.platform_tenants'))
            return redirect(url_for('admin.admin'))
        logger.warning(f'登录失败: email={email}')
        return render_template('login.html', error='账号或密码错误')
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.pop('admin_id', None)
    session.pop('active_tenant_id', None)
    return redirect(url_for('auth.index'))


@auth_bp.route('/admin/account', methods=['GET', 'POST'])
@csrf_required
def admin_account():
    from ..utils import admin_required
    admin_required_wrapped = admin_required(lambda: None)
    # Manual check since decorator on class-based would need wrapping
    if not session.get('admin_id'):
        return redirect(url_for('auth.login'))

    def render_account(**context):
        admin_user = get_current_admin()
        query = Admin.query
        tenant_id = current_tenant_id()
        if admin_user and admin_user.is_tenant_admin:
            query = query.filter_by(tenant_id=admin_user.tenant_id, role='tenant_admin')
        elif tenant_id:
            query = query.filter_by(tenant_id=tenant_id, role='tenant_admin')
        admins = query.order_by(Admin.created_at.desc()).all()
        return render_template('admin_account.html', admins=admins, **context)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'change_password':
            old_pw = request.form.get('old_password', '')
            new_pw = request.form.get('new_password', '')
            admin_user = db.session.get(Admin, session['admin_id'])
            if check_password_hash(admin_user.password_hash, old_pw):
                admin_user.password_hash = hash_password(new_pw)
                db.session.commit()
                return render_account(success='密码修改成功')
            return render_account(error='原密码错误')
        elif action == 'create_admin':
            email = truncate_str(request.form.get('email') or request.form.get('username', ''), 120).lower()
            username = truncate_str(request.form.get('username', '') or email, 50)
            password = request.form.get('password', '')
            tenant_id = current_tenant_id()
            if not tenant_id:
                return render_account(error='请先进入一个学校/单位后再创建租户管理员')
            if Admin.query.filter_by(email=email).first():
                return render_account(error='邮箱已存在')
            db.session.add(Admin(email=email, username=username,
                                 role='tenant_admin', tenant_id=tenant_id,
                                 password_hash=hash_password(password)))
            db.session.commit()
            flash('\u7ba1\u7406\u5458\u521b\u5efa\u6210\u529f', 'success')
            return redirect(url_for('auth.admin_account'))
    return render_account()


@auth_bp.route('/admin/account/<int:admin_id>/delete', methods=['POST'])
@csrf_required
def delete_admin(admin_id):
    if not session.get('admin_id'):
        return redirect(url_for('auth.login'))
    if admin_id == session['admin_id']:
        return '不能删除自己', 400
    current = get_current_admin()
    target = get_or_404(Admin, admin_id)
    tenant_id = current_tenant_id()
    if current.is_tenant_admin and target.tenant_id != current.tenant_id:
        return '权限不足', 403
    if current.is_platform_admin and tenant_id and target.tenant_id != tenant_id:
        return '权限不足', 403
    if target.is_platform_admin:
        return '不能在这里删除平台管理员', 400
    db.session.delete(target)
    db.session.commit()
    return redirect(url_for('auth.admin_account'))
