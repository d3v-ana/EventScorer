"""边界输入输出测试 — 极端值、权限校验、错误处理"""

import json


class TestAuthBoundary:
    """登录 / 权限边界"""

    def test_login_empty_password(self, client):
        """空密码登录"""
        resp = client.post('/login', data={
            'email': 'tenant@example.com', 'password': '',
        }, follow_redirects=True)
        assert '错误' in resp.data.decode('utf-8') or 'login' in resp.request.path

    def test_login_wrong_password(self, client):
        """错误密码"""
        resp = client.post('/login', data={
            'email': 'tenant@example.com', 'password': 'wrongpass',
        }, follow_redirects=True)
        assert '账号或密码错误' in resp.data.decode('utf-8')

    def test_login_nonexistent_user(self, client):
        """不存在的用户"""
        resp = client.post('/login', data={
            'email': 'nobody@example.com', 'password': 'anything',
        }, follow_redirects=True)
        assert '账号或密码错误' in resp.data.decode('utf-8')

    def test_unauthenticated_access_redirect(self, client):
        """未登录访问管理页 → 重定向"""
        resp = client.get('/admin/recorders', follow_redirects=True)
        assert resp.status_code == 200
        assert 'login' in resp.request.path


class TestProjectBoundary:
    """项目管理边界"""

    def test_create_project_duplicate_name(self, auth_client, app):
        """重复项目名称"""
        from app import db
        from app.models import Project
        db.session.add(Project(name='重复项目', type='time'))
        db.session.commit()

        resp = auth_client.post('/admin/project/create', data={
            'name': '重复项目', 'type': 'time',
        }, follow_redirects=True)
        assert '已存在' in resp.data.decode('utf-8')

    def test_create_project_long_name(self, auth_client, app):
        """超长项目名称（截断到100）"""
        resp = auth_client.post('/admin/project/create', data={
            'name': 'A' * 500, 'type': 'time',
        }, follow_redirects=True)
        from app.models import Project
        p = Project.query.order_by(Project.id.desc()).first()
        assert p is not None
        assert len(p.name) == 100

    def test_edit_project_invalid_type(self, auth_client, app):
        """编辑项目时传入非法 type"""
        from app import db
        from app.models import Project
        p = Project(name='测试', type='time')
        db.session.add(p)
        db.session.commit()
        pid = p.id

        resp = auth_client.post(f'/admin/project/{pid}/edit', data={
            'name': '测试修改', 'type': 'invalid_type',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert Project.query.get(pid).type == 'time'

    def test_delete_project_with_results_cascades(self, auth_client, app):
        """删除有成绩的项目 → Result 也被删除"""
        from app import db
        from app.models import (
            Project, Activity, ActivityType, ActivityProject,
            QRCode, Participant, Result, Recorder,
        )
        at = ActivityType.query.filter_by(name='学生').first()
        assert at is not None
        p = Project(name='将被删除', type='time')
        db.session.add(p)
        db.session.flush()
        act = Activity(name='测试活动delet', activity_type_id=at.id)
        db.session.add(act)
        db.session.flush()
        db.session.add(ActivityProject(activity_id=act.id, project_id=p.id))
        qr = QRCode(code='DEL001', activity_id=act.id, status='used')
        db.session.add(qr)
        db.session.flush()
        part = Participant(name='测试', activity_id=act.id, qrcode_id=qr.id)
        db.session.add(part)
        db.session.flush()
        rec = Recorder(name='测试录入员del', record_key='9999')
        db.session.add(rec)
        db.session.flush()
        r = Result(participant_id=part.id, project_id=p.id,
                   final_time=10.0, recorder_id=rec.id)
        db.session.add(r)
        db.session.commit()
        rid = r.id

        resp = auth_client.post(f'/admin/project/{p.id}/delete',
                                follow_redirects=True)
        assert resp.status_code == 200
        assert Project.query.get(p.id) is None
        # Result 应该被路由中的显式删除清除
        assert Result.query.get(rid) is None


class TestRecorderBoundary:
    """录入员管理边界"""

    def test_create_recorder_empty_name(self, auth_client):
        """空名字 → 400"""
        resp = auth_client.post('/admin/recorder/create',
                                data={'name': ''})
        assert resp.status_code == 400

    def test_create_recorder_duplicate_name(self, auth_client, app):
        """重复名字"""
        from app import db
        from app.models import Recorder
        db.session.add(Recorder(name='重复录入员', record_key='1111'))
        db.session.commit()

        resp = auth_client.post('/admin/recorder/create', data={
            'name': '重复录入员',
        }, follow_redirects=True)
        assert '已存在' in resp.data.decode('utf-8')

    def test_recorder_login_wrong_key(self, auth_client, app):
        """KEY 错误"""
        from app import db
        from app.models import Recorder
        db.session.add(Recorder(name='录入员XX', record_key='1234'))
        db.session.commit()

        resp = auth_client.post('/recorder/login', data={
            'name': '录入员XX', 'key': '0000',
        }, follow_redirects=True)
        assert '不匹配' in resp.data.decode('utf-8')

    def test_recorder_login_unauthorized_activity(self, auth_client, app):
        """录入员无权访问未分配的活动"""
        from app import db
        from app.models import Recorder, Activity, ActivityType
        at = ActivityType.query.filter_by(name='学生').first()
        rec = Recorder(name='无权限录入员', record_key='1234')
        db.session.add(rec)
        db.session.flush()
        act = Activity(name='未分配活动', activity_type_id=at.id)
        db.session.add(act)
        db.session.commit()

        with auth_client.session_transaction() as sess:
            sess['recorder_id'] = rec.id
            sess['recorder_key'] = rec.record_key
            sess['activity_id'] = act.id

        resp = auth_client.get(f'/recorder/{rec.id}/scan')
        assert resp.status_code == 403

    def test_edit_recorder_duplicate_key(self, auth_client, app):
        """设置重复 KEY 不生效"""
        from app import db
        from app.models import Recorder
        db.session.add(Recorder(name='A', record_key='1111'))
        db.session.add(Recorder(name='B', record_key='2222'))
        db.session.commit()
        r = Recorder.query.filter_by(name='B').first()

        auth_client.post(f'/admin/recorder/{r.id}/edit', data={
            'name': 'B', 'record_key': '1111',
        }, follow_redirects=True)
        assert Recorder.query.get(r.id).record_key == '2222'


class TestActivityBoundary:
    """活动管理边界"""

    def test_create_activity_duplicate_name(self, auth_client, app):
        """重复活动名称"""
        from app.models import Activity, ActivityType
        at = ActivityType.query.filter_by(name='学生').first()
        # 先创建
        auth_client.post('/admin/activity/create', data={
            'name': '重复活动test', 'activity_type_id': at.id,
        }, follow_redirects=True)

        # 再创建同名
        resp = auth_client.post('/admin/activity/create', data={
            'name': '重复活动test', 'activity_type_id': at.id,
        })
        html = resp.data.decode('utf-8')
        assert '已存在' in html or '错误' in html

    def test_archived_activity_reject_qrcode(self, auth_client, app):
        """已归档活动拒绝生成二维码"""
        from app import db
        from app.models import Activity, ActivityType
        at = ActivityType.query.filter_by(name='学生').first()
        act = Activity(name='归档活动test', activity_type_id=at.id, archived=True)
        db.session.add(act)
        db.session.commit()

        resp = auth_client.post(f'/admin/activity/{act.id}/qrcode/generate',
                                data={'count': 1})
        assert resp.status_code == 403


class TestScoreBoundary:
    """成绩录入边界"""

    def _setup_recorder_activity(self, app, proj_type='time', max_score=None):
        """创建测试数据并设置录入员 session，返回 (client, recorder_id, qrcode, project_id)"""
        from app import db
        from app.models import (
            Activity, ActivityType, Project, ActivityProject,
            QRCode, Participant, Recorder, ActivityRecorder,
        )
        at = ActivityType.query.filter_by(name='学生').first()
        assert at is not None
        p = Project(name=f'边界项目{proj_type}_{id(self)}', type=proj_type,
                    max_score=max_score)
        db.session.add(p)
        db.session.flush()
        act = Activity(name=f'边界活动{id(self)}', activity_type_id=at.id)
        db.session.add(act)
        db.session.flush()
        db.session.add(ActivityProject(activity_id=act.id, project_id=p.id))
        rec = Recorder(name=f'边界录入员{id(self)}', record_key=f'{id(self)%10000:04d}')
        db.session.add(rec)
        db.session.flush()
        db.session.add(
            ActivityRecorder(activity_id=act.id, recorder_id=rec.id,
                             project_ids=str(p.id))
        )
        qr = QRCode(code=f'BD{id(self)%10000:04d}', activity_id=act.id,
                    status='used')
        db.session.add(qr)
        db.session.flush()
        part = Participant(name=f'边界测试人{id(self)}', activity_id=act.id,
                           qrcode_id=qr.id)
        db.session.add(part)
        db.session.commit()

        from flask import Flask
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['recorder_id'] = rec.id
            sess['recorder_key'] = rec.record_key
            sess['activity_id'] = act.id
        return client, rec.id, qr.code, p.id

    def test_submit_zero_time_rejected(self, app):
        """提交 0 用时被拒绝"""
        client, rid, code, projid = self._setup_recorder_activity(app, 'time')
        resp = client.post(f'/recorder/{rid}/input/{code}', data={
            'project_id': projid,
            'time_minutes': 0, 'time_seconds': 0, 'time_ms': 0,
            'violations': 0,
        })
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_submit_zero_score_rejected(self, app):
        """提交 0 分数被拒绝"""
        client, rid, code, projid = self._setup_recorder_activity(app, 'score', 100)
        resp = client.post(f'/recorder/{rid}/input/{code}', data={
            'project_id': projid, 'score': 0,
        })
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_submit_score_exceeds_max(self, app):
        """提交超满分数的成绩被拒绝"""
        client, rid, code, projid = self._setup_recorder_activity(app, 'score', 100)
        resp = client.post(f'/recorder/{rid}/input/{code}', data={
            'project_id': projid, 'score': 101,
        })
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_recorder_no_project_permission(self, app):
        """录入员无权录入某个项目"""
        from app import db
        from app.models import (
            Activity, ActivityType, Project, ActivityProject,
            QRCode, Participant, Recorder, ActivityRecorder,
        )
        at = ActivityType.query.filter_by(name='学生').first()
        p1 = Project(name=f'可录入{id(self)}', type='time')
        p2 = Project(name=f'不可录入{id(self)}', type='time')
        db.session.add(p1)
        db.session.add(p2)
        db.session.flush()
        act = Activity(name=f'权限测试{id(self)}', activity_type_id=at.id)
        db.session.add(act)
        db.session.flush()
        db.session.add(ActivityProject(activity_id=act.id, project_id=p1.id))
        db.session.add(ActivityProject(activity_id=act.id, project_id=p2.id))
        rec = Recorder(name=f'权限录入员{id(self)}', record_key=f'{id(self)%10000:04d}')
        db.session.add(rec)
        db.session.flush()
        # 只分配 p1
        db.session.add(ActivityRecorder(
            activity_id=act.id, recorder_id=rec.id, project_ids=str(p1.id)))
        qr = QRCode(code=f'PERM{id(self)%10000:04d}', activity_id=act.id, status='used')
        db.session.add(qr)
        db.session.flush()
        part = Participant(name=f'权限测试人{id(self)}', activity_id=act.id, qrcode_id=qr.id)
        db.session.add(part)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['recorder_id'] = rec.id
            sess['recorder_key'] = rec.record_key
            sess['activity_id'] = act.id

        # 尝试录入 p2（无权限）
        resp = client.post(f'/recorder/{rec.id}/input/{qr.code}', data={
            'project_id': p2.id,
            'time_minutes': 1, 'time_seconds': 0, 'time_ms': 0,
            'violations': 0,
        })
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_submit_for_wrong_activity_participant(self, app):
        """录入不同活动的参与者 → 403"""
        from app import db
        from app.models import (
            Activity, ActivityType, Project, ActivityProject,
            QRCode, Participant, Recorder, ActivityRecorder,
        )
        at = ActivityType.query.filter_by(name='学生').first()
        p = Project(name=f'通用项目{id(self)}', type='time')
        db.session.add(p)
        db.session.flush()
        act1 = Activity(name=f'活动A{id(self)}', activity_type_id=at.id)
        act2 = Activity(name=f'活动B{id(self)}', activity_type_id=at.id)
        db.session.add(act1)
        db.session.add(act2)
        db.session.flush()
        db.session.add(ActivityProject(activity_id=act1.id, project_id=p.id))
        db.session.add(ActivityProject(activity_id=act2.id, project_id=p.id))
        rec = Recorder(name=f'跨活动录入员{id(self)}', record_key=f'{id(self)%10000:04d}')
        db.session.add(rec)
        db.session.flush()
        db.session.add(ActivityRecorder(
            activity_id=act1.id, recorder_id=rec.id, project_ids=str(p.id)))
        qr = QRCode(code=f'WRG{id(self)%10000:04d}', activity_id=act2.id, status='used')
        db.session.add(qr)
        db.session.flush()
        part_wrong = Participant(name=f'活动B的人{id(self)}', activity_id=act2.id, qrcode_id=qr.id)
        db.session.add(part_wrong)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['recorder_id'] = rec.id
            sess['recorder_key'] = rec.record_key
            sess['activity_id'] = act1.id

        resp = client.post(f'/recorder/{rec.id}/input/{qr.code}', data={
            'project_id': p.id,
            'time_minutes': 1, 'time_seconds': 0, 'time_ms': 0,
            'violations': 0,
        })
        assert resp.status_code == 403


class TestApiBoundary:
    """API 边界"""

    def test_api_by_code_invalid(self, app):
        """无效 code 查询参与者"""
        from app import db
        from app.models import Recorder, Activity, ActivityType, ActivityRecorder, Project, ActivityProject
        at = ActivityType.query.filter_by(name='学生').first()
        p = Project(name=f'API项目{id(self)}', type='time')
        db.session.add(p)
        db.session.flush()
        act = Activity(name=f'API测试{id(self)}', activity_type_id=at.id)
        db.session.add(act)
        db.session.flush()
        db.session.add(ActivityProject(activity_id=act.id, project_id=p.id))
        rec = Recorder(name=f'API录入员{id(self)}', record_key=f'{id(self)%10000:04d}')
        db.session.add(rec)
        db.session.flush()
        db.session.add(ActivityRecorder(
            activity_id=act.id, recorder_id=rec.id, project_ids=str(p.id)))
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['recorder_id'] = rec.id
            sess['recorder_key'] = rec.record_key
            sess['activity_id'] = act.id

        resp = client.get('/api/participant/by_code?code=NONEXIST')
        data = json.loads(resp.data)
        assert data['success'] is False

    def test_api_without_auth(self, client, app):
        """未授权访问 API"""
        resp = client.get('/api/participant/by_code?code=TEST')
        data = json.loads(resp.data)
        assert data['success'] is False


class TestRegistrationBoundary:
    """注册边界"""

    def test_register_used_qr(self, auth_client, app):
        """二维码已使用"""
        from app import db
        from app.models import QRCode, Activity, ActivityType, Participant
        at = ActivityType.query.filter_by(name='学生').first()
        act = Activity(name=f'重复注册{id(self)}', activity_type_id=at.id)
        db.session.add(act)
        db.session.flush()
        qr = QRCode(code=f'REG{id(self)%10000:04d}', activity_id=act.id, status='used')
        db.session.add(qr)
        db.session.flush()
        Participant(name='已注册的人', activity_id=act.id, qrcode_id=qr.id)
        db.session.commit()

        resp = auth_client.get(f'/register/{qr.code}')
        html = resp.data.decode('utf-8')
        assert '已被使用' in html or '已注册' in html

    def test_register_invalid_qr_id(self, auth_client):
        """无效二维码 ID → 404"""
        resp = auth_client.get('/register/99999')
        assert resp.status_code == 404


class TestRecorderSessionBoundary:
    """录入员会话边界"""

    def test_recorder_logout_clears_session(self, auth_client, app):
        """退出登录清除 session"""
        from app import db
        from app.models import Recorder
        rec = Recorder(name='session测试', record_key='1111')
        db.session.add(rec)
        db.session.commit()

        with auth_client.session_transaction() as sess:
            sess['recorder_id'] = rec.id
            sess['recorder_key'] = rec.record_key
            sess['activity_id'] = 1

        resp = auth_client.get('/recorder/logout', follow_redirects=True)
        assert resp.status_code == 200

        with auth_client.session_transaction() as sess:
            assert sess.get('recorder_id') is None
            assert sess.get('recorder_key') is None
            assert sess.get('activity_id') is None
