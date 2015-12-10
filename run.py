from LoCMiner.factories import create_app

if __name__ == '__main__':
    app = create_app('LoCMiner.config.ProductionConfig')
    app.debug = True
    app.run()
