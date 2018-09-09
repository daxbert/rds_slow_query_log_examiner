import os
import pprint


def logout(client):
    return client.get('/logout', follow_redirects=True)


def login(client, aws_access_key_id, aws_secret_key_id):
    return client.post('/credentials?redirect=/regions', data=dict(
        user_id=aws_access_key_id,
        password=aws_secret_key_id
    ), follow_redirects=True)


def test_no_user_homepage_redirects(client):
    rv = client.get('/', follow_redirects=False)
    assert rv.status_code == 302
    assert "/credentials?redirect=https://localhost.localdomain/" in rv.location


def test_no_user_regions_redirects(client):
    rv = client.get('/regions', follow_redirects=False)
    assert rv.status_code == 302
    assert "/credentials?redirect=https://localhost.localdomain/regions" in rv.location


def test_good_login(client):
    login(client, os.environ['AWS_ACCESS_KEY_ID'], os.environ['AWS_SECRET_ACCESS_KEY'])
    rv = client.get('/regions', follow_redirects=True)
    assert rv.status_code == 200
    assert b'us-east-1' in rv.data

    rv = logout(client)
    assert b'You\'ve been logged out' in rv.data


def test_bad_login(client):
    rv = login(client, 'FAKE', 'NOT_A_REAL_PASSWORD')
    assert b'Invalid AWS Credentials Provided' in rv.data


def test_session_login_success(app):
    with app.test_request_context():
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess['AWS_ACCESS_KEY_ID'] = os.environ['AWS_ACCESS_KEY_ID']
                sess['AWS_SECRET_ACCESS_KEY'] = os.environ['AWS_SECRET_ACCESS_KEY']
            rv = c.get('/', follow_redirects=True)
            assert rv.status_code == 200
            pprint.pprint(rv.location)


def test_session_login_failure(app):
    with app.test_request_context():
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess['AWS_ACCESS_KEY_ID'] = ""
                sess['AWS_SECRET_ACCESS_KEY'] = ""
            rv = c.get('/regions', follow_redirects=False)
            assert rv.status_code == 302
            assert "/credentials?redirect=/regions" in rv.location
