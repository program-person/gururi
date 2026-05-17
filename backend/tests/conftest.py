from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.config as app_config
from app.main import app

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_GRAPH = FIXTURES / "tiny.json"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(app_config.settings, "data_path", TINY_GRAPH)
    with TestClient(app) as test_client:
        yield test_client
