from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from .. import db, logger
from ..models import Recorder, Participant, Activity, Project, Result, QRCode, ActivityRecorder
from ..project_types import get_project_type, project_type_map
from ..utils import csrf_required, get_activity_projects, get_or_404, safe_float, safe_int, log_action

recorder_bp = Blueprint('recorder', __name__)


def _get_recorder_activity(recorder_id, activity_id):
    """获取录入员在指定活动中的 ActivityRecorder，校验权限"""
    ar = ActivityRecorder.query.filter_by(
        activity_id=activity_id, recorder_id=recorder_id
    ).first()
    if not ar:
        return None
    return ar


def _check_recorder_auth(recorder_id):
    """校验录入员会话"""
    if session.get('recorder_id') != recorder_id:
        return None
    recorder = db.session.get(Recorder, recorder_id)
    if not recorder or recorder.record_key != session.get('recorder_key'):
        return None
    return recorder


@recorder_bp.route('/recorder/login', methods=['GET', 'POST'])
@csrf_required
def recorder_login():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        key = request.form.get('key', '').strip()
        recorder = Recorder.query.filter_by(name=name, record_key=key).first()
        if recorder:
            session.permanent = True
            session['recorder_id'] = recorder.id
            session['recorder_key'] = recorder.record_key
            # 查该录入员的可用活动
            activities = Activity.query.join(ActivityRecorder).filter(
                ActivityRecorder.recorder_id == recorder.id,
                Activity.archived == False
            ).all()
            if len(activities) == 1:
                session['activity_id'] = activities[0].id
                return redirect(url_for('recorder.recorder_scan', recorder_id=recorder.id))
            elif len(activities) > 1:
                return redirect(url_for('recorder.recorder_select_activity', recorder_id=recorder.id))
            else:
                return render_template('recorder_login.html', error='该录入员尚未分配到任何活动')
        return render_template('recorder_login.html', error='姓名或KEY不匹配')
    return render_template('recorder_login.html')


@recorder_bp.route('/recorder/<int:recorder_id>/select-activity')
def recorder_select_activity(recorder_id):
    recorder = _check_recorder_auth(recorder_id)
    if not recorder:
        return '权限不足', 403
    activities = Activity.query.join(ActivityRecorder).filter(
        ActivityRecorder.recorder_id == recorder_id,
        Activity.archived == False
    ).all()
    return render_template('recorder_select_activity.html', recorder=recorder, activities=activities)


@recorder_bp.route('/recorder/<int:recorder_id>/set-activity', methods=['POST'])
@csrf_required
def recorder_set_activity(recorder_id):
    recorder = _check_recorder_auth(recorder_id)
    if not recorder:
        return '权限不足', 403
    activity_id = safe_int(request.form.get('activity_id', 0), 0)
    ar = _get_recorder_activity(recorder_id, activity_id)
    if not ar:
        return '无权访问该活动', 403
    activity = get_or_404(Activity, activity_id)
    if activity.archived:
        return '该活动已归档', 403
    session['activity_id'] = activity_id
    return redirect(url_for('recorder.recorder_scan', recorder_id=recorder_id))


@recorder_bp.route('/recorder/logout')
def recorder_logout():
    session.pop('recorder_id', None)
    session.pop('recorder_key', None)
    session.pop('activity_id', None)
    return redirect(url_for('recorder.recorder_login'))


@recorder_bp.route('/recorder/<int:recorder_id>/scan')
def recorder_scan(recorder_id):
    recorder = _check_recorder_auth(recorder_id)
    if not recorder:
        return '权限不足', 403
    activity_id = session.get('activity_id')
    if not activity_id:
        return redirect(url_for('recorder.recorder_select_activity', recorder_id=recorder_id))
    ar = _get_recorder_activity(recorder_id, activity_id)
    if not ar:
        return '权限不足', 403
    activity = get_or_404(Activity, activity_id)
    if activity.archived:
        return '该活动已归档，无法录入成绩', 403
    projects = get_activity_projects(activity.id)
    allowed_projects = [p for p in projects if p.id in ar.project_id_list()]
    import json
    project_types = {p.id: get_project_type(p.type).input_mode for p in allowed_projects}
    # 词库列表（只传递用户自定义的词）
    words = None
    if activity.custom_words:
        custom = [w.strip() for w in activity.custom_words.split('\n') if w.strip()]
        if custom:
            words = custom
    return render_template('recorder_scan.html', recorder=recorder, activity=activity,
                           allowed_projects=allowed_projects,
                           project_types_json=json.dumps(project_types),
                           words_json=json.dumps(words) if words else '[]')


@recorder_bp.route('/recorder/<int:recorder_id>/input/<code>', methods=['GET', 'POST'])
@csrf_required
def recorder_input(recorder_id, code):
    recorder = _check_recorder_auth(recorder_id)
    if not recorder:
        return '权限不足', 403
    activity_id = session.get('activity_id')
    if not activity_id:
        return redirect(url_for('recorder.recorder_select_activity', recorder_id=recorder_id))
    ar = _get_recorder_activity(recorder_id, activity_id)
    if not ar:
        return '权限不足', 403
    qr = QRCode.query.filter_by(code=code).first()
    if not qr and code.isdigit():
        qr = db.session.get(QRCode, int(code))
    if not qr:
        from flask import abort
        abort(404)
    participant = Participant.query.filter_by(qrcode_id=qr.id).first_or_404()
    if participant.activity_id != activity_id:
        return '权限不足', 403
    activity = get_or_404(Activity, activity_id)
    if activity.archived:
        if request.method == 'POST':
            return jsonify({'success': False, 'error': '该活动已归档，无法录入成绩'})
        return '该活动已归档，无法录入成绩', 403
    all_projects = get_activity_projects(activity.id)
    allowed_projects = [p for p in all_projects if p.id in ar.project_id_list()]
    if request.method == 'POST':
        project_id = safe_int(request.form.get('project_id', 0), 0)
        project = get_or_404(Project, project_id)
        if project.id not in ar.project_id_list():
            return jsonify({'success': False, 'error': '无权录入该项目'})

        project_type = get_project_type(project.type)
        try:
            result = project_type.save_result(
                participant_id=participant.id,
                project=project,
                recorder_id=recorder_id,
                form=request.form,
            )
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)})
        db.session.commit()
        log_action("submit_score", detail=f"project={project.name}, value={result.final_time}", recorder_id=recorder_id, participant_id=participant.id, activity_id=activity_id)
        return jsonify({
            'success': True,
            'final_time': result.final_time,
            'type': project_type.key,
        })
    import json
    project_types = {p.id: get_project_type(p.type).input_mode for p in allowed_projects}
    words = None
    if activity.custom_words:
        custom = [w.strip() for w in activity.custom_words.split('\n') if w.strip()]
        if custom:
            words = custom
    return render_template('recorder_input.html', recorder=recorder, participant=participant,
                           activity=activity, allowed_projects=allowed_projects,
                           project_types_json=json.dumps(project_types),
                           words_json=json.dumps(words) if words else '[]')
