import pytest
from fastapi.testclient import TestClient

from app import main


SAMPLE_DATA = {
    "date": "2026-05-18",
    "updated_at": "2026-05-18T17:00:00",
    "claude_code": {
        "available": True,
        "input_tokens_5h": 100,
        "output_tokens_5h": 50,
        "cache_tokens_5h": 25,
        "tokens_5h": 175,
        "input_tokens_7d": 1000,
        "output_tokens_7d": 500,
        "cache_tokens_7d": 250,
        "tokens_7d": 1750,
    },
    "codex": {
        "available": True,
        "tokens_today": 1234,
        "sessions_today": 3,
        "tokens_7d": 9876,
    },
    "codex_limits": {
        "available": True,
        "primary_used_pct": 42,
        "primary_resets_at": "2026-05-18T20:00:00Z",
        "secondary_used_pct": 64,
        "secondary_resets_at": "2026-05-21T20:00:00Z",
    },
    "claude_api": {
        "configured": True,
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
    },
    "openai_api": {
        "configured": True,
        "input_tokens": 11,
        "output_tokens": 22,
        "total_tokens": 33,
    },
    "claude_subscription": {
        "configured": True,
        "five_hour": {
            "utilization": 25,
            "resets_at": "2026-05-18T20:00:00Z",
        },
        "seven_day": {
            "utilization": 55,
            "resets_at": "2026-05-21T20:00:00Z",
        },
    },
}


@pytest.fixture(autouse=True)
def mock_data(monkeypatch):
    async def fake_get_data(force: bool = False):
        return SAMPLE_DATA

    monkeypatch.setattr(main, "_get_data", fake_get_data)
    monkeypatch.setattr(main, "REFRESH_TOKEN", "")


@pytest.fixture()
def client():
    return TestClient(main.app)


def test_claude_local_contract(client):
    response = client.get("/usage/claude-local")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["input_tokens_5h"] == 100
    assert data["output_tokens_7d"] == 500
    assert data["tokens_7d"] == 1750
    assert data["date"] == "2026-05-18"
    assert data["updated_at"] == "2026-05-18T17:00:00"


def test_codex_local_contract(client):
    response = client.get("/usage/codex-local")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "available": True,
        "tokens_today": 1234,
        "sessions_today": 3,
        "tokens_7d": 9876,
        "date": "2026-05-18",
        "updated_at": "2026-05-18T17:00:00",
    }


def test_codex_limits_contract(client):
    response = client.get("/usage/codex-limits")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "available": True,
        "used_percent_5h": 42,
        "used_percent_7d": 64,
        "resets_at_5h": "2026-05-18T20:00:00Z",
        "resets_at_7d": "2026-05-21T20:00:00Z",
        "date": "2026-05-18",
        "updated_at": "2026-05-18T17:00:00",
    }


def test_claude_subscription_contract(client):
    response = client.get("/usage/claude-subscription")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "configured": True,
        "error": None,
        "used_percent_5h": 25,
        "used_percent_7d": 55,
        "resets_at_5h": "2026-05-18T20:00:00Z",
        "resets_at_7d": "2026-05-21T20:00:00Z",
        "date": "2026-05-18",
        "updated_at": "2026-05-18T17:00:00",
    }


def test_refresh_allows_unauthenticated_when_token_is_unset(client):
    response = client.post("/refresh")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "updated_at": "2026-05-18T17:00:00"}


def test_refresh_requires_bearer_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(main, "REFRESH_TOKEN", "secret-token")

    missing = client.post("/refresh")
    invalid = client.post("/refresh", headers={"Authorization": "Bearer wrong"})
    valid = client.post("/refresh", headers={"Authorization": "Bearer secret-token"})

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert valid.status_code == 200
