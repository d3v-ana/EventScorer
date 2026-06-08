from werkzeug.security import generate_password_hash


PASSWORD_HASH_METHOD = 'pbkdf2:sha256'


def hash_password(password):
    return generate_password_hash(password, method=PASSWORD_HASH_METHOD)
