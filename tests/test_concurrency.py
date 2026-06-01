"""高并发测试 — 多线程并发成绩录入（模型层直接调用）

注意：SQLite 不支持真正的并行写入（Serialized 模式），
所以并发测试侧重于验证业务逻辑层面的竞态条件而不是原始写入性能。
"""

import concurrent.futures
import time
from app import db
from app.project_types import get_project_type
from sqlalchemy.exc import IntegrityError


class TestConcurrentModelLevel:
    """模型层并发测试 — 验证 upsert 的原子性和唯一约束"""

    def test_concurrent_upsert_same_participant(self, app):
        """并发 upsert 同一参与者同一项目 → 最终只有一条记录
        验证 save_result 的读-改-写模式是否有竞态缺陷
        """
        from app.models import (
            Activity, ActivityType, Project, ActivityProject, Result,
            QRCode, Participant, Recorder, ActivityRecorder,
        )

        with app.app_context():
            at = ActivityType.query.filter_by(name='学生').first()
            p = Project(name='并发项目', type='time', penalty_per_violation=5.0)
            db.session.add(p)
            db.session.flush()
            act = Activity(name='并发活动', activity_type_id=at.id)
            db.session.add(act)
            db.session.flush()
            db.session.add(ActivityProject(activity_id=act.id, project_id=p.id))
            rec = Recorder(name='并发录入员', record_key='0001')
            db.session.add(rec)
            db.session.flush()
            db.session.add(ActivityRecorder(
                activity_id=act.id, recorder_id=rec.id, project_ids=str(p.id)))
            qr = QRCode(code='CONC001', activity_id=act.id, status='used')
            db.session.add(qr)
            db.session.flush()
            part = Participant(name='并发参与者', activity_id=act.id, qrcode_id=qr.id)
            db.session.add(part)
            db.session.commit()
            pid, projid, rid = part.id, p.id, rec.id

        n_threads = 15
        errors = []

        def save(idx):
            try:
                with app.app_context():
                    project = db.session.get(Project, projid)
                    ptype = get_project_type(project.type)
                    form = {
                        'time_minutes': '0',
                        'time_seconds': str(10 + (idx % 10)),
                        'time_ms': '0',
                        'violations': str(idx % 5),
                    }
                    result = ptype.save_result(
                        participant_id=pid, project=project,
                        recorder_id=rid, form=form,
                    )
                    db.session.commit()
                    return result
            except Exception as e:
                errors.append(f'T{idx}: {type(e).__name__}: {e}')
                db.session.rollback()
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as ex:
            futures = [ex.submit(save, i) for i in range(n_threads)]
            concurrent.futures.wait(futures)

        with app.app_context():
            results = Result.query.filter_by(
                participant_id=pid, project_id=projid
            ).all()
            assert len(results) == 1, (
                f'Race condition! Expected 1 result, got {len(results)}. '
                'save_result upsert logic allows duplicates under concurrency.'
            )

    def test_concurrent_multiple_participants(self, app):
        """并发为多个不同参与者录入 — SQLite 限制测试
        SQLite 不擅长并发写入，此测试验证:
        1) 没有 IntegrityError
        2) 至少部分写入成功（在 MySQL 下全部成功）
        生产环境使用 MySQL 时并发能力更强
        """
        from app.models import (
            Activity, ActivityType, Project, ActivityProject, Result,
            QRCode, Participant, Recorder, ActivityRecorder,
        )
        n = 10
        with app.app_context():
            at = ActivityType.query.filter_by(name='学生').first()
            p = Project(name='多人并发项目', type='time', penalty_per_violation=5.0)
            db.session.add(p)
            db.session.flush()
            act = Activity(name='多人并发活动', activity_type_id=at.id)
            db.session.add(act)
            db.session.flush()
            db.session.add(ActivityProject(activity_id=act.id, project_id=p.id))
            rec = Recorder(name='多人并发录入员', record_key='0002')
            db.session.add(rec)
            db.session.flush()
            db.session.add(ActivityRecorder(
                activity_id=act.id, recorder_id=rec.id, project_ids=str(p.id)))
            participant_ids = []
            for i in range(n):
                qr = QRCode(code=f'MC{i:04d}', activity_id=act.id, status='used')
                db.session.add(qr)
                db.session.flush()
                part = Participant(name=f'参与者{i}', activity_id=act.id, qrcode_id=qr.id)
                db.session.add(part)
                db.session.flush()
                participant_ids.append(part.id)
            proj_id = p.id
            rec_id = rec.id
            db.session.commit()

        errors = []

        def save_for(pid, idx):
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with app.app_context():
                        project = db.session.get(Project, proj_id)
                        ptype = get_project_type(project.type)
                        form = {
                            'time_minutes': '0',
                            'time_seconds': str(15 + (idx % 10)),
                            'time_ms': str(idx * 50),
                            'violations': str(idx % 4),
                        }
                        result = ptype.save_result(
                            participant_id=pid, project=project,
                            recorder_id=rec_id, form=form,
                        )
                        db.session.commit()
                        return result
                except Exception as e:
                    db.session.rollback()
                    if attempt == max_retries - 1:
                        errors.append(f'P{pid}: {type(e).__name__}: {e}')
                    time.sleep(0.05)
                    continue
                break
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(save_for, pid, i)
                       for i, pid in enumerate(participant_ids)]
            concurrent.futures.wait(futures)

        with app.app_context():
            # SQLite 限制：部分写入可能因 InterfaceError 失败
            # 验证没有 IntegrityError
            ie_errors = [e for e in errors if 'IntegrityError' in e]
            assert len(ie_errors) == 0, f'IntegrityError: {ie_errors[:3]}'
            all_results = Result.query.filter_by(project_id=proj_id).all()
            # 至少有一部分写入成功
            assert len(all_results) > 0, f'All {n} writes failed under SQLite'
            # 且每个参与者最多 1 条记录（无重复）
            from collections import Counter
            pids = [r.participant_id for r in all_results]
            dupes = [pid for pid, cnt in Counter(pids).items() if cnt > 1]
            assert len(dupes) == 0, f'Duplicate results for participants: {dupes}'

    def test_concurrent_unique_constraint(self, app):
        """验证 UniqueConstraint 能阻止重复 INSERT
        多线程直接插入 Result（绕过 save_result 的 upsert），
        验证唯一约束能兜底
        """
        from app.models import (
            Activity, ActivityType, Project, ActivityProject, Result,
            QRCode, Participant, Recorder, ActivityRecorder,
        )

        with app.app_context():
            at = ActivityType.query.filter_by(name='学生').first()
            p = Project(name='唯一约束测试', type='time')
            db.session.add(p)
            db.session.flush()
            act = Activity(name='唯一约束活动', activity_type_id=at.id)
            db.session.add(act)
            db.session.flush()
            db.session.add(ActivityProject(activity_id=act.id, project_id=p.id))
            rec = Recorder(name='唯一约束录入员', record_key='0003')
            db.session.add(rec)
            db.session.flush()
            db.session.add(ActivityRecorder(
                activity_id=act.id, recorder_id=rec.id, project_ids=str(p.id)))
            qr = QRCode(code='UNIQ001', activity_id=act.id, status='used')
            db.session.add(qr)
            db.session.flush()
            part = Participant(name='唯一约束人', activity_id=act.id, qrcode_id=qr.id)
            db.session.add(part)
            db.session.commit()
            pid, projid, rid = part.id, p.id, rec.id

        n_threads = 20
        errors = []

        def attempt_insert(idx):
            try:
                with app.app_context():
                    r = Result(
                        participant_id=pid,
                        project_id=projid,
                        final_time=20.0 + idx,
                        recorder_id=rid,
                    )
                    db.session.add(r)
                    db.session.commit()
            except IntegrityError:
                db.session.rollback()
            except Exception as e:
                errors.append(f'T{idx}: {type(e).__name__}: {e}')
                db.session.rollback()

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as ex:
            futures = [ex.submit(attempt_insert, i) for i in range(n_threads)]
            concurrent.futures.wait(futures)

        with app.app_context():
            # 唯一约束确保最多 1 条记录
            actual = Result.query.filter_by(
                participant_id=pid, project_id=projid
            ).count()
            assert actual <= 1, (
                f'UniqueConstraint failed: {actual} records found (expected ≤1)'
            )
