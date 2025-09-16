"""
Test configuration and fixtures for the academic database application.
"""
import pytest
import django
from django.conf import settings

# Configure Django settings if not already configured
if not settings.configured:
    django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


@pytest.fixture
def academic_user(db):
    """Create a basic academic user for testing."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        orcid_id='0000-0000-0000-0001',
        institution='Test University',
        department='Computer Science'
    )


@pytest.fixture
def second_academic_user(db):
    """Create a second user for testing isolation."""
    return User.objects.create_user(
        username='testuser2',
        email='test2@example.com',
        orcid_id='0000-0000-0000-0002',
        institution='Another University'
    )


@pytest.fixture
def api_client():
    """Unauthenticated API client."""
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def authenticated_api_client(api_client, academic_user):
    """Authenticated API client."""
    api_client.force_authenticate(user=academic_user)
    return api_client


@pytest.fixture
def web_client():
    """Django test client."""
    return Client()


@pytest.fixture
def authenticated_web_client(web_client, academic_user):
    """Authenticated Django test client."""
    web_client.force_login(academic_user)
    return web_client


@pytest.fixture
def sample_publication(academic_user):
    """Create a sample publication for testing."""
    from academic.models import Publication
    return Publication.objects.create(
        owner=academic_user,
        title="Sample Research Paper",
        doi="10.1234/test.paper.2024",
        year=2024,
        journal="Journal of Test Research",
        authors=[
            {"name": "Test Author", "orcid": "0000-0000-0000-0001"},
            {"name": "Co Author", "orcid": None}
        ],
        metadata={
            "abstract": "This is a test abstract for testing purposes.",
            "keywords": ["testing", "academic", "database"],
            "source": "manual"
        }
    )


@pytest.fixture
def publication_with_manual_edits(academic_user):
    """Create a publication with manual edits for testing edit preservation."""
    from academic.models import Publication
    pub = Publication.objects.create(
        owner=academic_user,
        title="Manually Edited Paper",
        doi="10.1234/manual.edit.2024",
        year=2024,
        journal="Manual Journal",
        manual_edits={"title": True, "journal": True},
        edit_history=[
            {
                "field": "title",
                "old_value": "Original Title",
                "new_value": "Manually Edited Paper",
                "timestamp": "2024-01-01T12:00:00Z",
                "is_manual": True
            }
        ]
    )
    return pub


@pytest.fixture
def batch_publications(academic_user, second_academic_user):
    """Create multiple publications for different users to test isolation."""
    from academic.models import Publication
    user1_pubs = []
    user2_pubs = []

    # Create publications for first user
    for i in range(3):
        pub = Publication.objects.create(
            owner=academic_user,
            title=f"User 1 Paper {i+1}",
            doi=f"10.1234/user1.{i+1}",
            year=2024 - i,
            journal="User 1 Journal"
        )
        user1_pubs.append(pub)

    # Create publications for second user
    for i in range(2):
        pub = Publication.objects.create(
            owner=second_academic_user,
            title=f"User 2 Paper {i+1}",
            doi=f"10.1234/user2.{i+1}",
            year=2023 - i,
            journal="User 2 Journal"
        )
        user2_pubs.append(pub)

    return {
        'user1_publications': user1_pubs,
        'user2_publications': user2_pubs
    }


@pytest.fixture
def mock_external_apis(monkeypatch):
    """Mock all external API calls to prevent network requests in tests."""
    def mock_orcid_fetch(*args, **kwargs):
        return []

    def mock_scopus_search(*args, **kwargs):
        return []

    def mock_pubmed_search(*args, **kwargs):
        return []

    def mock_crossref_works(*args, **kwargs):
        return []

    # Mock the external API functions
    monkeypatch.setattr('academic.services.orcid.fetch_publications', mock_orcid_fetch)
    monkeypatch.setattr('academic.services.scopus.search_publications', mock_scopus_search)
    monkeypatch.setattr('academic.services.pubmed.search_publications', mock_pubmed_search)
    monkeypatch.setattr('academic.services.crossref.works', mock_crossref_works)

    return monkeypatch


@pytest.fixture
def production_like_data(academic_user):
    """Create data that mimics production patterns."""
    from academic.models import Publication
    publications = []

    # Create publications with various metadata patterns
    pub1 = Publication.objects.create(
        owner=academic_user,
        title="Machine Learning in Healthcare: A Systematic Review",
        doi="10.1016/j.jbi.2024.104567",
        year=2024,
        journal="Journal of Biomedical Informatics",
        volume="142",
        page_range="104567",
        authors=[
            {
                "name": academic_user.get_full_name(),
                "orcid": academic_user.orcid_id,
                "scopus_id": "123456789"
            },
            {
                "name": "Jane Smith",
                "orcid": "0000-0001-2345-6789",
                "affiliation": "Stanford University"
            }
        ],
        metadata={
            "abstract": "Machine learning has revolutionized healthcare applications...",
            "keywords": ["machine learning", "healthcare", "systematic review"],
            "pubmed_id": "38123456",
            "scopus_id": "2-s2.0-85123456789",
            "citations": 15,
            "source": "scopus"
        }
    )
    publications.append(pub1)

    # Preprint with manual edits
    pub2 = Publication.objects.create(
        owner=academic_user,
        title="Novel Approach to Data Privacy in Medical AI",
        doi="10.1101/2024.01.15.24301234",
        year=2024,
        journal="bioRxiv",
        is_preprint=True,
        authors=[{"name": academic_user.get_full_name(), "orcid": academic_user.orcid_id}],
        manual_edits={"title": True},
        metadata={
            "abstract": "We present a novel approach to ensuring data privacy...",
            "keywords": ["privacy", "medical AI", "differential privacy"],
            "source": "manual"
        }
    )
    publications.append(pub2)

    return {
        'publications': publications,
        'user': academic_user
    }


# Database fixtures for different test scenarios
@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    """Setup test database with initial data if needed."""
    with django_db_blocker.unblock():
        # Any initial database setup can go here
        pass


@pytest.fixture
def transactional_db(transactional_db):
    """Fixture that enables real database transactions for testing."""
    return transactional_db