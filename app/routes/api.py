from flask import Blueprint, request, jsonify, session
from .. import db
from ..models import ActivityRecorder, Recorder, QRCode, Participant

api_bp = Blueprint('api', __name__)


def _authorized_activity_id(recorder_id):
    activity_id = session.get('activity_id')
    if not activity_id:
        return None
    if not ActivityRecorder.query.filter_by(
            activity_id=activity_id, recorder_id=recorder_id).first():
        return None
    return activity_id


@api_bp.route('/api/participant/by_code')
def api_participant_by_code():
    code = request.args.get('code', '').strip().upper()
    recorder_id = session.get('recorder_id', 0)
    recorder = db.session.get(Recorder, recorder_id)
    if not recorder or recorder.record_key != session.get('recorder_key'):
        return jsonify({'success': False, 'error': '权限不足'})
    activity_id = _authorized_activity_id(recorder_id)
    if not activity_id:
        return jsonify({'success': False, 'error': '权限不足'})
    qr = QRCode.query.filter_by(code=code, activity_id=activity_id).first()
    if not qr or qr.status != 'used':
        return jsonify({'success': False, 'error': '二维码无效或未注册'})
    participant = Participant.query.filter_by(qrcode_id=qr.id).first()
    if not participant:
        return jsonify({'success': False, 'error': '未找到参与者'})
    return jsonify({'success': True, 'participant_id': participant.id,
                    'participant_name': participant.name, 'class_name': participant.class_name or '',
                    'extra': participant.get_extra(),
                    'qr_code': qr.code})


