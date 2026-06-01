# 活动成绩管理系统

基于 Flask 的多活动成绩管理平台，支持**计时**和**分值**两种项目类型，提供二维码扫码注册、录入员录入成绩、自动排名与 Excel 导出。

## 功能特性

- **活动管理** — 创建学生/教职工活动，支持归档/恢复/删除
- **项目管理** — 分组管理项目（计时/分值），设置罚时或满分值
- **二维码注册** — 自定义助记词批量生成二维码，参与者扫码填写信息绑定
- **成绩录入** — 录入员（裁判）扫码后录入用时/分数，自动计算罚时
- **自动排名** — 总排名（计时升序/分值降序）与单项排名，支持自动刷新
- **成绩历史** — 每个参赛者的完整成绩记录，可查看项目、录入员、提交时间
- **系统日志** — 记录生成二维码/注册/录入/删除等操作，可按类型过滤
- **Excel 导出** — 将成绩导出为格式化的 Excel 文件
- **权限控制** — 管理员、录入员、参与者三级权限

## 数据模型

| 表 | 用途 | 说明 |
| --- | --- | --- |
| `admin` | 管理员 | 后台登录账号 |
| `activity` | 活动/赛事 | 名称、类型（学生/教职工）、归档状态 |
| `activity_type` | 活动类型 | 自定义活动类型（如运动会、艺术节） |
| `project` | 比赛项目 | 名称、类型（time/score）、罚时/满分 |
| `activity_project` | 活动⇄项目关联 | 多对多关系 |
| `project_category` | 项目分组 | 下拉可选的分组 |
| `qr_code` | 二维码 | 唯一 code（助记词+数字）、使用状态 |
| `participant` | 参与者 | 姓名、班级、自定义字段 |
| `recorder` | 录入员（裁判） | 姓名、4位密钥 |
| `activity_recorder` | 录入员权限 | 活动中的项目权限 |
| `result` | 成绩记录 | 用时/分数、犯规、罚时、最终结果、录入员 |
| `system_log` | 系统操作日志 | 记录关键操作的时间线 |

## 业务流程

```
管理员创建活动 → 添加项目 → 配置自定义词库 → 批量生成二维码 → 打印
                                  ↑                          │
                          录入员扫码录入成绩                  │
                                  ↑                          ↓
                           参与者扫码注册 ← 二维码贴在参赛者身上
                                  │
                                  ↓
             排名页查看 / Excel 导出 / 成绩历史查看
```

## 项目结构

```
EventScorer/
├── run.py                          # 应用入口
├── requirements.txt                # Python 依赖
├── pytest.ini                      # 测试配置
│
├── app/
│   ├── __init__.py                 # Flask 工厂函数
│   ├── config.py                   # 配置类
│   ├── models.py                   # 12 个 SQLAlchemy 模型
│   ├── utils.py                    # 工具函数（CSRF、分页、格式化、日志等）
│   ├── project_types.py            # 项目类型注册（time / score）
│   ├── scoring.py                  # 成绩汇总与排名逻辑
│   ├── routes/
│   │   ├── auth.py                 # 管理员登录/登出/账号管理
│   │   ├── admin.py                # 后台管理（活动/项目/二维码/录入员/排名/导出）
│   │   ├── recorder.py             # 录入员登录/扫码/录入
│   │   ├── participant.py          # 参与者注册/查看成绩
│   │   └── api.py                  # JSON API 接口
│   ├── templates/                  # 26 个 Jinja2 模板
│   └── static/
│       ├── css/                    # 样式文件
│       ├── js/                     # 前端 JS（录入员扫码页面）
│       └── qrcodes/                # 生成的二维码 PNG（运行时自动生成）
│
├── tests/
│   ├── conftest.py                 # 测试夹具
│   ├── test_admin.py               # 管理员 CRUD 测试
│   ├── test_auth.py                # 登录/权限测试
│   ├── test_recorder.py            # 录入员流程测试
│   ├── test_participant.py         # 参与者注册测试
│   ├── test_models.py              # 模型关系测试
│   ├── test_boundary.py            # 边界条件测试
│   ├── test_flow.py                # 完整业务流程测试
│   ├── test_concurrency.py         # 并发测试
│   ├── test_config.py              # 配置测试
│   ├── test_project_types.py       # 项目类型测试
│   ├── test_utils.py               # 工具函数测试
│   ├── test_warnings.py            # 告警测试
│   └── test_pagination_utils.py    # 分页工具测试
│
└── activity.service                # systemd 服务单元（Gunicorn）
```

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python Flask + SQLAlchemy |
| 数据库 | SQLite（开发）/ MySQL（生产） |
| 前端 | Jinja2 模板 + 纯 CSS |
| 部署 | Gunicorn + Nginx + systemd |
| 二维码 | qrcode[pil] |
| Excel | openpyxl |
| 测试 | pytest（143+ 测试用例） |

## 快速开始（开发环境）

```bash
# 1. 克隆仓库
git clone <repo-url>
cd EventScorer

# 2. 创建虚拟环境并安装依赖
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows

pip install -r requirements.txt

# 3. 运行（自动创建 SQLite 数据库 + 默认管理员）
python run.py
```

首次启动会自动：
- 创建 SQLite 数据库 `instance/activity.db`
- 生成默认管理员账号（用户名 `admin`，密码打印在控制台）
- 创建所有数据表

浏览器访问 `http://127.0.0.1:5000` 即可使用。

## 生产部署流程

### 1. 部署到服务器

将项目文件上传到服务器（如 `/var/www/EventScorer`），安装依赖：

```bash
cd /var/www/EventScorer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```


### 2. 初始化数据库

```bash
# 如果使用 MySQL，先创建数据库
mysql -u root -p -e "CREATE DATABASE yytj CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 首次启动会自动建表和创建默认管理员
gunicorn -w 4 -b 127.0.0.1:5000 run:app
```

### 3. 配置 Nginx 反向代理

```bash
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location ^~ /static/ {
        alias /www/wwwroot/EventScorer/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /uploads/ {
        alias /www/wwwroot/EventScorer/uploads/;
        internal;
    }
```


关键配置要点：
- 将 `server_name` 改为你的域名
- 设置 `proxy_pass http://127.0.0.1:5000` 转发到 Gunicorn
- 配置 HTTPS（推荐使用 Certbot）

### 4. 配置 systemd 服务

参考 [`activity.service`](activity.service)：

```bash
sudo cp activity.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable activity
sudo systemctl start activity
```

### 5. 验证部署

```bash
# 查看服务状态
sudo systemctl status activity

# 查看日志
sudo journalctl -u activity -f

# 访问 http://your-domain/admin 确认可正常登录
```

### 6. 后续维护

```bash
# 更新代码
cd /var/www/EventScorer
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart activity

# 查看应用日志
sudo journalctl -u activity -f

# 备份数据库
cp instance/activity.db backups/activity-$(date +%Y%m%d).db
```

## 访问路径

| 路径 | 用途 |
| --- | --- |
| `/` | 首页 |
| `/login` | 管理员登录 |
| `/admin` | 活动列表 |
| `/admin/projects` | 项目管理 |
| `/admin/activity/<id>` | 活动详情（二维码/参赛者/排名/录入员） |
| `/admin/activity/<id>/ranking` | 活动排名 |
| `/admin/logs` | 系统日志 |
| `/admin/participant/<id>/history` | 参赛者成绩历史 |
| `/admin/recorders` | 录入员管理 |
| `/register/<code>` | 参与者扫码注册 |
| `/recorder/<id>/scan` | 录入员扫码页面 |

## 环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `SECRET_KEY` | Flask 会话密钥 | 随机生成 |
| `ADMIN_PASSWORD` | 初始管理员密码 | 随机生成（打印到控制台） |
| `FLASK_ENV` | `development` 启用调试 | production |
| `DB_HOST` | MySQL 主机 | SQLite |
| `DB_USER` | MySQL 用户名 | — |
| `DB_PASSWORD` | MySQL 密码 | — |
| `DB_NAME` | MySQL 数据库名 | — |

## 运行测试

```bash
pytest tests/ -v
# 143+ 测试用例，覆盖管理员操作、录入员流程、参与者注册、并发场景、边界条件
```

## 许可证

MIT
