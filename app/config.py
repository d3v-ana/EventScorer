import os
import secrets

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        # 持久化密钥文件，避免每次重启后 session 失效
        key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance', '.secret_key')
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                SECRET_KEY = f.read().strip()
        else:
            SECRET_KEY = secrets.token_hex(32)
            os.makedirs(os.path.dirname(key_file), exist_ok=True)
            with open(key_file, 'w') as f:
                f.write(SECRET_KEY)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    PERMANENT_SESSION_LIFETIME = 7 * 24 * 3600  # 7天
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads')

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        host = os.environ.get('DB_HOST')
        user = os.environ.get('DB_USER')
        password = os.environ.get('DB_PASSWORD')
        db_name = os.environ.get('DB_NAME')
        if host and user and db_name:
            return f'mysql+pymysql://{user}:{password}@{host}/{db_name}?charset=utf8mb4'
        return 'sqlite:///' + os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'instance', 'activity.db'
        )


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
