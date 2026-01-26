"""
pytest configuration and fixtures for myDREAMS tests.
"""
import os
import sys
from pathlib import Path

import pytest

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'src'))


@pytest.fixture
def project_root():
    """Return the project root path."""
    return PROJECT_ROOT


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary database path for testing."""
    return tmp_path / "test_dreams.db"


@pytest.fixture
def test_db(test_db_path):
    """Create an in-memory test database with schema."""
    from src.core.database import DREAMSDatabase
    db = DREAMSDatabase(str(test_db_path))
    yield db
    # Cleanup happens automatically when temp directory is removed


@pytest.fixture
def sample_lead():
    """Sample lead data for testing."""
    return {
        "id": "test-lead-001",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "phone": "8285551234",
        "stage": "lead",
        "type": "buyer",
        "source": "Website",
        "heat_score": 75,
        "value_score": 60,
        "relationship_score": 50,
        "priority_score": 65
    }


@pytest.fixture
def sample_property():
    """Sample property data for testing."""
    return {
        "id": "test-prop-001",
        "address": "123 Main St",
        "city": "Asheville",
        "state": "NC",
        "zip": "28801",
        "price": 350000,
        "beds": 3,
        "baths": 2.0,
        "sqft": 1800,
        "acreage": 0.5,
        "status": "active",
        "mls_number": "MLS12345",
        "listing_agent_name": "Jane Agent",
        "source": "zillow"
    }


@pytest.fixture
def mock_fub_api(mocker):
    """Mock FUB API responses."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"people": []}
    mock_response.status_code = 200
    mocker.patch('httpx.AsyncClient.get', return_value=mock_response)
    mocker.patch('httpx.AsyncClient.post', return_value=mock_response)
    return mock_response


@pytest.fixture
def env_vars(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("DREAMS_DB_PATH", ":memory:")
    monkeypatch.setenv("FUB_API_KEY", "test_key")
    monkeypatch.setenv("DREAMS_ENV", "test")
