from flask import Blueprint, flash, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from .. import db, logger
from ..models import Admin
from ..utils import csrf_required, get_or_404, truncate_str

auth_bp = Blueprint('auth', __name__, url_prefix='')


@auth_bp.route('/')
def index():
    return render_template('index.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@csrf_required
def login():
    if request.method == 'POST':
        username = truncate_str(request.form.get('username', ''), 50)
        password = request.form.get('password', '')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session.permanent = True
            session['admin_id'] = admin.id
            logger.info(f'管理员登录: {admin.username}')
            return redirect(url_for('admin.admin'))
        logger.warning(f'登录失败: username={username}')
        return render_template('login.html', error='账号或密码错误')
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.pop('admin_id', None)
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
        admins = Admin.query.all()
        return render_template('admin_account.html', admins=admins, **context)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'change_password':
            old_pw = request.form.get('old_password', '')
            new_pw = request.form.get('new_password', '')
            admin_user = db.session.get(Admin, session['admin_id'])
            if check_password_hash(admin_user.password_hash, old_pw):
                admin_user.password_hash = generate_password_hash(new_pw)
                db.session.commit()
                return render_account(success='密码修改成功')
            return render_account(error='原密码错误')
        elif action == 'create_admin':
            username = truncate_str(request.form.get('username', ''), 50)
            password = request.form.get('password', '')
            if Admin.query.filter_by(username=username).first():
                return render_account(error='用户名已存在')
            db.session.add(Admin(username=username, password_hash=generate_password_hash(password)))
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
    db.session.delete(get_or_404(Admin, admin_id))
    db.session.commit()
    return redirect(url_for('auth.admin_account'))
