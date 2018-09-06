import os

from flask import Flask


def create_app(test_config=None):
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        # a default secret that should be overridden by instance config
        SECRET_KEY='does this really matter?',
        SESSION_TYPE='filesystem',
        SESSION_PERMANENT=False,
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.update(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    from . import rds_app
    app.register_blueprint(rds_app.bp)

    return app


# def start_https():
#     rds_app.secret_key = 'does this really matter?'
#     rds_app.config['SESSION_TYPE'] = 'filesystem'
#     rds_app.config['SESSION_PERMANENT'] = False
#
#     logger.info('Starting HTTPS server...')
#     if "DEBUG" in os.environ:
#         rds_app.run(ssl_context=('ssl/server.pem', 'ssl/key.pem'), debug=True, host='0.0.0.0', port=5151)
#     else:
#         rds_app.run(ssl_context=('ssl/server.pem', 'ssl/key.pem'), host='0.0.0.0', port=5151)
#     logger.info('HTTPS Exiting...')
#     exit(0)

