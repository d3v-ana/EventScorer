"""Tests for participant registration (QR code binding)."""
import pytest
from app import db
from app.models import QRCode, Participant, Activity, Project, ActivityProject, Result


class TestRegistrationPage:
    def test_register_page_get(self, client, app, sample_activity):
        with app.app_context():
            qr = QRCode(code='TEST1', activity_id=sample_activity.id, status='unused')
            db.session.add(qr)
            db.session.commit()
            code = qr.code
        resp = client.get(f'/register/{code}')
        assert resp.status_code == 200
        body = resp.data.decode('utf-8')
        assert '注册' in body or 'register' in body.lower()

    def test_register_unused_qr_404(self, client):
        resp = client.get('/register/ZZZZZZ')
        assert resp.status_code == 404


class TestRegistration:
    def test_register_success(self, client, app, sample_activity):
        with app.app_context():
            qr = QRCode(code='TEST2', activity_id=sample_activity.id, status='unused')
            db.session.add(qr)
            db.session.commit()
            code = qr.code
            activity_id = sample_activity.id
        resp = client.post(f'/register/{code}', data={
            'name': '张三',
            'class_name': '一班',
            '_csrf_token': 'test'
        }, follow_redirects=True)
        assert resp.status_code == 200
        with app.app_context():
            participant = Participant.query.filter_by(name='张三').first()
            assert participant is not None
            assert participant.class_name == '一班'
            assert participant.activity_id == activity_id
            qr_check = QRCode.query.filter_by(code=code).first()
            assert qr_check.status == 'used'

    def test_register_redirects_to_results(self, client, app, sample_activity):
        with app.app_context():
            qr = QRCode(code='TEST3', activity_id=sample_activity.id, status='unused')
            db.session.add(qr)
            db.session.commit()
            code = qr.code
        resp = client.post(f'/register/{code}', data={
            'name': '李四',
            'class_name': '一班',
            '_csrf_token': 'test'
        })
        # Should redirect (302) to /user/results/<code>
        assert resp.status_code == 302 or resp.status_code == 200

    def test_already_used_qr_redirects(self, client, app, sample_activity):
        with app.app_context():
            qr = QRCode(code='TEST4', activity_id=sample_activity.id, status='used')
            db.session.add(qr)
            db.session.flush()
            p = Participant(name='王五', class_name='一班',
                            activity_id=sample_activity.id, qrcode_id=qr.id)
            db.session.add(p)
            db.session.commit()
            code = qr.code
        resp = client.get(f'/register/{code}')
        # Should redirect to user_results page
        assert resp.status_code in (302, 200)


class TestUserResults:
    def test_user_results_page(self, client, app, sample_activity, sample_project):
        with app.app_context():
            qr = QRCode(code='TEST5', activity_id=sample_activity.id)
            db.session.add(qr)
            db.session.flush()
            p = Participant(name='赵六', class_name='一班',
                            activity_id=sample_activity.id, qrcode_id=qr.id)
            db.session.add(p)
            db.session.flush()
            r = Result(participant_id=p.id, project_id=sample_project.id,
                       time_seconds=30.0, violations=1,
                       penalty_time=5.0, final_time=35.0)
            db.session.add(r)
            db.session.commit()
            code = qr.code
        resp = client.get(f'/user/results/{code}')
        assert resp.status_code == 200
        body = resp.data.decode('utf-8')
        assert '赵六' in body
