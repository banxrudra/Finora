import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db as _db


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def register(client, name="Test User", email="test@example.com", password="password123"):
    return client.post("/register", data={"name": name, "email": email, "password": password, "confirm": password})


def login(client, email="test@example.com", password="password123"):
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture()
def auth_client(client):
    register(client)
    return client
