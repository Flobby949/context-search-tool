from app.service import Service


def test_service_runs():
    assert Service() is not None
