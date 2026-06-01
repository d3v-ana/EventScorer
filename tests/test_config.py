from app import create_app


def test_create_app_uses_requested_config():
    app = create_app('config.TestConfig')

    assert app.config['TESTING'] is True
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///:memory:'
