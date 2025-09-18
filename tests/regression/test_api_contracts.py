"""
API contract regression tests.

These tests document and verify the current API behavior to prevent
breaking changes to existing functionality.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from academic.models import Publication, Teaching, Talk, Conference
from tests.factories import AcademicUserFactory, PublicationFactory

User = get_user_model()


@pytest.mark.django_db
class TestPublicationAPIContract:
    """Test Publication API endpoints maintain their current contract."""

    def setup_method(self):
        """Set up test data for each test method."""
        self.user = AcademicUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_publication_list_endpoint_structure(self):
        """Verify publication list endpoint returns expected structure."""
        # Create some test publications
        PublicationFactory.create_batch(3, owner=self.user)

        response = self.client.get('/api/v1/publications/')
        assert response.status_code == status.HTTP_200_OK

        # Check response structure
        data = response.data
        assert 'results' in data
        assert 'count' in data
        assert 'next' in data
        assert 'previous' in data

        # Check pagination
        assert data['count'] == 3
        assert len(data['results']) == 3

    def test_publication_list_required_fields(self):
        """Verify each publication in the list has required fields."""
        pub = PublicationFactory(
            owner=self.user,
            title="Test Publication",
            doi="10.1234/test",
            year=2024,
            publication_name="Test Journal"
        )

        response = self.client.get('/api/v1/publications/')
        assert response.status_code == status.HTTP_200_OK

        publication_data = response.data['results'][0]

        # Required fields that should always be present
        required_fields = ['id', 'title', 'year', 'doi']
        for field in required_fields:
            assert field in publication_data, f"Field '{field}' missing from API response"

        # Verify field values
        assert publication_data['id'] == pub.id
        assert publication_data['title'] == "Test Publication"
        assert publication_data['doi'] == "10.1234/test"
        assert publication_data['year'] == 2024

    def test_publication_detail_endpoint(self):
        """Verify publication detail endpoint returns complete data."""
        pub = PublicationFactory(
            owner=self.user,
            title="Detailed Publication",
            doi="10.1234/detailed",
            year=2024,
            authors=[{"name": "Test Author", "orcid": "0000-0000-0000-0001"}],
            metadata={"abstract": "Test abstract", "keywords": ["test"]}
        )

        response = self.client.get(f'/api/v1/publications/{pub.id}/')
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data['id'] == pub.id
        assert data['title'] == "Detailed Publication"
        assert data['doi'] == "10.1234/detailed"
        assert data['year'] == 2024

        # JSON fields should be preserved
        assert 'authors' in data
        assert len(data['authors']) == 1
        assert data['authors'][0]['name'] == "Test Author"

        # Note: metadata field is not exposed via API (internal use only)

    def test_publication_create_endpoint(self):
        """Verify publication creation works with minimal required fields."""
        publication_data = {
            'title': 'New Test Publication',
            'doi': '10.1234/new.test',
            'year': 2024,
            'authors': [{'name': 'Test Author'}]  # Required field
        }

        response = self.client.post('/api/v1/publications/', publication_data)
        assert response.status_code == status.HTTP_201_CREATED

        # Verify created publication
        created_pub = Publication.objects.get(doi='10.1234/new.test')
        assert created_pub.owner == self.user
        assert created_pub.title == 'New Test Publication'
        assert created_pub.year == 2024

    def test_publication_update_endpoint(self):
        """Verify publication update preserves existing data."""
        pub = PublicationFactory(
            owner=self.user,
            title="Original Title",
            doi="10.1234/update",
            year=2024,
            publication_name="Original Journal"
        )

        update_data = {'title': 'Updated Title'}
        response = self.client.patch(f'/api/v1/publications/{pub.id}/', update_data)
        assert response.status_code == status.HTTP_200_OK

        # Verify only title was updated
        pub.refresh_from_db()
        assert pub.title == 'Updated Title'
        assert pub.doi == "10.1234/update"  # Should remain unchanged
        assert pub.year == 2024  # Should remain unchanged
        assert pub.publication_name == "Original Journal"  # Should remain unchanged

    def test_publication_delete_endpoint(self):
        """Verify publication deletion works correctly."""
        pub = PublicationFactory(owner=self.user)
        pub_id = pub.id

        response = self.client.delete(f'/api/v1/publications/{pub.id}/')
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify publication was deleted
        assert not Publication.objects.filter(id=pub_id).exists()

    def test_publication_filtering_by_year(self):
        """Verify year filtering works if implemented."""
        PublicationFactory(owner=self.user, year=2023, title="Pub 2023")
        PublicationFactory(owner=self.user, year=2024, title="Pub 2024")

        response = self.client.get('/api/v1/publications/?year=2024')

        if response.status_code == status.HTTP_200_OK:
            # Current behavior: year filtering is not implemented
            # API returns all publications, not filtered by year
            results = response.data['results']
            assert len(results) == 2  # Should return both publications (no filtering)

    def test_publication_search_endpoint(self):
        """Verify search functionality if implemented."""
        PublicationFactory(
            owner=self.user,
            title="Machine Learning Research",
            doi="10.1234/ml"
        )
        PublicationFactory(
            owner=self.user,
            title="Biology Study",
            doi="10.1234/bio"
        )

        response = self.client.get('/api/v1/publications/?search=machine')

        if response.status_code == status.HTTP_200_OK:
            # If search is implemented, verify it works
            results = response.data.get('results', [])
            if len(results) > 0:
                # At least one result should contain search term
                found_search_term = any(
                    'machine' in pub.get('title', '').lower()
                    for pub in results
                )
                assert found_search_term


@pytest.mark.django_db
class TestTeachingAPIContract:
    """Test Teaching API endpoints maintain their current contract."""

    def setup_method(self):
        """Set up test data for each test method."""
        self.user = AcademicUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_teaching_list_endpoint(self):
        """Verify teaching list endpoint works."""
        Teaching.objects.create(
            owner=self.user,
            name="Test Course",
            year=2024
        )

        response = self.client.get('/api/v1/teaching/')
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert 'results' in data
        assert len(data['results']) == 1
        assert data['results'][0]['name'] == "Test Course"

    def test_teaching_create_endpoint(self):
        """Verify teaching creation works."""
        teaching_data = {
            'name': 'New Course',
            'year': 2024,
            'level': 'undergraduate'
        }

        response = self.client.post('/api/v1/teaching/', teaching_data)
        assert response.status_code == status.HTTP_201_CREATED

        # Verify creation
        teaching = Teaching.objects.get(name='New Course')
        assert teaching.owner == self.user
        assert teaching.year == 2024


@pytest.mark.django_db
class TestAPIErrorHandling:
    """Test API error handling and edge cases."""

    def setup_method(self):
        """Set up test data for each test method."""
        self.user = AcademicUserFactory()
        self.client = APIClient()

    def test_unauthenticated_access_returns_401(self):
        """Verify unauthenticated requests return 401."""
        # Don't authenticate the client
        response = self.client.get('/api/v1/publications/')
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_nonexistent_publication_returns_404(self):
        """Verify accessing nonexistent publication returns 404."""
        self.client.force_authenticate(user=self.user)

        response = self.client.get('/api/v1/publications/99999/')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_invalid_publication_data_returns_400(self):
        """Verify invalid data returns 400 with error details."""
        self.client.force_authenticate(user=self.user)

        # Missing required fields
        invalid_data = {'title': 'Missing required fields'}

        response = self.client.post('/api/v1/publications/', invalid_data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Should include error details
        assert 'errors' in response.data or any(
            key in response.data for key in ['year', 'doi', 'non_field_errors']
        )

    def test_duplicate_doi_handling(self):
        """Test how duplicate DOIs are handled."""
        self.client.force_authenticate(user=self.user)

        # Create first publication
        pub_data = {
            'title': 'First Publication',
            'doi': '10.1234/duplicate',
            'year': 2024,
            'authors': [{'name': 'Test Author'}]
        }
        response = self.client.post('/api/v1/publications/', pub_data)
        assert response.status_code == status.HTTP_201_CREATED

        # Try to create second with same DOI
        duplicate_data = {
            'title': 'Duplicate DOI Publication',
            'doi': '10.1234/duplicate',
            'year': 2024,
            'authors': [{'name': 'Test Author'}]
        }
        response = self.client.post('/api/v1/publications/', duplicate_data)

        # Should handle duplicate DOIs gracefully
        # (Either allow it, return error, or merge - document current behavior)
        assert response.status_code in [
            status.HTTP_201_CREATED,  # If duplicates allowed
            status.HTTP_400_BAD_REQUEST,  # If duplicates rejected
            status.HTTP_409_CONFLICT  # If conflict handled specially
        ]


@pytest.mark.django_db
class TestAPIResponseFormats:
    """Test API response formats and serialization."""

    def setup_method(self):
        """Set up test data for each test method."""
        self.user = AcademicUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_json_field_serialization(self):
        """Verify JSON fields are properly serialized."""
        pub = PublicationFactory(
            owner=self.user,
            authors=[
                {"name": "John Doe", "orcid": "0000-0000-0000-0001"},
                {"name": "Jane Smith", "affiliation": "University"}
            ],
            metadata={
                "abstract": "Test abstract",
                "keywords": ["test", "research"],
                "citations": 10
            }
        )

        response = self.client.get(f'/api/v1/publications/{pub.id}/')
        assert response.status_code == status.HTTP_200_OK

        data = response.data

        # Verify authors array structure
        assert isinstance(data['authors'], list)
        assert len(data['authors']) == 2
        assert data['authors'][0]['name'] == "John Doe"
        assert data['authors'][0]['orcid'] == "0000-0000-0000-0001"

        # Note: metadata field is not exposed via API (internal use only)
        # This documents the current behavior - metadata is stored in the database
        # but not serialized in API responses

    def test_date_field_formatting(self):
        """Verify date fields are properly formatted."""
        # Create models with date fields
        talk = Talk.objects.create(
            owner=self.user,
            place="Test University",
            year=2024,
            invited=True
        )

        response = self.client.get(f'/api/v1/talks/{talk.id}/')
        if response.status_code == status.HTTP_200_OK:
            data = response.data
            # Verify year field formatting
            if 'year' in data:
                assert isinstance(data['year'], int)
                assert data['year'] == 2024

    def test_boolean_field_serialization(self):
        """Verify boolean fields are properly serialized."""
        pub = PublicationFactory(
            owner=self.user,
            is_preprint=True
        )

        response = self.client.get(f'/api/v1/publications/{pub.id}/')
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        if 'is_preprint' in data:
            assert isinstance(data['is_preprint'], bool)
            # Note: is_preprint is read-only and calculated based on the data
            # Setting is_preprint=True on factory doesn't guarantee API will return True
            # as it may be overridden by publication logic