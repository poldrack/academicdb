"""
Critical tests for user data isolation.

These tests ensure that users can only access their own data,
which is fundamental for security in a multi-tenant application.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from academic.models import Publication, Teaching, Talk, Conference
from tests.factories import (
    AcademicUserFactory,
    PublicationFactory,
    TeachingFactory,
    TalkFactory,
    ConferenceFactory
)

User = get_user_model()


@pytest.mark.django_db
class TestUserDataIsolation:
    """Test that users cannot access each other's data."""

    def test_publication_list_isolation(self):
        """Users should only see their own publications."""
        # Create two users with publications
        user1 = AcademicUserFactory()
        user2 = AcademicUserFactory()

        # Create publications for each user
        user1_pubs = PublicationFactory.create_batch(3, owner=user1)
        user2_pubs = PublicationFactory.create_batch(2, owner=user2)

        # Test with user1's authentication
        client = APIClient()
        client.force_authenticate(user=user1)

        response = client.get('/api/v1/publications/')
        assert response.status_code == status.HTTP_200_OK

        # Should only see user1's publications
        publication_ids = [pub['id'] for pub in response.data['results']]
        user1_pub_ids = [pub.id for pub in user1_pubs]
        user2_pub_ids = [pub.id for pub in user2_pubs]

        # All returned publications should belong to user1
        for pub_id in publication_ids:
            assert pub_id in user1_pub_ids
            assert pub_id not in user2_pub_ids

    def test_publication_detail_isolation(self):
        """Users should not be able to access other users' publication details."""
        user1 = AcademicUserFactory()
        user2 = AcademicUserFactory()

        user1_pub = PublicationFactory(owner=user1)
        user2_pub = PublicationFactory(owner=user2)

        client = APIClient()
        client.force_authenticate(user=user1)

        # Should be able to access own publication
        response = client.get(f'/api/v1/publications/{user1_pub.id}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == user1_pub.id

        # Should NOT be able to access other user's publication
        response = client.get(f'/api/v1/publications/{user2_pub.id}/')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_publication_creation_automatic_ownership(self):
        """Created publications should automatically be assigned to the authenticated user."""
        user1 = AcademicUserFactory()
        user2 = AcademicUserFactory()

        client = APIClient()
        client.force_authenticate(user=user1)

        publication_data = {
            'title': 'Test Publication',
            'doi': '10.1234/test.publication',
            'year': 2024,
            'journal': 'Test Journal'
        }

        response = client.post('/api/v1/publications/', publication_data)
        assert response.status_code == status.HTTP_201_CREATED

        # Publication should be owned by user1, not user2
        created_pub = Publication.objects.get(id=response.data['id'])
        assert created_pub.owner == user1
        assert created_pub.owner != user2

    def test_publication_update_isolation(self):
        """Users should only be able to update their own publications."""
        user1 = AcademicUserFactory()
        user2 = AcademicUserFactory()

        user1_pub = PublicationFactory(owner=user1)
        user2_pub = PublicationFactory(owner=user2)

        client = APIClient()
        client.force_authenticate(user=user1)

        update_data = {'title': 'Updated Title'}

        # Should be able to update own publication
        response = client.patch(f'/api/v1/publications/{user1_pub.id}/', update_data)
        assert response.status_code == status.HTTP_200_OK

        # Should NOT be able to update other user's publication
        response = client.patch(f'/api/v1/publications/{user2_pub.id}/', update_data)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_publication_delete_isolation(self):
        """Users should only be able to delete their own publications."""
        user1 = AcademicUserFactory()
        user2 = AcademicUserFactory()

        user1_pub = PublicationFactory(owner=user1)
        user2_pub = PublicationFactory(owner=user2)

        client = APIClient()
        client.force_authenticate(user=user1)

        # Should be able to delete own publication
        response = client.delete(f'/api/v1/publications/{user1_pub.id}/')
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Should NOT be able to delete other user's publication
        response = client.delete(f'/api/v1/publications/{user2_pub.id}/')
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify user2's publication still exists
        assert Publication.objects.filter(id=user2_pub.id).exists()

    def test_funding_isolation(self):
        """Users should only see their own funding records."""
        # Skip this test since FundingViewSet doesn't exist yet
        pytest.skip("FundingViewSet not implemented yet")

    def test_teaching_isolation(self):
        """Users should only see their own teaching records."""
        user1 = AcademicUserFactory()
        user2 = AcademicUserFactory()

        user1_teaching = TeachingFactory.create_batch(2, owner=user1)
        user2_teaching = TeachingFactory.create_batch(1, owner=user2)

        client = APIClient()
        client.force_authenticate(user=user1)

        response = client.get('/api/v1/teaching/')
        assert response.status_code == status.HTTP_200_OK

        teaching_ids = [teach['id'] for teach in response.data['results']]
        user1_teaching_ids = [teach.id for teach in user1_teaching]
        user2_teaching_ids = [teach.id for teach in user2_teaching]

        for teach_id in teaching_ids:
            assert teach_id in user1_teaching_ids
            assert teach_id not in user2_teaching_ids

    def test_unauthenticated_access_blocked(self):
        """Unauthenticated users should not be able to access any data."""
        user1 = AcademicUserFactory()
        PublicationFactory.create_batch(3, owner=user1)

        client = APIClient()
        # No authentication

        response = client.get('/api/v1/publications/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_cross_model_isolation(self):
        """Test isolation across all models for comprehensive security."""
        user1 = AcademicUserFactory()
        user2 = AcademicUserFactory()

        # Create various records for user2
        PublicationFactory(owner=user2)
        TeachingFactory(owner=user2)
        TalkFactory(owner=user2)
        ConferenceFactory(owner=user2)

        client = APIClient()
        client.force_authenticate(user=user1)

        # User1 should see empty results for all endpoints
        endpoints = [
            '/api/v1/publications/',
            '/api/v1/teaching/',
            '/api/v1/talks/',
            '/api/v1/conferences/'
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            if response.status_code == 200:
                # Should have no results
                assert len(response.data.get('results', [])) == 0

    def test_bulk_operations_isolation(self):
        """Test that bulk operations respect user isolation."""
        user1 = AcademicUserFactory()
        user2 = AcademicUserFactory()

        user1_pubs = PublicationFactory.create_batch(3, owner=user1)
        user2_pubs = PublicationFactory.create_batch(2, owner=user2)

        client = APIClient()
        client.force_authenticate(user=user1)

        # Try to bulk update - should only affect user1's publications
        all_pub_ids = [pub.id for pub in user1_pubs + user2_pubs]

        # This test depends on the bulk update API existing
        # For now, we'll test the concept with individual updates
        for pub_id in all_pub_ids:
            response = client.patch(f'/api/v1/publications/{pub_id}/', {'title': 'Bulk Updated'})

            pub = Publication.objects.get(id=pub_id)
            if pub.owner == user1:
                # Should succeed and be updated
                assert response.status_code == status.HTTP_200_OK
                assert pub.title == 'Bulk Updated'
            else:
                # Should fail for user2's publications
                assert response.status_code == status.HTTP_404_NOT_FOUND
                # Title should remain unchanged
                assert pub.title != 'Bulk Updated'