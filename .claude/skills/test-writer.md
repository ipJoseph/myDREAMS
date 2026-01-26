# Test Writer Skill

Generate pytest tests for myDREAMS codebase.

## Activation

Use this skill when asked to:
- Write tests for a module
- Add test coverage
- Create unit tests
- Generate test fixtures

## Instructions

When generating tests, follow these guidelines:

### 1. Test Location
- Place tests in `/home/bigeug/myDREAMS/tests/`
- Mirror the source structure: `apps/property-api/` -> `tests/apps/property-api/`
- Use `test_` prefix for test files

### 2. Test Structure
```python
"""Tests for [module name]."""
import pytest
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Fixtures
@pytest.fixture
def sample_data():
    """Provide sample test data."""
    return {...}

# Test classes group related tests
class TestClassName:
    """Tests for ClassName."""

    def test_method_success(self):
        """Test successful case."""
        pass

    def test_method_edge_case(self):
        """Test edge case."""
        pass

    def test_method_error(self):
        """Test error handling."""
        with pytest.raises(ValueError):
            pass
```

### 3. Test Naming
- `test_<function>_<scenario>` format
- Be descriptive: `test_score_calculation_with_empty_activities`
- Include positive, negative, and edge cases

### 4. Database Tests
Use in-memory SQLite for database tests:
```python
@pytest.fixture
def test_db():
    """Create in-memory test database."""
    from src.core.database import DREAMSDatabase
    db = DREAMSDatabase(":memory:")
    yield db
    # Cleanup happens automatically
```

### 5. API Tests
Use Flask test client:
```python
@pytest.fixture
def client():
    """Create test client."""
    from apps.property_api.app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_endpoint(client):
    """Test API endpoint."""
    response = client.get('/api/v1/properties')
    assert response.status_code == 200
```

### 6. Mocking
Use pytest-mock or unittest.mock:
```python
def test_external_api(mocker):
    """Test with mocked external API."""
    mock_response = mocker.patch('requests.get')
    mock_response.return_value.json.return_value = {'data': []}
    # Test code here
```

### 7. Coverage Goals
- Aim for 80%+ coverage on new code
- Focus on business logic (scoring, matching)
- Test error paths explicitly

### 8. Run Tests
```bash
cd /home/bigeug/myDREAMS
pytest tests/ -v --cov=src --cov=apps
```

## Workflow

1. **Analyze** the code to test
2. **Identify** key functions and edge cases
3. **Create** test file with proper structure
4. **Write** tests for happy path first
5. **Add** edge cases and error handling tests
6. **Run** tests to verify they pass
7. **Report** coverage results

## Example Output

When asked "Write tests for the database module", you should:

1. Read `/home/bigeug/myDREAMS/src/core/database.py`
2. Create `/home/bigeug/myDREAMS/tests/src/core/test_database.py`
3. Write tests for key methods:
   - `get_lead()`
   - `upsert_lead()`
   - `get_properties()`
   - Score calculations
4. Run pytest and report results
