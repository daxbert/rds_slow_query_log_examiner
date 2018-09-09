import os

import pytest
from rds_slow_query_log_examiner import create_app

@pytest.fixture
def app():
    if not ( 'AWS_ACCESS_KEY_ID' in os.environ and 'AWS_SECRET_ACCESS_KEY' in os.environ ):
        print("WARNING: AWS Environment variables needed for testing")
    app = create_app( {
        'TESTING': True,
        'SAVE_API_CALLS': True
    })
    app.config['SERVER_NAME'] = 'localhost.localdomain'
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.config['SECRET_KEY'] = 'does this really matter?'


    yield app

@pytest.fixture
def client(app):
    return app.test_client()


