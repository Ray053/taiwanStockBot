"""Integration tests for API endpoints."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.database import get_db


def make_mock_db():
    mock = MagicMock()
    # Default: queries return empty lists / None
    mock.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    mock.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    mock.query.return_value.order_by.return_value.first.return_value = None
    mock.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    mock.query.return_value.filter.return_value.first.return_value = None
    return mock


@pytest.fixture(scope="module")
def client():
    with patch("app.main.run_migrations"):
        from app.main import app
        mock_db = make_mock_db()
        app.dependency_overrides[get_db] = lambda: mock_db
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()


class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "taiwan-stock-bot" in data["service"]


class TestScoresEndpoints:
    def test_today_scores_empty(self, client):
        resp = client.get("/api/v1/scores/today")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_scores_by_date_format(self, client):
        resp = client.get("/api/v1/scores/2024-01-15")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_scores_invalid_date(self, client):
        resp = client.get("/api/v1/scores/not-a-date")
        assert resp.status_code == 422

    def test_scores_with_limit(self, client):
        resp = client.get("/api/v1/scores/today?limit=5")
        assert resp.status_code == 200

    def test_stock_score_history(self, client):
        resp = client.get("/api/v1/scores/stock/2330")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestStocksEndpoints:
    def test_kline_stock_not_found(self, client):
        resp = client.get("/api/v1/stocks/9999/kline")
        assert resp.status_code == 404

    def test_institutional_stock_not_found(self, client):
        resp = client.get("/api/v1/stocks/9999/institutional")
        assert resp.status_code == 404

    def test_margin_stock_not_found(self, client):
        resp = client.get("/api/v1/stocks/9999/margin")
        assert resp.status_code == 404

    def test_detail_stock_not_found(self, client):
        resp = client.get("/api/v1/stocks/9999/detail")
        assert resp.status_code == 404


class TestMacroEndpoints:
    def test_macro_latest_404_when_empty(self, client):
        resp = client.get("/api/v1/macro/latest")
        assert resp.status_code == 404

    def test_macro_history_returns_list(self, client):
        resp = client.get("/api/v1/macro/history")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestAdminEndpoints:
    def test_trigger_score_requires_auth(self, client):
        resp = client.post("/api/v1/admin/trigger-score")
        assert resp.status_code == 422  # Missing X-API-Key header

    def test_trigger_score_wrong_key(self, client):
        resp = client.post(
            "/api/v1/admin/trigger-score",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 403

    def test_refresh_polymarket_requires_auth(self, client):
        resp = client.post("/api/v1/admin/refresh-polymarket")
        assert resp.status_code == 422

    def test_refresh_polymarket_wrong_key(self, client):
        resp = client.post(
            "/api/v1/admin/refresh-polymarket",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 403

    def test_trigger_score_valid_key(self, client):
        with patch("app.routers.admin.scoring_engine.run_scoring", return_value=[]):
            resp = client.post(
                "/api/v1/admin/trigger-score",
                headers={"X-API-Key": "test-api-key"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "stocks_scored" in data
