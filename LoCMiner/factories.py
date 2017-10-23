from flask import Flask
from celery import Celery

from .extensions import db
from .views import site
from .config import ProductionConfig


def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)

    db.init_app(app)
    db.create_all(app=app)  # pass app because of Flask-SQLAlchemy contexts

    app.register_blueprint(site)

    return app


def create_celery(app=None):
    app = app or create_app(ProductionConfig)
    celery = Celery(app.import_name,
                    backend=app.config['CELERY_RESULT_BACKEND'],
                    broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery.Task = ContextTask
    celery.app = app

    return celery