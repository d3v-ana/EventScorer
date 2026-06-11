import json
from dataclasses import dataclass, field

from flask import has_app_context

from . import db
from .models import Participant, ProjectPluginDefinition, Result
from .utils import format_time, safe_float, safe_int


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    field_type: str = 'number'
    default: object = None
    required: bool = False
    min_value: float = None
    step: float = None
    placeholder: str = ''
    options: tuple = field(default_factory=tuple)

    def as_dict(self):
        return {
            'key': self.key,
            'label': self.label,
            'type': self.field_type,
            'default': self.default,
            'required': self.required,
            'min': self.min_value,
            'step': self.step,
            'placeholder': self.placeholder,
            'options': list(self.options),
        }


def _decode_config(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def get_project_config(project):
    config = _decode_config(getattr(project, 'type_config', ''))
    if config:
        config.setdefault('fields', {})
        config.setdefault('custom_fields', [])
        return config
    return legacy_project_config(project)


def set_project_config(project, config):
    config = config or {}
    config.setdefault('fields', {})
    config.setdefault('custom_fields', [])
    project.type_config = json.dumps(config, ensure_ascii=False)


def legacy_project_config(project):
    plugin = get_project_type(getattr(project, 'type', 'time'))
    fields = {}
    for item in plugin.config_fields:
        if item.key == 'penalty_per_violation':
            fields[item.key] = getattr(project, 'penalty_per_violation', item.default)
        elif item.key == 'max_score':
            fields[item.key] = getattr(project, 'max_score', item.default)
        else:
            fields[item.key] = item.default
    return {'fields': fields, 'custom_fields': []}


def sync_legacy_columns(project):
    fields = get_project_config(project).get('fields', {})
    project.penalty_per_violation = safe_float(
        fields.get('penalty_per_violation', getattr(project, 'penalty_per_violation', 5.0)),
        5.0,
    )
    max_score = fields.get('max_score')
    project.max_score = safe_float(max_score, 0) or None if max_score not in (None, '') else None


class ProjectType:
    key = 'time'
    label = '时间'
    input_component = 'time_input'
    summary_bucket = 'time'
    result_unit = 'time'
    ranking_policy = 'asc'
    result_field = 'score'
    source = 'code'
    version = 1
    config_fields = ()
    input_fields = ()
    ui_slots = {}

    @property
    def input_mode(self):
        return 'score' if self.input_component == 'number_input' else 'time'

    def config_field_dicts(self):
        return [item.as_dict() for item in self.config_fields]

    def input_field_dicts(self):
        if self.input_fields:
            return [item.as_dict() if hasattr(item, 'as_dict') else item
                    for item in self.input_fields]
        return [{'component': self.input_component}]

    def config_value(self, project, key, default=None):
        fields = get_project_config(project).get('fields', {})
        if key in fields and fields[key] != '':
            return fields[key]
        for item in self.config_fields:
            if item.key == key:
                return item.default
        return default

    def build_config_from_form(self, form):
        fields = {}
        errors = []
        for item in self.config_fields:
            raw = self._form_config_value(form, item)
            value = self._coerce_config_value(item, raw)
            if item.required and value in (None, ''):
                errors.append(f'{item.label}不能为空')
            fields[item.key] = value
        custom_fields = parse_custom_fields(form)
        return {
            'plugin_key': self.key,
            'plugin_version': self.version,
            'fields': fields,
            'custom_fields': custom_fields,
        }, errors

    def _form_config_value(self, form, item):
        names = [f'config_{item.key}', item.key]
        if item.key == 'penalty_per_violation':
            names.append('penalty')
        for name in names:
            if name in form:
                return form.get(name)
        return item.default

    def _coerce_config_value(self, item, raw):
        if item.field_type == 'number':
            if raw in (None, '') and item.default in (None, ''):
                return ''
            return safe_float(raw, item.default or 0)
        if item.field_type == 'boolean':
            return str(raw).lower() in ('1', 'true', 'on', 'yes')
        return '' if raw is None else str(raw).strip()

    def validate_and_values(self, project, form):
        raise NotImplementedError

    def compute_result(self, project, form):
        return self.validate_and_values(project, form)

    def save_result(self, participant_id, project, recorder_id, form):
        values = self.compute_result(project, form)
        result = Result.query.filter_by(
            participant_id=participant_id,
            project_id=project.id,
        ).first()
        if not result:
            participant = db.session.get(Participant, participant_id)
            tenant_id = participant.tenant_id if participant else project.tenant_id
            result = Result(tenant_id=tenant_id,
                            participant_id=participant_id, project_id=project.id)
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

    def result_label(self):
        return '成绩' if self.result_unit == 'score' else '最终用时'

    def option_label(self, project):
        return ''

    def result_sort_value(self, value):
        return value

    def config_summary(self, project):
        return self.option_label(project)

    def ui_slot(self, slot_name):
        return (self.ui_slots or {}).get(slot_name, '')


class TimeProjectType(ProjectType):
    key = 'time'
    label = '时间'
    input_component = 'time_input'
    summary_bucket = 'time'
    result_unit = 'time'
    config_fields = (
        ConfigField('penalty_per_violation', '犯规罚时(秒/次)', 'number',
                    default=5.0, required=True, min_value=0, step=0.1),
    )

    def validate_and_values(self, project, form):
        time_minutes = safe_float(form.get('time_minutes', 0))
        time_seconds = safe_float(form.get('time_seconds', 0))
        time_ms = safe_float(form.get('time_ms', 0))
        violations = safe_int(form.get('violations', 0))
        total_sec = time_minutes * 60 + time_seconds + time_ms / 1000
        if total_sec <= 0:
            raise ValueError('用时不能为0')
        penalty = violations * safe_float(self.config_value(project, 'penalty_per_violation', 5.0), 5.0)
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

    def option_label(self, project):
        return f'(罚{self.config_value(project, "penalty_per_violation", 5.0)}s/次)'


class ScoreProjectType(ProjectType):
    key = 'score'
    label = '分数'
    input_component = 'number_input'
    summary_bucket = 'score'
    result_unit = 'score'
    ranking_policy = 'desc'
    config_fields = (
        ConfigField('max_score', '最大分值', 'number',
                    default=100, required=False, min_value=0, step=0.1,
                    placeholder='不填则不限制'),
    )

    def validate_and_values(self, project, form):
        score = safe_float(form.get('score', 0), 0)
        if score <= 0:
            raise ValueError('成绩必须大于0')
        max_score = safe_float(self.config_value(project, 'max_score', 0), 0)
        if max_score and score > max_score:
            raise ValueError(f'成绩不能超过满分{max_score:g}')
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

    def option_label(self, project):
        max_score = self.config_value(project, 'max_score', None)
        return f'(满分{max_score or "-"}分)'


class ConfigProjectType(ProjectType):
    source = 'config'

    def __init__(self, definition):
        self.definition_id = definition.id
        self.key = definition.key
        self.label = definition.name
        self.description = definition.description or ''
        self.enabled = definition.enabled
        self.version = definition.version or 1
        self.config_fields = tuple(field_from_dict(item)
                                   for item in definition.config_fields)
        self.input_fields = definition.input_fields or []
        self.ui_slots = definition.slot_config or {}
        result_schema = definition.result_config or {}
        self.result_unit = result_schema.get('result_unit', 'score')
        self.summary_bucket = result_schema.get(
            'summary_bucket',
            'score' if self.result_unit == 'score' else 'time',
        )
        self.ranking_policy = result_schema.get(
            'ranking_policy',
            'desc' if self.summary_bucket == 'score' else 'asc',
        )
        self.input_component = result_schema.get(
            'input_component',
            infer_input_component(self.input_fields, self.result_unit),
        )
        self.result_field = result_schema.get('result_field') or infer_result_field(
            self.input_fields, self.input_component
        )
        self.result_label_text = result_schema.get(
            'result_label',
            '成绩' if self.result_unit == 'score' else '最终用时',
        )
        self.display_format = result_schema.get('display_format', self.result_unit)
        self.export_label = result_schema.get('export_label', self.result_label_text)

    def result_label(self):
        return self.result_label_text

    def validate_and_values(self, project, form):
        value = self._result_value(form)
        if self.result_unit == 'time':
            if value <= 0:
                raise ValueError(f'{self.result_label_text}不能为0')
        else:
            if value <= 0:
                raise ValueError(f'{self.result_label_text}必须大于0')
        min_value = self._schema_float('min_value', None)
        max_value = self._schema_float('max_value', None)
        if min_value is not None and value < min_value:
            raise ValueError(f'{self.result_label_text}不能小于{min_value:g}')
        if max_value is not None and value > max_value:
            raise ValueError(f'{self.result_label_text}不能超过{max_value:g}')
        return {
            'time_seconds': value,
            'violations': safe_int(form.get('violations', 0), 0),
            'penalty_time': 0,
            'final_time': value,
        }

    def _result_value(self, form):
        if self.input_component == 'time_input':
            minutes = safe_float(form.get('time_minutes', 0), 0)
            seconds = safe_float(form.get('time_seconds', 0), 0)
            ms = safe_float(form.get('time_ms', 0), 0)
            return minutes * 60 + seconds + ms / 1000
        return safe_float(form.get(self.result_field, form.get('score', 0)), 0)

    def _schema_float(self, key, default):
        for item in self.input_fields:
            if item.get('key') == self.result_field and key in item:
                if item.get(key) in (None, ''):
                    return default
                return safe_float(item.get(key), default or 0)
        return default

    def display_value(self, value):
        if self.display_format == 'time' or self.result_unit == 'time':
            return format_time(value)
        return f'{safe_float(value, 0):g}'

    def export_headers(self, project):
        return [f'{project.name}({self.export_label})']

    def export_values(self, project, result):
        return [self.display_value(result.final_time) if result else '-']

    def option_label(self, project):
        return self.config_summary(project)

    def config_summary(self, project):
        fields = get_project_config(project).get('fields', {})
        bits = []
        for item in self.config_fields:
            value = fields.get(item.key, item.default)
            if value not in (None, ''):
                bits.append(f'{item.label}:{value}')
        return f'({" / ".join(bits)})' if bits else ''


PROJECT_TYPES = {}


def register_project_type(project_type):
    PROJECT_TYPES[project_type.key] = project_type
    return project_type


register_project_type(TimeProjectType())
register_project_type(ScoreProjectType())


def get_project_type(key):
    if key in PROJECT_TYPES:
        return PROJECT_TYPES[key]
    return config_project_type_map().get(key) or PROJECT_TYPES['time']


def project_type_choices(include_disabled=False):
    return [(item.key, item.label) for item in project_type_map(include_disabled).values()
            if include_disabled or getattr(item, 'enabled', True)]


def project_type_map(include_disabled=False):
    items = config_project_type_map(include_disabled=include_disabled)
    items.update(PROJECT_TYPES)
    return items


def _metadata_for(item):
    return {
        'key': item.key,
        'label': item.label,
        'source': getattr(item, 'source', 'code'),
        'version': getattr(item, 'version', 1),
        'enabled': getattr(item, 'enabled', True),
        'input_component': item.input_component,
        'input_mode': item.input_mode,
        'input_fields': item.input_field_dicts(),
        'summary_bucket': item.summary_bucket,
        'result_unit': item.result_unit,
        'ranking_policy': getattr(item, 'ranking_policy', 'asc'),
        'result_field': getattr(item, 'result_field', 'score'),
        'config_fields': item.config_field_dicts(),
        'ui_slots': getattr(item, 'ui_slots', {}),
    }


def project_type_metadata(include_disabled=False):
    data = {key: _metadata_for(item) for key, item in PROJECT_TYPES.items()}
    data.update({
        key: _metadata_for(item)
        for key, item in config_project_type_map(include_disabled).items()
    })
    return data


def project_summary_bucket(project):
    return get_project_type(project.type).summary_bucket


def field_from_dict(data):
    data = data or {}
    return ConfigField(
        key=str(data.get('key', '')).strip(),
        label=str(data.get('label') or data.get('key') or '').strip(),
        field_type=data.get('type') or data.get('field_type') or 'number',
        default=data.get('default'),
        required=bool(data.get('required', False)),
        min_value=data.get('min') if 'min' in data else data.get('min_value'),
        step=data.get('step'),
        placeholder=data.get('placeholder', ''),
        options=tuple(data.get('options') or ()),
    )


def infer_input_component(input_fields, result_unit):
    for item in input_fields or []:
        component = item.get('component') or item.get('type')
        if component in ('time_input', 'timer', 'time'):
            return 'time_input'
        if component in ('number_input', 'number'):
            return 'number_input'
    return 'time_input' if result_unit == 'time' else 'number_input'


def infer_result_field(input_fields, input_component):
    for item in input_fields or []:
        if item.get('result') or item.get('primary'):
            return item.get('key') or 'score'
    for item in input_fields or []:
        if item.get('key'):
            return item.get('key')
    return 'score' if input_component == 'number_input' else 'time_seconds'


def config_project_type_map(include_disabled=False):
    if not has_app_context():
        return {}
    query = ProjectPluginDefinition.query.filter_by(source='config')
    if not include_disabled:
        query = query.filter_by(enabled=True)
    items = {}
    for definition in query.order_by(ProjectPluginDefinition.tenant_id,
                                     ProjectPluginDefinition.key).all():
        if definition.key in PROJECT_TYPES:
            continue
        items[definition.key] = ConfigProjectType(definition)
    return items


def plugin_definition_payload(definition):
    return {
        'key': definition.key,
        'name': definition.name,
        'description': definition.description or '',
        'enabled': definition.enabled,
        'source': definition.source,
        'version': definition.version,
        'config_schema': definition.config_fields,
        'input_schema': definition.input_fields,
        'result_schema': definition.result_config,
        'ui_slots': definition.slot_config,
    }


def parse_custom_fields(form):
    def get_list(name):
        if hasattr(form, 'getlist'):
            return form.getlist(name)
        value = form.get(name, [])
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    fields = []
    keys = get_list('custom_config_key[]')
    labels = get_list('custom_config_label[]')
    types = get_list('custom_config_type[]')
    values = get_list('custom_config_value[]')
    for idx, key in enumerate(keys):
        key = str(key or '').strip()[:50]
        label = str(labels[idx] if idx < len(labels) else '').strip()[:50]
        field_type = types[idx] if idx < len(types) else 'text'
        value = values[idx] if idx < len(values) else ''
        if not key or not label:
            continue
        if field_type not in ('text', 'number', 'boolean', 'select'):
            field_type = 'text'
        if field_type == 'number':
            value = safe_float(value, 0)
        elif field_type == 'boolean':
            value = str(value).lower() in ('1', 'true', 'on', 'yes')
        fields.append({
            'key': key,
            'label': label,
            'type': field_type,
            'value': value,
        })
    return fields
