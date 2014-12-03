from LoCMiner.factories import create_app

if __name__ == '__main__':
    app = create_app(dict(
        SQLALCHEMY_DATABASE_URI='postgresql://loc:locminer@localhost:5432/loc',
        CELERY_BROKER_URL='redis://localhost:6379',
        CELERY_RESULT_BACKEND='redis://localhost:6379',
        SECRET_KEY='development key',
    ))
    app.debug = True
    app.run()
