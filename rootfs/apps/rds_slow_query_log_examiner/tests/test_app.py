import pprint

import pytest
from rds_slow_query_log_examiner import create_app

@pytest.fixture
def app():
    app = create_app( {
        'TESTING': True
    })

    yield app

@pytest.fixture
def client(app):
    return app.test_client()


def test_nouser_homepage_redirects(client):
    rv = client.get('/')
    assert rv.status_code == 302
    assert "/credentials?redirect=" in rv.location
    pprint.pprint(rv.location)

def test_nouser_regions_redirects(client):
    rv = client.get('/regions')
    assert rv.status_code == 302
    assert "/credentials?redirect=" in rv.location
    pprint.pprint(rv.location)

