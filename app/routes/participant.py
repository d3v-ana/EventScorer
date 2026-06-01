from flask import Blueprint, render_template, request, redirect, url_for, session
from sqlalchemy.exc import IntegrityError
from .. import db, logger
from ..models import QRCode, Participant, Activity, Project, Result, Recorder
from ..scoring import summarize_results
from ..utils import csrf_required, truncate_str, get_activity_projects, get_or_404, log_action

participant_bp = Blueprint('participant', __name__)


@participant_bp.route('/register/<code>', methods=['GET', 'POST'])
@csrf_required
def participant_register(code):
    # 先按 code 查找
    qr = QRCode.query.filter_by(code=code).first()
    # 向后兼容：旧二维码编码的是 qr.id，用 id 再查一次
    if not qr and code.isdigit():
        qr = db.session.get(QRCode, int(code))
    if not qr:
        from flask import abort
        abort(404)
    activity = get_or_404(Activity, qr.activity_id)
    if qr.status == 'used':
        participant = Participant.query.filter_by(qrcode_id=qr.id).first()
        if participant:
            recorder_id = session.get('recorder_id')
            if recorder_id:
                recorder = db.session.get(Recorder, recorder_id)
                if recorder and recorder.record_key == session.get('recorder_key'):
                    return redirect(url_for('recorder.recorder_input',
                                            recorder_id=recorder_id,
                                            code=code))
            return redirect(url_for('participant.user_results', code=code))
        return render_template('register.html', activity=activity, qr=qr, error='该二维码已被使用')
    if request.method == 'POST':
        import json
        fields = activity.registration_fields
        name = ''
        class_name = ''
        extra = {}
        for field in fields:
            key = field['key']
            val = truncate_str(request.form.get(key, ''), 200)
            if key == 'name':
                name = val
            elif key == 'class_name':
                class_name = val
            else:
                if val:
                    extra[key] = val
        participant = Participant(
            name=name,
            class_name=class_name,
            activity_id=activity.id,
            qrcode_id=qr.id
        )
        if extra:
            participant.set_extra(extra)
        db.session.add(participant)
        qr.status = 'used'
        try:
            log_action('register', detail=f'name={name}, qr={qr.code}', activity_id=activity.id, participant_id=participant.id)
            db.session.commit()
            logger.info(f'参与者注册: {name} (qr={qr.code}, activity={activity.name})')
            return redirect(url_for('participant.user_results', code=code))
        except IntegrityError:
            db.session.rollback()
            logger.warning(f'重复注册: code={code}')
            return render_template('register.html', activity=activity, qr=qr,
                                   error='该二维码已被其他人注册')
    return render_template('register.html', activity=activity, qr=qr)


@participant_bp.route('/user/results/<code>')
def user_results(code):
    qr = QRCode.query.filter_by(code=code).first()
    if not qr and code.isdigit():
        qr = db.session.get(QRCode, int(code))
    if not qr or not qr.id:
        from flask import abort
        abort(404)
    participant = Participant.query.filter_by(qrcode_id=qr.id).first()
    if not participant:
        abort(404)
    activity = get_or_404(Activity, participant.activity_id)
    projects = get_activity_projects(activity.id)
    results = []
    pid = participant.id
    for project in projects:
        r = Result.query.filter_by(participant_id=pid, project_id=project.id).first()
        results.append({'project': project, 'result': r})
    summary = summarize_results(
        projects,
        [item['result'] for item in results if item['result']]
    )
    return render_template('user_results.html', activity=activity, participant=participant,
                           results=results, total_time=summary['total_time'],
                           time_total=summary['time_total'],
                           score_total=summary['score_total'],
                           all_score=summary['all_score'],
                           registration_fields=activity.registration_fields)
