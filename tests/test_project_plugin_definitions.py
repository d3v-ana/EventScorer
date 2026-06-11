import json

from app import db
from app.models import Project, ProjectPluginDefinition, SystemLog, Tenant


def _login_platform(client):
    client.get('/login')
    with client.session_transaction() as sess:
        token = sess.get('_csrf_token', '')
    client.post('/login', data={
        'email': 'admin@example.com',
        'password': 'admin',
        '_csrf_token': token,
    }, follow_redirects=True)


def test_platform_admin_can_create_config_project_plugin(client, app):
    _login_platform(client)

    resp = client.post('/platform/project-plugin/create', data={
        'key': 'distance_high',
        'name': '距离成绩',
        'description': '按距离从高到低排名',
        'enabled': '1',
        'config_schema': json.dumps([
            {'key': 'unit', 'label': '单位', 'type': 'text', 'default': '米'}
        ]),
        'input_schema': json.dumps([
            {'key': 'distance', 'label': '距离', 'component': 'number_input',
             'primary': True, 'min_value': 0}
        ]),
        'result_schema': json.dumps({
            'result_unit': 'score',
            'summary_bucket': 'score',
            'ranking_policy': 'desc',
            'input_component': 'number_input',
            'result_field': 'distance',
            'result_label': '距离',
            'display_format': 'score',
            'export_label': '距离',
        }),
        'ui_slots': json.dumps({'admin_config': '<p>插件提示</p>'}),
        '_csrf_token': 'test',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert '距离成绩' in resp.data.decode('utf-8')
    with app.app_context():
        definition = ProjectPluginDefinition.query.filter_by(
            key='distance_high'
        ).first()
        assert definition is not None
        assert definition.tenant_id is None
        assert definition.version == 1
        assert definition.result_config['result_field'] == 'distance'
        assert SystemLog.query.filter_by(
            action='project_plugin_create',
            tenant_id=None,
        ).first() is not None


def test_config_plugin_key_cannot_override_code_plugin(client):
    _login_platform(client)

    resp = client.post('/platform/project-plugin/create', data={
        'key': 'score',
        'name': '覆盖分数',
        '_csrf_token': 'test',
    }, follow_redirects=True)

    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert '插件 Key 与内置或已有插件冲突' in body


def test_config_plugin_can_drive_project_result_and_ranking(ctx):
    from app.project_types import get_project_type, project_type_choices
    from app.scoring import ranking_sort_key

    tenant = Tenant.query.filter_by(name='测试学校').first()
    definition = ProjectPluginDefinition(
        key='low_points',
        name='低分优先',
        enabled=True,
        source='config',
        config_schema='[]',
        input_schema=json.dumps([
            {'key': 'points', 'label': '扣分', 'component': 'number_input',
             'primary': True, 'min_value': 0}
        ]),
        result_schema=json.dumps({
            'result_unit': 'score',
            'summary_bucket': 'score',
            'ranking_policy': 'asc',
            'input_component': 'number_input',
            'result_field': 'points',
            'result_label': '扣分',
            'display_format': 'score',
            'export_label': '扣分',
        }),
        ui_slots=json.dumps({'user_result': '<span>低分优先</span>'}),
    )
    project = Project(tenant_id=tenant.id, name='扣分项目', type='low_points')
    db.session.add_all([definition, project])
    db.session.flush()

    assert ('low_points', '低分优先') in project_type_choices()
    plugin = get_project_type('low_points')
    result = plugin.save_result(
        participant_id=1,
        project=project,
        recorder_id=2,
        form={'points': '3.5'},
    )
    assert result.final_time == 3.5
    assert plugin.display_value(result.final_time) == '3.5'
    assert plugin.export_headers(project) == ['扣分项目(扣分)']
    assert plugin.ui_slot('user_result') == '<span>低分优先</span>'

    first = {'all_score': True, 'all_asc': True, 'score_total': 3,
             'participant': type('P', (), {'id': 1})()}
    second = {'all_score': True, 'all_asc': True, 'score_total': 7,
              'participant': type('P', (), {'id': 2})()}
    assert sorted([second, first], key=ranking_sort_key)[0] is first
