import os
os.environ['ADMIN_PASSWORD'] = 'admin'  # predictable password for tests

import pytest
import tempfile
import re
from app import create_app, db
from app.models import Admin, Activity, Project, ActivityProject, Participant, Recorder, Result, QRCode, ActivityRecorder


@pytest.fixture
def app():
    """Create app with in-memory SQLite for testing."""
    app = create_app('config.TestConfig')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    """Test client."""
    return app.test_client()


@pytest.fixture
def ctx(app):
    """Provide an active application context for model operations."""
    with app.app_context():
        yield


@pytest.fixture
def auth_client(client):
    """Authenticated test client with CSRF token management."""
    # First GET sets CSRF token in session
    login_page = client.get('/login')
    # Extract CSRF token from session or form
    import secrets
    with client.session_transaction() as sess:
        csrf_token = sess.get('_csrf_token', '')
    # Login
    client.post('/login', data={
        'username': 'admin',
        'password': 'admin',
        '_csrf_token': csrf_token
    }, follow_redirects=True)
    return client


@pytest.fixture
def sample_project(app, ctx):
    """Create a sample project."""
    p = Project(name='测试项目', penalty_per_violation=5.0)
    db.session.add(p)
    db.session.commit()
    db.session.refresh(p)
    return p


@pytest.fixture
def sample_activity(app, ctx, sample_project):
    """Create a sample activity with a project."""
    from app.models import ActivityType
    stu_type = ActivityType.query.filter_by(name='学生').first()
    if not stu_type:
        stu_type = ActivityType(name='学生', sort_order=0)
        db.session.add(stu_type)
        db.session.flush()
    a = Activity(name='测试活动', activity_type_id=stu_type.id)
    db.session.add(a)
    db.session.flush()
    ap = ActivityProject(activity_id=a.id, project_id=sample_project.id)
    db.session.add(ap)
    db.session.commit()
    db.session.refresh(a)
    return a


@pytest.fixture
def sample_recorder(app, ctx):
    """Create a sample global recorder."""
    r = Recorder(name='录入员A', record_key='0001')
    db.session.add(r)
    db.session.commit()
    db.session.refresh(r)
    return r


@pytest.fixture
def sample_activity_recorder(app, ctx, sample_activity, sample_recorder, sample_project):
    """Assign sample recorder to sample activity with project permissions."""
    ar = ActivityRecorder(activity_id=sample_activity.id, recorder_id=sample_recorder.id, project_ids=str(sample_project.id))
    db.session.add(ar)
    db.session.commit()
    db.session.refresh(ar)
    return ar
