"""Shared test fixtures."""
import os
import pytest
from fastapi.testclient import TestClient

# Override DB/Redis URLs for testing before importing app
os.environ.setdefault("DATABASE_URL", "postgresql://stockbot:password@localhost:5432/stockbot_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ["ADMIN_API_KEY"] = "test-api-key"  # Always override for tests
os.environ.setdefault("FINMIND_API_TOKEN", "")

# Force settings singleton to reflect test values after env overrides
from app.config import settings
settings.admin_api_key = "test-api-key"


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c
