from types import SimpleNamespace

from app import db
from app.models import Project, Result


def test_project_type_registry_exposes_time_and_score_metadata():
    from app.project_types import get_project_type, project_type_choices

    time_type = get_project_type('time')
    score_type = get_project_type('score')

    assert time_type.key == 'time'
    assert time_type.label == '时间'
    assert time_type.input_mode == 'time'
    assert score_type.key == 'score'
    assert score_type.label == '分数'
    assert score_type.input_mode == 'score'
    assert ('time', '时间') in project_type_choices()
    assert ('score', '分数') in project_type_choices()


def test_score_project_type_validates_and_saves_result(ctx):
    from app.project_types import get_project_type

    project = Project(name='Score', type='score', max_score=100)
    db.session.add(project)
    db.session.flush()
    form = {'score': '88.5'}

    result = get_project_type(project.type).save_result(
        participant_id=1,
        project=project,
        recorder_id=2,
        form=form,
    )

    assert isinstance(result, Result)
    assert result.time_seconds == 88.5
    assert result.penalty_time == 0
    assert result.final_time == 88.5
    assert result.recorder_id == 2


def test_time_project_type_validates_and_saves_result(ctx):
    from app.project_types import get_project_type

    project = Project(name='Run', type='time', penalty_per_violation=5)
    db.session.add(project)
    db.session.flush()
    form = {
        'time_minutes': '1',
        'time_seconds': '2',
        'time_ms': '300',
        'violations': '2',
    }

    result = get_project_type(project.type).save_result(
        participant_id=1,
        project=project,
        recorder_id=2,
        form=form,
    )

    assert result.time_seconds == 62.3
    assert result.violations == 2
    assert result.penalty_time == 10
    assert result.final_time == 72.3


def test_project_type_contributes_to_summary_and_export_columns():
    from app.project_types import get_project_type

    score_project = SimpleNamespace(name='Score', type='score')
    time_project = SimpleNamespace(name='Run', type='time')
    score_result = SimpleNamespace(final_time=90, time_seconds=90,
                                   violations=0, penalty_time=0)
    time_result = SimpleNamespace(final_time=12.5, time_seconds=10,
                                  violations=1, penalty_time=2.5)

    score_type = get_project_type('score')
    time_type = get_project_type('time')

    assert score_type.summary_bucket == 'score'
    assert time_type.summary_bucket == 'time'
    assert score_type.export_headers(score_project) == ['Score(成绩)']
    assert time_type.export_headers(time_project) == [
        'Run(用时)', 'Run(犯规)', 'Run(罚时)', 'Run(最终)'
    ]
    assert score_type.export_values(score_project, score_result) == [90]
    assert time_type.export_values(time_project, time_result) == [
        '0:10.000', 1, '0:02.500', '0:12.500'
    ]


def test_empty_type_config_falls_back_to_legacy_project_fields(ctx):
    from app.project_types import get_project_config, get_project_type

    score_project = Project(
        name='Legacy Score', type='score', max_score=60, type_config=''
    )
    time_project = Project(
        name='Legacy Time', type='time', penalty_per_violation=3.5,
        type_config=''
    )

    assert get_project_config(score_project)['fields']['max_score'] == 60
    assert get_project_config(time_project)['fields']['penalty_per_violation'] == 3.5
    assert get_project_type('score').config_value(score_project, 'max_score') == 60
    assert get_project_type('time').config_value(
        time_project, 'penalty_per_violation'
    ) == 3.5


def test_build_config_from_form_accepts_legacy_field_names():
    from app.project_types import get_project_type

    score_config, score_errors = get_project_type('score').build_config_from_form({
        'max_score': '75',
    })
    time_config, time_errors = get_project_type('time').build_config_from_form({
        'penalty': '4.5',
    })

    assert score_errors == []
    assert time_errors == []
    assert score_config['fields']['max_score'] == 75
    assert time_config['fields']['penalty_per_violation'] == 4.5
