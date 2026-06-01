"""Tests for database models."""
import pytest
from app import db
from app.models import (
    Admin, Activity, ActivityType, Project, ActivityProject,
    Participant, Recorder, ActivityRecorder, Result, QRCode
)
from werkzeug.security import generate_password_hash


class TestActivityRecorderModel:
    def test_project_id_list_empty(self, ctx, sample_activity, sample_recorder):
        ar = ActivityRecorder(activity_id=sample_activity.id, recorder_id=sample_recorder.id, project_ids='')
        db.session.add(ar)
        db.session.flush()
        assert ar.project_id_list() == []

    def test_project_id_list_single(self, ctx, sample_activity, sample_recorder):
        ar = ActivityRecorder(activity_id=sample_activity.id, recorder_id=sample_recorder.id, project_ids='1')
        db.session.add(ar)
        db.session.flush()
        assert ar.project_id_list() == [1]

    def test_project_id_list_multiple(self, ctx, sample_activity, sample_recorder):
        ar = ActivityRecorder(activity_id=sample_activity.id, recorder_id=sample_recorder.id, project_ids='1,2,3')
        db.session.add(ar)
        db.session.flush()
        assert ar.project_id_list() == [1, 2, 3]

    def test_project_id_list_with_spaces(self, ctx, sample_activity, sample_recorder):
        ar = ActivityRecorder(activity_id=sample_activity.id, recorder_id=sample_recorder.id, project_ids='1, 2, 3')
        db.session.add(ar)
        db.session.flush()
        assert ar.project_id_list() == [1, 2, 3]

    def test_recorder_global(self, ctx):
        """Recorder is now global, no activity_id required."""
        r = Recorder(name='全局录入员', record_key='9999')
        db.session.add(r)
        db.session.commit()
        saved = db.session.get(Recorder, r.id)
        assert saved.name == '全局录入员'
        assert saved.record_key == '9999'


class TestAdminModel:
    def test_create_admin(self, ctx):
        a = Admin(username='testadmin', password_hash=generate_password_hash('test123'))
        db.session.add(a)
        db.session.commit()
        saved = Admin.query.filter_by(username='testadmin').first()
        assert saved is not None
        assert saved.username == 'testadmin'


class TestActivityProjectRelation:
    def test_activity_has_projects(self, ctx, sample_activity, sample_project):
        a = db.session.get(Activity, sample_activity.id)
        assert len(a.activity_projects) == 1
        assert a.activity_projects[0].project_id == sample_project.id

    def test_unique_constraint(self, ctx, sample_activity, sample_project):
        from sqlalchemy.exc import IntegrityError
        dup = ActivityProject(activity_id=sample_activity.id, project_id=sample_project.id)
        db.session.add(dup)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


class TestActivityModel:
    def test_user_type_returns_activity_type_name(self, ctx):
        activity_type = ActivityType(name='亲子组', sort_order=0)
        db.session.add(activity_type)
        db.session.flush()
        activity = Activity(name='亲子活动', activity_type_id=activity_type.id)
        db.session.add(activity)
        db.session.commit()

        saved = db.session.get(Activity, activity.id)
        assert saved.user_type == '亲子组'
        assert saved.user_type_display == '亲子组'
        assert saved.is_student is False

    def test_is_student_detects_student_activity_type(self, ctx):
        activity_type = ActivityType.query.filter_by(name='学生').first()
        activity = Activity(name='学生活动', activity_type_id=activity_type.id)
        db.session.add(activity)
        db.session.commit()

        saved = db.session.get(Activity, activity.id)
        assert saved.user_type == '学生'
        assert saved.is_student is True


class TestParticipantModel:
    def test_create_participant(self, ctx, sample_activity):
        qr = QRCode(code='ABCD', activity_id=sample_activity.id)
        db.session.add(qr)
        db.session.flush()
        p = Participant(name='张三', class_name='一班',
                        activity_id=sample_activity.id, qrcode_id=qr.id)
        db.session.add(p)
        db.session.commit()
        saved = db.session.get(Participant, p.id)
        assert saved.name == '张三'
        assert saved.class_name == '一班'


class TestResultModel:
    def test_create_result(self, ctx, sample_activity, sample_project):
        qr = QRCode(code='EFGH', activity_id=sample_activity.id)
        db.session.add(qr)
        db.session.flush()
        p = Participant(name='李四', activity_id=sample_activity.id, qrcode_id=qr.id)
        db.session.add(p)
        db.session.flush()
        r = Result(participant_id=p.id, project_id=sample_project.id,
                   time_seconds=30.5, violations=2,
                   penalty_time=10.0, final_time=40.5)
        db.session.add(r)
        db.session.commit()
        saved = db.session.get(Result, r.id)
        assert saved.final_time == 40.5

    def test_unique_participant_project(self, ctx, sample_activity, sample_project):
        qr = QRCode(code='IJKL', activity_id=sample_activity.id)
        db.session.add(qr)
        db.session.flush()
        p = Participant(name='王五', activity_id=sample_activity.id, qrcode_id=qr.id)
        db.session.add(p)
        db.session.flush()
        r1 = Result(participant_id=p.id, project_id=sample_project.id,
                    time_seconds=10.0, final_time=10.0)
        db.session.add(r1)
        db.session.commit()
        from sqlalchemy.exc import IntegrityError
        r2 = Result(participant_id=p.id, project_id=sample_project.id,
                    time_seconds=20.0, final_time=20.0)
        db.session.add(r2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
