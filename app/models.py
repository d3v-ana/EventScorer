from datetime import datetime, timezone
from . import db


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class ActivityType(db.Model):
    """活动类型（如：学生、教职工）"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    fields_config = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def get_parsed_fields(self):
        """返回字段配置列表，每个元素为 {key, label, type, required, options}"""
        import json
        if not self.fields_config:
            return []
        try:
            return json.loads(self.fields_config)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_fields(self, fields):
        """设置字段配置，fields 为 [{key,label,type,required,options},...]"""
        import json
        self.fields_config = json.dumps(fields, ensure_ascii=False)

    def get_default_fields(self):
        """根据活动类型名称生成默认字段配置"""
        if '学生' in self.name:
            return [
                {'key': 'name', 'label': '姓名', 'type': 'text', 'required': True},
                {'key': 'class_name', 'label': '班级', 'type': 'text', 'required': True},
            ]
        return [
            {'key': 'name', 'label': '姓名', 'type': 'text', 'required': True},
        ]

    def __str__(self):
        return self.name


class Department(db.Model):
    """发起部门"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __str__(self):
        return self.name


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    activity_type_id = db.Column(db.Integer, db.ForeignKey('activity_type.id'), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)
    need_class = db.Column(db.Boolean, default=True)
    archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    custom_words = db.Column(db.Text, nullable=True)
    activity_type = db.relationship('ActivityType', backref='activities', lazy=True)
    department = db.relationship('Department', backref='activities', lazy=True)
    activity_projects = db.relationship('ActivityProject', backref='activity', lazy=True,
                                        cascade='all, delete-orphan')
    qrcodes = db.relationship('QRCode', backref='activity', lazy=True)

    @property
    def recorders(self):
        return [ar.recorder for ar in self.activity_recorders]

    @property
    def user_type(self):
        """Return the configured activity type name for display."""
        return self.activity_type.name if self.activity_type else ''

    @property
    def is_student(self):
        name = self.activity_type.name if self.activity_type else ''
        return '\u5b66\u751f' in name

    @property
    def user_type_display(self):
        return self.user_type or '\u672a\u77e5'

    @property
    def registration_fields(self):
        """获取该活动有效的注册字段配置"""
        if self.activity_type:
            fields = self.activity_type.get_parsed_fields()
            if fields:
                return fields
        # Fallback: use need_class
        return [
            {'key': 'name', 'label': '姓名', 'type': 'text', 'required': True},
            {'key': 'class_name', 'label': '班级', 'type': 'text', 'required': True},
        ] if self.need_class else [
            {'key': 'name', 'label': '姓名', 'type': 'text', 'required': True},
        ]


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('project_category.id'), nullable=True)
    type = db.Column(db.String(10), default='time')
    max_score = db.Column(db.Float, nullable=True)
    penalty_per_violation = db.Column(db.Float, default=5.0)
    rule_file = db.Column(db.String(500))
    video_file = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    activity_projects = db.relationship('ActivityProject', backref='project', lazy=True,
                                        cascade='all, delete-orphan')
    results = db.relationship('Result', backref='project', lazy=True)


class ActivityProject(db.Model):
    """活动-项目关联表"""
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('activity_id', 'project_id'),)


class QRCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), nullable=False)
    status = db.Column(db.String(20), default='unused')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    participant = db.relationship('Participant', backref='qrcode', uselist=False, lazy=True)


class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    class_name = db.Column(db.String(50))
    extra_data = db.Column(db.Text, default='{}')
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), nullable=False)
    qrcode_id = db.Column(db.Integer, db.ForeignKey('qr_code.id'), nullable=False, unique=True)
    results = db.relationship('Result', backref='participant', lazy=True)

    def get_extra(self):
        """解析 extra_data JSON"""
        import json
        if not self.extra_data:
            return {}
        try:
            return json.loads(self.extra_data)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_extra(self, data):
        """设置 extra_data，data 为 dict"""
        import json
        self.extra_data = json.dumps(data, ensure_ascii=False)


class ProjectCategory(db.Model):
    """项目分类"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    projects = db.relationship('Project', backref='category', lazy=True)

    def __str__(self):
        return self.name


class Recorder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    record_key = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __str__(self):
        return self.name


class ActivityRecorder(db.Model):
    """活动-录入员关联表，记录录入员在某个活动中的项目权限"""
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), nullable=False)
    recorder_id = db.Column(db.Integer, db.ForeignKey('recorder.id'), nullable=False)
    project_ids = db.Column(db.String(500), default='')
    __table_args__ = (db.UniqueConstraint('activity_id', 'recorder_id'),)

    activity = db.relationship('Activity', backref=db.backref('activity_recorders', lazy=True, cascade='all, delete-orphan'))
    recorder = db.relationship('Recorder', backref=db.backref('activity_recorders', lazy=True, cascade='all, delete-orphan'))

    def project_id_list(self):
        if not self.project_ids:
            return []
        return [int(x) for x in self.project_ids.split(',') if x.strip()]


class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    time_seconds = db.Column(db.Float)
    violations = db.Column(db.Integer, default=0)
    penalty_time = db.Column(db.Float, default=0)
    final_time = db.Column(db.Float)
    recorder_id = db.Column(db.Integer, db.ForeignKey('recorder.id'))
    recorded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint('participant_id', 'project_id', name='uq_result_participant_project'),)


class SystemLog(db.Model):
    """系统操作日志"""
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    detail = db.Column(db.Text, nullable=True)
    recorder_id = db.Column(db.Integer, db.ForeignKey('recorder.id'), nullable=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    recorder = db.relationship('Recorder', backref='logs', lazy=True)
    participant = db.relationship('Participant', backref='logs', lazy=True)
    activity = db.relationship('Activity', backref='logs', lazy=True)

    def __repr__(self):
        return f'<SystemLog {self.action} #{self.id}>'
