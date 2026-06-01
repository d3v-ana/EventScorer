"""Tests for recorder login and scoring entry (refactored for global recorders)."""
import pytest
import json
from app import db
from app.models import (
    Activity, ActivityProject, Participant, Project, QRCode, Recorder,
    Result, ActivityRecorder
)


class TestRecorderLogin:
    def test_login_page(self, client, sample_activity):
        resp = client.get('/recorder/login')
        assert resp.status_code == 200

    def test_login_no_activity(self, client, app, sample_recorder):
        """Recorder with no activity assignment should see error."""
        resp = client.post('/recorder/login', data={
            'name': '录入员A', 'key': '0001', '_csrf_token': 'test'
        }, follow_redirects=True)
        assert resp.status_code == 200
        body = resp.data.decode('utf-8')
        assert '尚未分配到任何活动' in body

    def test_login_success_with_activity(self, client, app, sample_activity,
                                         sample_recorder, sample_activity_recorder):
        """Login + assigned to 1 activity → redirect to scan."""
        resp = client.post('/recorder/login', data={
            'name': '录入员A', 'key': '0001', '_csrf_token': 'test'
        })
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert sess.get('recorder_id') == sample_recorder.id
            assert sess.get('recorder_key') == '0001'
            assert sess.get('activity_id') == sample_activity.id

    def test_login_wrong_key(self, client, app, sample_activity, sample_recorder):
        resp = client.post('/recorder/login', data={
            'name': '录入员A', 'key': 'wrong', '_csrf_token': 'test'
        }, follow_redirects=True)
        assert resp.status_code == 200
        body = resp.data.decode('utf-8')
        assert '不匹配' in body or 'error' in body.lower()

    def test_login_wrong_name(self, client, app, sample_activity, sample_recorder):
        resp = client.post('/recorder/login', data={
            'name': '不存在', 'key': '0001', '_csrf_token': 'test'
        }, follow_redirects=True)
        assert resp.status_code == 200
        body = resp.data.decode('utf-8')
        assert '不匹配' in body or 'error' in body.lower()


class TestRecorderScan:
    def test_scan_page_accessible(self, client, app, sample_recorder,
                                  sample_activity_recorder, sample_activity):
        """Log in as recorder with activity, then access scan page."""
        client.post('/recorder/login', data={
            'name': '录入员A', 'key': '0001', '_csrf_token': 'test'
        })
        resp = client.get(f'/recorder/{sample_recorder.id}/scan')
        assert resp.status_code == 200

    def test_scan_page_renders_word_select_script_once(
            self, client, app, sample_recorder, sample_activity_recorder,
            sample_activity):
        """The scan page must not run word option initialization twice."""
        with app.app_context():
            sample_activity.custom_words = '\n'.join(['alpha', 'beta', 'gamma'])
            db.session.commit()

        with client.session_transaction() as sess:
            sess['recorder_id'] = sample_recorder.id
            sess['recorder_key'] = sample_recorder.record_key
            sess['activity_id'] = sample_activity.id
        resp = client.get(f'/recorder/{sample_recorder.id}/scan')

        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert html.count('function onWordSelect()') == 1
        assert html.count('var wordsList = ["alpha", "beta", "gamma"];') == 1

    def test_scan_page_no_session(self, client, sample_recorder):
        resp = client.get(f'/recorder/{sample_recorder.id}/scan')
        assert resp.status_code == 403

    def test_scan_page_no_activity_in_session(self, client, app, sample_recorder):
        """Login but no activity_id in session → redirect to activity picker."""
        client.post('/recorder/login', data={
            'name': '录入员A', 'key': '0001', '_csrf_token': 'test'
        })
        resp = client.get(f'/recorder/{sample_recorder.id}/scan')
        assert resp.status_code == 302  # redirect to select-activity

    def test_scan_page_wrong_recorder(self, client, app, sample_activity):
        """Access scan with wrong recorder ID."""
        with app.app_context():
            other = Recorder(name='其他录入员', record_key='9999')
            db.session.add(other)
            db.session.commit()
            other_id = other.id
        client.post('/recorder/login', data={
            'name': '录入员A', 'key': '0001', '_csrf_token': 'test'
        })
        resp = client.get(f'/recorder/{other_id}/scan')
        assert resp.status_code == 403


class TestRecorderInput:
    @pytest.fixture
    def setup(self, app, sample_activity, sample_project, sample_recorder,
              sample_activity_recorder):
        """Create participant + login recorder with activity, return IDs."""
        with app.app_context():
            qr = QRCode(code='INPUT1', activity_id=sample_activity.id)
            db.session.add(qr)
            db.session.flush()
            p = Participant(name='参赛者甲', activity_id=sample_activity.id, qrcode_id=qr.id)
            db.session.add(p)
            db.session.commit()
            code = qr.code
            rid = sample_recorder.id
        client = app.test_client()
        client.application.config['TESTING'] = True
        # Login recorder (will set activity_id in session)
        client.post('/recorder/login', data={
            'name': '录入员A', 'key': '0001', '_csrf_token': 'test'
        })
        return client, code, rid, sample_project.id

    def test_input_get_form(self, setup):
        client, code, rid, proj_id = setup
        resp = client.get(f'/recorder/{rid}/input/{code}')
        assert resp.status_code == 200

    def test_input_time_manual_entry_is_collapsible_like_scan(self, setup):
        client, code, rid, proj_id = setup
        resp = client.get(f'/recorder/{rid}/input/{code}')

        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert '<details style="margin-top:12px;">' in html
        assert '<summary style="cursor:pointer;color:#667eea;font-weight:600;font-size:13px;">' in html
        assert html.index('<summary') < html.index('id="timeInput"')

    def test_input_no_session(self, client, app, sample_recorder, sample_activity):
        with app.app_context():
            qr = QRCode(code='INPUT2', activity_id=sample_activity.id)
            db.session.add(qr)
            db.session.flush()
            p = Participant(name='参赛者乙', activity_id=sample_activity.id, qrcode_id=qr.id)
            db.session.add(p)
            db.session.commit()
            code = qr.code
        resp = client.get(f'/recorder/{sample_recorder.id}/input/{code}')
        assert resp.status_code == 403

    def test_input_score(self, setup):
        """Submit a score and verify it's saved correctly."""
        client, code, rid, proj_id = setup
        resp = client.post(f'/recorder/{rid}/input/{code}', data={
            'project_id': str(proj_id),
            'time_minutes': '1', 'time_seconds': '30', 'time_ms': '500',
            'violations': '2', '_csrf_token': 'test'
        })
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True
        # 1:30.500 + 2 * 5.0 = 90.5 + 10.0 = 100.5
        assert abs(data['final_time'] - 100.5) < 0.01

    def test_input_score_updates_existing(self, setup, app):
        """Submit same project twice, should update not create duplicate."""
        client, code, rid, proj_id = setup
        client.post(f'/recorder/{rid}/input/{code}', data={
            'project_id': str(proj_id),
            'time_minutes': '1', 'time_seconds': '0', 'time_ms': '0',
            'violations': '0', '_csrf_token': 'test'
        })
        client.post(f'/recorder/{rid}/input/{code}', data={
            'project_id': str(proj_id),
            'time_minutes': '2', 'time_seconds': '0', 'time_ms': '0',
            'violations': '1', '_csrf_token': 'test'
        })
        with app.app_context():
            qr = QRCode.query.filter_by(code=code).first()
            results = Result.query.filter_by(participant_id=qr.participant.id, project_id=proj_id).all()
            assert len(results) == 1
            assert abs(results[0].final_time - (120.0 + 5.0)) < 0.01

    def test_input_unauthorized_project(self, setup, app, sample_activity):
        """Recorder can't input for a project they're not assigned to."""
        client, code, rid, proj_id = setup
        with app.app_context():
            from app.models import Project, ActivityProject
            other = Project(name='其他项目', penalty_per_violation=10.0)
            db.session.add(other)
            db.session.flush()
            ap = ActivityProject(activity_id=sample_activity.id, project_id=other.id)
            db.session.add(ap)
            db.session.commit()
            other_id = other.id
        resp = client.post(f'/recorder/{rid}/input/{code}', data={
            'project_id': str(other_id),
            'time_minutes': '1', 'time_seconds': '0', 'time_ms': '0',
            'violations': '0', '_csrf_token': 'test'
        })
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_input_rejects_participant_from_other_activity(
            self, setup, app, sample_project):
        """Recorder activity scope must match the participant activity."""
        client, _code, rid, proj_id = setup
        with app.app_context():
            other_activity = Activity(name='Other Activity')
            db.session.add(other_activity)
            db.session.flush()
            db.session.add(ActivityProject(activity_id=other_activity.id,
                                           project_id=sample_project.id))
            qr = QRCode(code='OTHER-ACTIVITY', activity_id=other_activity.id)
            db.session.add(qr)
            db.session.flush()
            participant = Participant(name='Other Participant',
                                      activity_id=other_activity.id,
                                      qrcode_id=qr.id)
            db.session.add(participant)
            db.session.commit()
            other_code = qr.code
            other_pid = participant.id

        resp = client.post(f'/recorder/{rid}/input/{other_code}', data={
            'project_id': str(proj_id),
            'time_minutes': '0', 'time_seconds': '10', 'time_ms': '0',
            'violations': '0', '_csrf_token': 'test'
        })

        assert resp.status_code == 403
        with app.app_context():
            assert Result.query.filter_by(participant_id=other_pid).count() == 0

    def test_scan_api_rejects_qr_from_other_activity(
            self, setup, app):
        client, _code, _rid, _proj_id = setup
        with app.app_context():
            other_activity = Activity(name='Other API Activity')
            db.session.add(other_activity)
            db.session.flush()
            qr = QRCode(code='OTHER-API', activity_id=other_activity.id,
                        status='used')
            db.session.add(qr)
            db.session.flush()
            participant = Participant(name='Other API Participant',
                                      activity_id=other_activity.id,
                                      qrcode_id=qr.id)
            db.session.add(participant)
            db.session.commit()

        resp = client.get('/api/participant/by_code?code=OTHER-API')
        data = json.loads(resp.data)

        assert data['success'] is False
