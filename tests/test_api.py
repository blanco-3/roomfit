import os

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app


init_db()
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


def test_dev_mode_session_without_login():
    prev = os.environ.get('DEV_MODE')
    os.environ['DEV_MODE'] = '1'
    try:
        sess = client.post('/v1/dev/session')
        assert sess.status_code == 200
        token = sess.json()['token']
        assert token

        # no auth header should still pass in dev mode
        est = client.post('/v1/room/estimate', json={
            'width_cm': 280,
            'length_cm': 340,
            'height_cm': 240,
            'mood': 'minimal_warm',
            'purpose': 'work_sleep',
            'budget_krw': 1200000,
        })
        assert est.status_code == 200
    finally:
        if prev is None:
            os.environ.pop('DEV_MODE', None)
        else:
            os.environ['DEV_MODE'] = prev


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
    assert 'alternatives' in data
    assert 'run_id' in data
    assert {'budget_krw', 'remaining_budget_krw', 'budget_usage_pct'}.issubset(data['summary'].keys())


def test_ops_logs_endpoint():
    headers = auth_headers()
    r = client.get('/v1/ops/logs?limit=5', headers=headers)
    assert r.status_code == 200
    payload = r.json()
    assert 'items' in payload
    assert isinstance(payload['items'], list)
    assert len(payload['items']) >= 1


def test_recommendation_history_endpoint():
    headers = auth_headers()

    est = client.post('/v1/room/estimate', json={
        'width_cm': 280,
        'length_cm': 340,
        'height_cm': 240,
        'mood': 'minimal_warm',
        'purpose': 'work_sleep',
        'budget_krw': 1200000,
    }, headers=headers)
    room_id = est.json()['room_profile']['room_id']

    client.post('/v1/recommendations', json={
        'room_id': room_id,
        'required_categories': ['bed', 'desk', 'chair', 'storage']
    }, headers=headers)

    hist = client.get('/v1/recommendations/history?limit=10', headers=headers)
    assert hist.status_code == 200
    data = hist.json()
    assert 'items' in data
    assert len(data['items']) >= 1
    assert {'run_id', 'room_id', 'total_price_krw'}.issubset(data['items'][0].keys())


def test_auto_estimate_from_photos_and_recommendation_flow():
    headers = auth_headers()

    files = [
        ('files', ('a.jpg', b'fakeimg1', 'image/jpeg')),
        ('files', ('b.jpg', b'fakeimg2', 'image/jpeg')),
    ]
    auto = client.post('/v1/room/auto-estimate', data={
        'reference_object': 'a4_long',
        'mood': 'minimal_warm',
        'purpose': 'work_sleep',
        'budget_krw': '1300000',
    }, files=files, headers=headers)
    assert auto.status_code == 200
    profile = auto.json()['room_profile']
    assert profile['estimate_source'] == 'ai_photo_reference'
    assert profile['estimate_confidence'] is not None
    assert 'needs_manual_review' in profile

    room_id = profile['room_id']
    reviewed = client.post('/v1/room/estimate', json={
        'room_id': room_id,
        'width_cm': 300,
        'length_cm': 360,
        'height_cm': 242,
        'mood': 'minimal_warm',
        'purpose': 'work_sleep',
        'budget_krw': 1300000,
        'estimate_source': 'ai_reviewed',
        'estimate_confidence': 0.81,
    }, headers=headers)
    assert reviewed.status_code == 200

    rec = client.post('/v1/recommendations', json={
        'room_id': room_id,
        'required_categories': ['bed', 'desk', 'chair', 'storage']
    }, headers=headers)
    assert rec.status_code == 200
    assert rec.json()['room_estimation']['source'] in ('ai_photo_reference', 'ai_reviewed', 'manual')


def test_recommendation_idempotency_key_reuses_run():
    headers = auth_headers()

    est = client.post('/v1/room/estimate', json={
        'width_cm': 280,
        'length_cm': 340,
        'height_cm': 240,
        'mood': 'minimal_warm',
        'purpose': 'work_sleep',
        'budget_krw': 1200000,
    }, headers=headers)
    room_id = est.json()['room_profile']['room_id']

    rec_headers = {**headers, 'Idempotency-Key': 'same-room-same-run'}
    first = client.post('/v1/recommendations', json={
        'room_id': room_id,
        'required_categories': ['bed', 'desk', 'chair', 'storage']
    }, headers=rec_headers)
    second = client.post('/v1/recommendations', json={
        'room_id': room_id,
        'required_categories': ['bed', 'desk', 'chair', 'storage']
    }, headers=rec_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()['run_id'] == second.json()['run_id']


def test_cv_job_mocked_estimation_flow():
    headers = auth_headers()

    est = client.post('/v1/room/estimate', json={
        'width_cm': 320,
        'length_cm': 360,
        'height_cm': 245,
        'mood': 'minimal_warm',
        'purpose': 'work_sleep',
        'budget_krw': 1500000,
    }, headers=headers)
    room_id = est.json()['room_profile']['room_id']

    files = [
        ('files', ('a.jpg', b'fakeimg1', 'image/jpeg')),
        ('files', ('b.jpg', b'fakeimg2', 'image/jpeg')),
    ]
    up = client.post('/v1/room/photos', data={'room_id': room_id}, files=files, headers=headers)
    assert up.status_code == 200

    created = client.post(f'/v1/cv/jobs?room_id={room_id}', headers=headers)
    assert created.status_code == 200
    job = created.json()['job']
    assert job['status'] in ('completed', 'running', 'queued')

    read_back = client.get(f"/v1/cv/jobs/{job['job_id']}", headers=headers)
    assert read_back.status_code == 200
    job2 = read_back.json()['job']
    assert 'result' in job2


def test_cv_job_idempotency_key_reuses_job():
    headers = auth_headers()

    est = client.post('/v1/room/estimate', json={
        'width_cm': 320,
        'length_cm': 360,
        'height_cm': 245,
        'mood': 'minimal_warm',
        'purpose': 'work_sleep',
        'budget_krw': 1500000,
    }, headers=headers)
    room_id = est.json()['room_profile']['room_id']

    files = [
        ('files', ('a.jpg', b'fakeimg1', 'image/jpeg')),
        ('files', ('b.jpg', b'fakeimg2', 'image/jpeg')),
    ]
    _ = client.post('/v1/room/photos', data={'room_id': room_id}, files=files, headers=headers)

    cv_headers = {**headers, 'Idempotency-Key': 'cv-retry-safe'}
    first = client.post(f'/v1/cv/jobs?room_id={room_id}', headers=cv_headers)
    second = client.post(f'/v1/cv/jobs?room_id={room_id}', headers=cv_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()['job']['job_id'] == second.json()['job']['job_id']
    assert second.json()['idempotent_reused'] is True
