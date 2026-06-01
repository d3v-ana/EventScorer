from dataclasses import dataclass

from . import db
from .models import Result
from .utils import format_time, safe_float, safe_int


@dataclass(frozen=True)
class ProjectType:
    key: str
    label: str
    input_mode: str
    summary_bucket: str

    def validate_and_values(self, project, form):
        raise NotImplementedError

    def save_result(self, participant_id, project, recorder_id, form):
        values = self.validate_and_values(project, form)
        result = Result.query.filter_by(
            participant_id=participant_id,
            project_id=project.id,
        ).first()
        if not result:
            result = Result(participant_id=participant_id, project_id=project.id)
            db.session.add(result)

        for key, value in values.items():
            setattr(result, key, value)
        result.recorder_id = recorder_id
        return result

    def export_headers(self, project):
        raise NotImplementedError

    def export_values(self, project, result):
        raise NotImplementedError

    def display_value(self, value):
        return value


class TimeProjectType(ProjectType):
    def __init__(self):
        super().__init__(
            key='time',
            label='时间',
            input_mode='time',
            summary_bucket='time',
        )

    def validate_and_values(self, project, form):
        time_minutes = safe_float(form.get('time_minutes', 0))
        time_seconds = safe_float(form.get('time_seconds', 0))
        time_ms = safe_float(form.get('time_ms', 0))
        violations = safe_int(form.get('violations', 0))
        total_sec = time_minutes * 60 + time_seconds + time_ms / 1000
        if total_sec <= 0:
            raise ValueError('用时不能为0')
        penalty = violations * project.penalty_per_violation
        return {
            'time_seconds': total_sec,
            'violations': violations,
            'penalty_time': penalty,
            'final_time': total_sec + penalty,
        }

    def export_headers(self, project):
        return [
            f'{project.name}(用时)',
            f'{project.name}(犯规)',
            f'{project.name}(罚时)',
            f'{project.name}(最终)',
        ]

    def export_values(self, project, result):
        if not result:
            return ['', '', '', '']
        return [
            format_time(result.time_seconds),
            result.violations,
            format_time(result.penalty_time),
            format_time(result.final_time),
        ]

    def display_value(self, value):
        return format_time(value)


class ScoreProjectType(ProjectType):
    def __init__(self):
        super().__init__(
            key='score',
            label='分数',
            input_mode='score',
            summary_bucket='score',
        )

    def validate_and_values(self, project, form):
        score = safe_float(form.get('score', 0), 0)
        if score <= 0:
            raise ValueError('成绩必须大于0')
        if project.max_score and score > project.max_score:
            raise ValueError(f'成绩不能超过满分{project.max_score}')
        return {
            'time_seconds': score,
            'violations': 0,
            'penalty_time': 0,
            'final_time': score,
        }

    def export_headers(self, project):
        return [f'{project.name}(成绩)']

    def export_values(self, project, result):
        return [result.final_time if result else '-']


PROJECT_TYPES = {
    'time': TimeProjectType(),
    'score': ScoreProjectType(),
}


def get_project_type(key):
    return PROJECT_TYPES.get(key) or PROJECT_TYPES['time']


def project_type_choices():
    return [(item.key, item.label) for item in PROJECT_TYPES.values()]


def project_type_map():
    return PROJECT_TYPES.copy()


def project_summary_bucket(project):
    return get_project_type(project.type).summary_bucket
