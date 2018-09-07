import pytest
from rds_slow_query_log_examiner import create_app

@pytest.fixture
def app():
    app = create_app( {
        'TESTING': True
    })

    yield app

@pytest.fixture
def client():
    return app.test_client()

