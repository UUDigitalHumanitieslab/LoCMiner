class Config(object):
    DEBUG = False
    TESTING = False
    SQLALCHEMY_TRACK_MODIFICATIONS = True


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'postgresql://loc:locminer@localhost:5432/loc'
    CELERY_BROKER_URL = 'redis://localhost:6379/1'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
    CELERY_DEFAULT_QUEUE = 'loc'
    SECRET_KEY = 'production key'


class DevelopmentConfig(ProductionConfig):
    DEBUG = True
    SECRET_KEY = 'development key'


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SECRET_KEY = 'test key'
