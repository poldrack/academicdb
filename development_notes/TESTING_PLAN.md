# Comprehensive Testing Plan for Academic Database Application (Existing Codebase)

## Executive Summary
This document outlines a pragmatic approach to retrofit comprehensive testing to an existing Django academic database application, targeting 80%+ test coverage while minimizing disruption to current functionality.

## Testing Philosophy for Legacy Code
- **Characterization Testing**: Document current behavior before making changes
- **Risk-Based Priority**: Test critical paths and high-risk areas first
- **Regression Prevention**: Capture current functionality to prevent breakage
- **Incremental Coverage**: Build tests gradually without stopping feature development
- **Production-Informed**: Use real usage patterns to guide test scenarios

## 1. Test Infrastructure Setup

### 1.1 Test Configuration
```python
# settings/test.py
from .base import *

# Use SQLite for speed in most tests
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Separate PostgreSQL config for specific tests
DATABASES_POSTGRES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'test_academicdb',
        'USER': 'test_user',
        'PASSWORD': 'test_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Disable migrations for speed
class DisableMigrations:
    def __contains__(self, item):
        return True
    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()

# Mock external APIs by default
MOCK_EXTERNAL_APIS = True

# Use sandbox APIs for integration tests
ORCID_API_URL = 'https://sandbox.orcid.org'
SCOPUS_API_URL = 'https://api-sandbox.elsevier.com'
```

### 1.2 Dependencies
```toml
# pyproject.toml
[tool.poetry.dev-dependencies]
pytest = "^7.4"
pytest-django = "^4.5"
pytest-cov = "^4.1"
pytest-xdist = "^3.3"  # Parallel execution
pytest-benchmark = "^4.0"
factory-boy = "^3.3"
faker = "^19.0"
responses = "^0.23"  # Mock HTTP responses
freezegun = "^1.2"  # Time mocking
model-bakery = "^1.15"
```

### 1.3 Test Structure
```
tests/
├── conftest.py              # Shared fixtures
├── factories.py             # Model factories
├── fixtures/                # Static test data
│   ├── orcid_response.json
│   ├── scopus_response.json
│   └── crossref_response.json
├── unit/
│   ├── models/
│   ├── utils/
│   └── validators/
├── integration/
│   ├── api/
│   ├── auth/
│   └── sync/
├── e2e/
│   └── user_workflows/
└── performance/
    └── load_tests/
```

## 2. Test Fixtures and Factories

### 2.1 Core Fixtures
```python
# tests/conftest.py
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

@pytest.fixture
def academic_user(db):
    """Create a basic academic user"""
    return User.objects.create_user(
        username='test_user',
        orcid_id='0000-0000-0000-0001',
        email='test@example.com'
    )

@pytest.fixture
def api_client():
    """Unauthenticated API client"""
    return APIClient()

@pytest.fixture
def authenticated_client(api_client, academic_user):
    """Authenticated API client"""
    api_client.force_authenticate(user=academic_user)
    return api_client

@pytest.fixture
def mock_external_apis(monkeypatch):
    """Mock all external API calls"""
    monkeypatch.setattr('academic.services.orcid.fetch_publications', lambda x: [])
    monkeypatch.setattr('academic.services.scopus.search', lambda x: [])
    return monkeypatch
```

### 2.2 Model Factories
```python
# tests/factories.py
import factory
from factory.django import DjangoModelFactory
from academic.models import Publication, AcademicUser

class AcademicUserFactory(DjangoModelFactory):
    class Meta:
        model = AcademicUser

    username = factory.Sequence(lambda n: f'user_{n}')
    orcid_id = factory.Faker('bothify', text='####-####-####-####')
    email = factory.Faker('email')
    institution = factory.Faker('company')

class PublicationFactory(DjangoModelFactory):
    class Meta:
        model = Publication

    owner = factory.SubFactory(AcademicUserFactory)
    title = factory.Faker('sentence', nb_words=10)
    doi = factory.Sequence(lambda n: f'10.1234/test.{n}')
    year = factory.Faker('year')
    journal = factory.Faker('company')
    authors = factory.LazyFunction(
        lambda: [{'name': faker.name(), 'orcid': None} for _ in range(3)]
    )
    metadata = factory.Dict({
        'abstract': factory.Faker('text'),
        'keywords': factory.List([factory.Faker('word') for _ in range(5)])
    })
```

## 3. Unit Tests (60% of tests)

### 3.1 Model Tests
```python
# tests/unit/models/test_publication.py
import pytest
from django.db import IntegrityError

class TestPublicationModel:
    def test_unique_doi_per_user(self, academic_user):
        """DOI should be unique per user"""
        Publication.objects.create(owner=academic_user, doi='10.1234/test')
        with pytest.raises(IntegrityError):
            Publication.objects.create(owner=academic_user, doi='10.1234/test')

    def test_edit_tracking(self, publication):
        """Manual edits should be tracked"""
        publication.update_field('title', 'New Title', is_manual=True)
        assert publication.manual_edits['title'] is True
        assert len(publication.edit_history) == 1

    def test_metadata_json_field(self, publication):
        """JSONB field should store complex data"""
        publication.metadata = {'nested': {'data': [1, 2, 3]}}
        publication.save()
        publication.refresh_from_db()
        assert publication.metadata['nested']['data'] == [1, 2, 3]
```

### 3.2 Edit Preservation Logic Tests
```python
# tests/unit/models/test_edit_preservation.py
class TestEditPreservation:
    def test_manual_edit_preserved_during_sync(self, publication):
        """Manual edits should not be overwritten by API sync"""
        original_title = publication.title
        publication.update_field('title', 'Manual Edit', is_manual=True)

        # Simulate API sync with different title
        api_data = {'title': 'API Title', 'year': 2024}
        publication.sync_from_api(api_data)

        assert publication.title == 'Manual Edit'  # Preserved
        assert publication.year == 2024  # Updated

    def test_edit_history_maintained(self, publication):
        """All edits should be logged in history"""
        publication.update_field('title', 'Edit 1')
        publication.update_field('title', 'Edit 2', is_manual=True)

        assert len(publication.edit_history) == 2
        assert publication.edit_history[-1]['field'] == 'title'
        assert publication.edit_history[-1]['is_manual'] is True
```

### 3.3 Utility Function Tests
```python
# tests/unit/utils/test_doi_utils.py
from academic.utils import normalize_doi, validate_doi

class TestDOIUtils:
    @pytest.mark.parametrize('input_doi,expected', [
        ('10.1234/test', '10.1234/test'),
        ('https://doi.org/10.1234/test', '10.1234/test'),
        ('DOI:10.1234/test', '10.1234/test'),
    ])
    def test_normalize_doi(self, input_doi, expected):
        assert normalize_doi(input_doi) == expected

    def test_validate_doi_format(self):
        assert validate_doi('10.1234/valid.doi') is True
        assert validate_doi('invalid-doi') is False
```

## 4. Integration Tests (30% of tests)

### 4.1 API Endpoint Tests
```python
# tests/integration/api/test_publications_api.py
import pytest
from rest_framework import status

class TestPublicationsAPI:
    def test_list_user_publications(self, authenticated_client, publication_factory):
        """User should only see their own publications"""
        user_pubs = publication_factory.create_batch(3, owner=authenticated_client.user)
        other_pubs = publication_factory.create_batch(2)  # Different owner

        response = authenticated_client.get('/api/publications/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3

    def test_create_publication_with_validation(self, authenticated_client):
        """API should validate publication data"""
        data = {
            'title': 'Test Publication',
            'doi': '10.1234/test',
            'year': 2024,
            'authors': [{'name': 'Test Author'}]
        }
        response = authenticated_client.post('/api/publications/', data)
        assert response.status_code == status.HTTP_201_CREATED
        assert Publication.objects.filter(doi='10.1234/test').exists()
```

### 4.2 External API Sync Tests
```python
# tests/integration/sync/test_orcid_sync.py
import responses

class TestORCIDSync:
    @responses.activate
    def test_sync_orcid_publications(self, academic_user, orcid_response_fixture):
        """Test syncing publications from ORCID API"""
        responses.add(
            responses.GET,
            f'https://api.orcid.org/v3.0/{academic_user.orcid_id}/works',
            json=orcid_response_fixture,
            status=200
        )

        sync_orcid_publications(academic_user)

        assert Publication.objects.filter(owner=academic_user).count() == 5
        pub = Publication.objects.first()
        assert pub.metadata['source'] == 'orcid'
```

### 4.3 Authentication Tests
```python
# tests/integration/auth/test_orcid_auth.py
class TestORCIDAuthentication:
    def test_orcid_login_creates_user(self, client, mock_orcid_oauth):
        """ORCID login should create user if not exists"""
        response = client.post('/auth/orcid/callback/', {
            'code': 'auth_code',
            'state': 'test_state'
        })

        assert User.objects.filter(orcid_id='0000-0000-0000-0001').exists()
        assert response.status_code == 302  # Redirect to dashboard

    def test_requires_authentication(self, api_client):
        """API endpoints should require authentication"""
        response = api_client.get('/api/publications/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
```

## 5. End-to-End Tests (10% of tests)

### 5.1 User Workflow Tests
```python
# tests/e2e/user_workflows/test_publication_management.py
from django.test import LiveServerTestCase
from selenium import webdriver

class TestPublicationManagementFlow(LiveServerTestCase):
    def setUp(self):
        self.browser = webdriver.Chrome()

    def test_complete_publication_workflow(self):
        """Test full workflow: login -> add publication -> edit -> export"""
        # Login via ORCID
        self.browser.get(f'{self.live_server_url}/login/')
        self.browser.find_element_by_id('orcid-login').click()

        # Add publication
        self.browser.find_element_by_id('add-publication').click()
        self.browser.find_element_by_name('title').send_keys('Test Pub')
        self.browser.find_element_by_name('doi').send_keys('10.1234/test')
        self.browser.find_element_by_id('submit').click()

        # Verify publication appears
        assert 'Test Pub' in self.browser.page_source
```

## 6. Performance Tests

### 6.1 Load Tests
```python
# tests/performance/test_load.py
import pytest
from django.test import TestCase

class TestPerformance(TestCase):
    @pytest.mark.benchmark
    def test_search_performance_with_1000_publications(self, benchmark):
        """Search should complete within 500ms with 1000 publications"""
        PublicationFactory.create_batch(1000)

        result = benchmark(
            Publication.objects.search,
            query='test'
        )
        assert result.time < 0.5

    def test_concurrent_user_isolation(self):
        """Test 50 concurrent users don't see each other's data"""
        users = [AcademicUserFactory() for _ in range(50)]

        # Create publications for each user in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for user in users:
                future = executor.submit(
                    PublicationFactory.create_batch,
                    10, owner=user
                )
                futures.append(future)

            # Wait for all to complete
            for future in futures:
                future.result()

        # Verify isolation
        for user in users:
            pubs = Publication.objects.filter(owner=user)
            assert pubs.count() == 10
```

## 7. Test Execution Strategy

### 7.1 Test Commands
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=academic --cov=academicdb_web --cov-report=html

# Run specific test categories
uv run pytest tests/unit/  # Fast, run frequently
uv run pytest tests/integration/  # Medium speed
uv run pytest tests/e2e/ --liveserver  # Slow, run on CI

# Parallel execution
uv run pytest -n 4  # Use 4 cores

# Run PostgreSQL-specific tests
uv run pytest -m postgres --database=postgres

# Performance tests
uv run pytest tests/performance/ --benchmark-only
```

### 7.2 Continuous Integration
```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync

      - name: Run tests
        run: |
          uv run pytest --cov --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## 8. Testing Strategy for Existing Code

### Phase 0: Discovery and Analysis (Week 1)
1. **Code Coverage Analysis**
   ```bash
   # Generate initial coverage report to identify gaps
   uv run pytest --cov=academic --cov=academicdb_web --cov-report=html
   # Review HTML report to identify untested code paths
   ```

2. **Critical Path Identification**
   - Map user journeys through production logs
   - Identify most-used features from analytics
   - Document business-critical workflows
   - Review recent bug reports for problem areas

3. **Dependency Mapping**
   - Document external API dependencies
   - Map database relationships
   - Identify shared state and side effects

### Phase 1: Characterization Tests (Weeks 2-3)
**Goal: Lock in current behavior to prevent regressions**

1. **Golden Master Tests**
   ```python
   # tests/characterization/test_current_behavior.py
   def test_publication_sync_current_behavior(production_data_snapshot):
       """Document exactly how sync currently works"""
       # Use production data snapshot
       user = create_user_from_snapshot(production_data_snapshot)

       # Capture current behavior
       with record_http_calls() as recorder:
           result = sync_publications(user)

       # Save as golden master
       save_golden_master('sync_publications', result, recorder.calls)

       # Future tests compare against this baseline
       assert result == load_golden_master('sync_publications')
   ```

2. **Snapshot Testing for Complex Objects**
   ```python
   def test_cv_generation_snapshot():
       """Capture current CV output format"""
       publication = Publication.objects.get(pk=1)
       cv_output = generate_cv_entry(publication)
       assert cv_output == snapshot  # Using pytest-snapshot
   ```

### Phase 2: High-Risk Area Testing (Weeks 3-4)
**Goal: Secure critical business logic and security boundaries**

1. **User Data Isolation** (CRITICAL)
   ```python
   def test_user_cannot_access_other_user_data():
       """Existing code test - verify isolation works"""
       user1 = AcademicUser.objects.get(orcid_id='0000-0000-0000-0001')
       user2 = AcademicUser.objects.get(orcid_id='0000-0000-0000-0002')

       # Test all endpoints with user1's auth
       client = APIClient()
       client.force_authenticate(user=user1)

       # Should not see user2's publications
       response = client.get(f'/api/publications/?owner={user2.id}')
       assert response.status_code == 403 or len(response.data) == 0
   ```

2. **Edit Preservation Logic** (CRITICAL)
   ```python
   def test_manual_edits_preserved_in_production():
       """Test existing edit preservation behavior"""
       # Create publication with actual production data
       pub = Publication.objects.create(**production_publication_data)

       # Simulate what happens in production
       pub.title = "Manual Edit"
       pub.manual_edits['title'] = True
       pub.save()

       # Run actual sync code
       sync_from_external_api(pub)

       # Verify current behavior is preserved
       assert pub.title == "Manual Edit"
   ```

### Phase 3: Regression Test Suite (Weeks 4-5)
**Goal: Prevent breaking changes to existing features**

1. **API Contract Tests**
   ```python
   # tests/regression/test_api_contracts.py
   class TestExistingAPIContracts:
       """Test that existing API behavior doesn't change"""

       def test_publication_list_format(self, live_api_client):
           """Ensure API response format matches production"""
           response = live_api_client.get('/api/publications/')

           # These assertions based on current production behavior
           assert 'results' in response.data
           assert 'count' in response.data
           assert 'next' in response.data

           if response.data['results']:
               pub = response.data['results'][0]
               required_fields = ['id', 'title', 'doi', 'year', 'authors']
               for field in required_fields:
                   assert field in pub
   ```

2. **Database Migration Tests**
   ```python
   def test_migrations_are_reversible():
       """Ensure all migrations can be applied and reversed"""
       call_command('migrate', 'academic', '0001_initial')
       call_command('migrate', 'academic')
       call_command('migrate', 'academic', '0001_initial')
   ```

### Phase 4: Integration Testing (Weeks 5-6)
**Goal: Test interactions with external systems**

1. **Record and Replay External APIs**
   ```python
   # tests/integration/test_with_recorded_responses.py
   @pytest.mark.vcr()  # Records HTTP interactions
   def test_orcid_sync_with_real_api():
       """Test with recorded real API responses"""
       user = AcademicUser.objects.get(orcid_id='0000-0000-0000-0001')

       # First run records the API calls
       # Subsequent runs use the recording
       publications = sync_orcid_publications(user)

       assert len(publications) > 0
       assert all(p.owner == user for p in publications)
   ```

2. **Mutation Testing** (Optional but valuable)
   ```bash
   # Use mutmut to verify test quality
   uv run mutmut run --paths-to-mutate academic/models.py
   uv run mutmut results
   ```

## 9. Success Metrics

- **Code Coverage**: Achieve 80%+ overall, 90%+ for critical paths
- **Test Speed**: Unit tests < 5 seconds, integration < 30 seconds
- **Reliability**: Zero flaky tests in CI
- **Performance**: All API endpoints < 200ms p95
- **Security**: All user data isolation tests passing

## 10. Working with Existing Code

### Strategies for Untested Code

1. **Extract and Test**
   ```python
   # Before: Untested complex method
   def sync_publication(self):
       # 100 lines of complex logic...

   # After: Extract testable pieces
   def sync_publication(self):
       api_data = self._fetch_from_api()
       normalized = self._normalize_data(api_data)
       return self._save_if_changed(normalized)

   # Now each piece can be tested independently
   ```

2. **Seam Testing**
   ```python
   # Add test seams to existing code
   class PublicationSync:
       def __init__(self, api_client=None):
           self.api_client = api_client or RealAPIClient()

       # Now we can inject a test double
   ```

3. **Approval Testing for Complex Output**
   ```python
   def test_complex_report_generation():
       """Use approval testing for complex outputs"""
       report = generate_annual_report(2024)

       # First run: manually verify and approve
       # Future runs: compare against approved version
       verify(report, reporter=DiffReporter())
   ```

### Dealing with Technical Debt

1. **Document Debt as Tests**
   ```python
   @pytest.mark.xfail(reason="Known bug: duplicate DOIs allowed")
   def test_doi_uniqueness():
       """This SHOULD pass but doesn't due to technical debt"""
       # When fixed, remove xfail marker
   ```

2. **Refactoring Under Test Coverage**
   ```python
   # Step 1: Add characterization tests
   def test_current_behavior():
       """Lock in current behavior before refactoring"""
       result = legacy_function(test_input)
       assert result == known_output

   # Step 2: Refactor with confidence
   # Step 3: Update tests to reflect improved behavior
   ```

## 11. Tooling for Legacy Code Testing

### Essential Tools
```toml
[tool.poetry.dev-dependencies]
# Coverage and mutation testing
coverage = "^7.0"
pytest-cov = "^4.0"
mutmut = "^2.4"

# Snapshot and approval testing
pytest-snapshot = "^0.9"
approvaltests = "^8.0"

# HTTP mocking and recording
vcrpy = "^5.0"
responses = "^0.23"

# Test data generation from production
faker = "^19.0"
factory-boy = "^3.3"
pytest-factoryboy = "^2.5"

# Performance profiling
pytest-profiling = "^1.7"
memory-profiler = "^0.60"
```

### Coverage Improvement Workflow
```bash
# 1. Find untested code
uv run coverage run -m pytest
uv run coverage html
open htmlcov/index.html

# 2. Generate test stubs
uv run pytest --co -q | grep -E "test_.*\.py" > test_inventory.txt

# 3. Track progress
uv run coverage report --skip-covered --show-missing

# 4. Focus on critical paths
uv run coverage report --include="*/models.py,*/views.py" --fail-under=80
```

## 12. Maintenance

### Quick Wins for Immediate Coverage

1. **Low-Hanging Fruit** (Week 1)
   - Simple utility functions
   - Data validation methods
   - Model properties and computed fields
   - Template tags and filters

2. **Critical Path Focus** (Week 2)
   - Authentication flows
   - User data access controls
   - Payment/billing logic (if applicable)
   - Data export functions

3. **Automated Test Generation**
   ```bash
   # Use hypothesis for property-based testing
   from hypothesis import given, strategies as st

   @given(st.integers(min_value=1900, max_value=2100))
   def test_publication_year_validation(year):
       """Auto-generate test cases for year validation"""
       pub = Publication(year=year)
       if 1900 <= year <= datetime.now().year + 1:
           pub.full_clean()  # Should not raise
       else:
           with pytest.raises(ValidationError):
               pub.full_clean()
   ```

## Appendix A: Testing Anti-Patterns to Avoid

1. **Don't Test Framework Code**
   ```python
   # Bad: Testing Django's ORM
   def test_save_works():
       pub = Publication()
       pub.save()
       assert pub.id is not None  # Django already tests this
   ```

2. **Don't Mock What You Don't Own**
   ```python
   # Bad: Mocking third-party library internals
   @mock.patch('requests.Session.send')

   # Good: Mock at your boundary
   @mock.patch('academic.services.external_api.fetch')
   ```

3. **Avoid Brittle Tests**
   ```python
   # Bad: Testing implementation details
   assert str(publication) == "Publication: Test Article (2024)"

   # Good: Test behavior
   assert "Test Article" in str(publication)
   assert "2024" in str(publication)
   ```

## Appendix B: Prioritization Matrix

| Component | Risk | Usage | Current Coverage | Priority |
|-----------|------|-------|------------------|----------|
| User Authentication | HIGH | HIGH | 0% | 1 |
| Data Isolation | HIGH | HIGH | 0% | 1 |
| Publication CRUD | MED | HIGH | 33% | 2 |
| External API Sync | MED | MED | 0% | 3 |
| CV Generation | LOW | MED | 0% | 4 |
| Admin Interface | LOW | LOW | 0% | 5 |