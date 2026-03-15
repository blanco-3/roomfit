from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def auth_headers():
    email = 'dev-test@roomfit.ai'
    pw = 'devpass1234'
    client.post('/v1/auth/register', json={
        'email': email,
        'password': pw,
        'display_name': 'Dev'
    })
    login = client.post('/v1/auth/login', json={'email': email, 'password': pw})
    token = login.json()['token']
    return {'Authorization': f'Bearer {token}'}


def test_health():
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json()['ok'] is True


def test_estimate_and_recommend():
    headers = auth_headers()

    est = client.post('/v1/room/estimate', json={
        'width_cm': 280,
        'length_cm': 340,
        'height_cm': 240,
        'mood': 'minimal_warm',
        'purpose': 'work_sleep',
        'budget_krw': 1200000,
    }, headers=headers)
    assert est.status_code == 200
    room_id = est.json()['room_profile']['room_id']

    rec = client.post('/v1/recommendations', json={
        'room_id': room_id,
        'required_categories': ['bed', 'desk', 'chair', 'storage']
    }, headers=headers)
    assert rec.status_code == 200
    data = rec.json()
    assert 'summary' in data
    assert 'items' in data
    assert 'run_id' in data
