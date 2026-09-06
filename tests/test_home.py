from django.test import Client


def test_home_returns_successfully():
    response = Client().get("/")

    assert response.status_code == 200
    assert response.content == b""
