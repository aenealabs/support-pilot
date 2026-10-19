from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from support_pilot.app import create_app
from support_pilot.config import load_settings
from support_pilot.db import make_engine


@pytest.fixture
def settings(tmp_path):
    return replace(load_settings(), db_path=str(tmp_path / "t.db"))


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings, engine=make_engine(settings.db_path)))


def test_pages_render(client):
    for path in ["/", "/problems", "/problems/PRB-1", "/data"]:
        assert client.get(path).status_code == 200, path
