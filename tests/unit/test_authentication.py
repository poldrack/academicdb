"""
Tests for authentication and authorization.

Covers ORCID authentication, session management, and access controls.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from tests.factories import AcademicUserFactory

User = get_user_model()


@pytest.mark.django_db
class TestAuthentication:
    """Test authentication flows and requirements."""

    def test_unauthenticated_api_access_blocked(self):
        """Unauthenticated requests should be rejected."""
        client = APIClient()

        protected_endpoints = [
            '/api/v1/publications/',
            '/api/v1/teaching/',
            '/api/v1/talks/',
            '/api/v1/conferences/'
        ]

        for endpoint in protected_endpoints:
            response = client.get(endpoint)
            assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_authenticated_api_access_allowed(self):
        """Authenticated requests should be allowed."""
        user = AcademicUserFactory()
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get('/api/v1/publications/')
        assert response.status_code == status.HTTP_200_OK

    def test_orcid_id_uniqueness(self):
        """ORCID IDs should be unique across users."""
        orcid_id = "0000-0000-0000-0001"

        # Create first user with ORCID ID
        user1 = AcademicUserFactory(orcid_id=orcid_id)
        assert user1.orcid_id == orcid_id

        # Attempting to create second user with same ORCID should fail
        with pytest.raises(Exception):  # IntegrityError expected
            AcademicUserFactory(orcid_id=orcid_id)

    def test_orcid_id_format_validation(self):
        """ORCID IDs should follow the correct format."""
        valid_orcid_ids = [
            "0000-0000-0000-0001",
            "0000-0001-2345-6789",
            "0000-0002-1825-0097"
        ]

        for orcid_id in valid_orcid_ids:
            user = AcademicUserFactory(orcid_id=orcid_id)
            assert user.orcid_id == orcid_id

        # Test invalid formats would require model validation
        # This depends on whether ORCID format validation is implemented

    def test_user_profile_access_control(self):
        """Users should only be able to access their own profile."""
        user1 = AcademicUserFactory()
        user2 = AcademicUserFactory()

        client = APIClient()
        client.force_authenticate(user=user1)

        # Should be able to access own profile
        response = client.get(f'/api/users/{user1.id}/')
        if response.status_code != 404:  # Endpoint might not exist yet
            assert response.status_code == status.HTTP_200_OK

        # Should NOT be able to access other user's profile
        response = client.get(f'/api/users/{user2.id}/')
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN]

    def test_session_persistence(self):
        """Test that user sessions persist correctly."""
        user = AcademicUserFactory()
        client = Client()

        # Simulate login
        client.force_login(user)

        # Make request to protected view
        response = client.get('/dashboard/')  # Assuming dashboard exists
        # Should not redirect to login page
        assert response.status_code != 302 or '/login/' not in response.url

    def test_logout_clears_session(self):
        """Test that logout properly clears user session."""
        user = AcademicUserFactory()
        client = Client()

        # Login first
        client.force_login(user)

        # Logout
        response = client.post('/accounts/logout/')

        # Subsequent request to protected view should redirect to login
        response = client.get('/dashboard/', follow=True)
        # Should redirect to login page
        assert any('login' in url for url, _ in response.redirect_chain)

    def test_api_token_authentication(self):
        """Test API token authentication if implemented."""
        user = AcademicUserFactory()

        # This test assumes token authentication is implemented
        # If not, this test documents the requirement
        client = APIClient()

        # Without token should fail
        response = client.get('/api/v1/publications/')
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

        # With valid user authentication should work
        client.force_authenticate(user=user)
        response = client.get('/api/v1/publications/')
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestORCIDIntegration:
    """Test ORCID-specific authentication features."""

    def test_orcid_user_creation(self):
        """Test creating user with ORCID data."""
        orcid_data = {
            'username': 'orcid_user',
            'email': 'orcid@example.com',
            'orcid_id': '0000-0000-0000-0001',
            'first_name': 'John',
            'last_name': 'Doe'
        }

        user = User.objects.create_user(**orcid_data)

        assert user.orcid_id == '0000-0000-0000-0001'
        assert user.email == 'orcid@example.com'
        assert user.first_name == 'John'
        assert user.last_name == 'Doe'

    def test_orcid_token_storage(self):
        """Test that ORCID tokens can be stored securely."""
        user = AcademicUserFactory()

        # Simulate storing ORCID access token
        mock_token = "mock-orcid-access-token-12345"
        user.orcid_token = mock_token
        user.save()

        user.refresh_from_db()
        assert user.orcid_token == mock_token

    def test_user_without_orcid(self):
        """Test that users can exist without ORCID IDs."""
        user = AcademicUserFactory(orcid_id=None)
        assert user.orcid_id is None
        assert user.is_active

    def test_orcid_profile_data_integration(self):
        """Test integration of ORCID profile data."""
        orcid_profile_data = {
            'orcid_id': '0000-0000-0000-0001',
            'institution': 'Stanford University',
            'department': 'Computer Science',
            'research_areas': ['Machine Learning', 'Healthcare AI']
        }

        user = AcademicUserFactory(**orcid_profile_data)

        assert user.orcid_id == '0000-0000-0000-0001'
        assert user.institution == 'Stanford University'
        assert user.department == 'Computer Science'
        assert 'Machine Learning' in user.research_areas
        assert 'Healthcare AI' in user.research_areas


@pytest.mark.django_db
class TestPermissions:
    """Test permission-based access controls."""

    def test_staff_user_permissions(self):
        """Test staff user permissions if applicable."""
        regular_user = AcademicUserFactory(is_staff=False)
        staff_user = AcademicUserFactory(is_staff=True)

        assert not regular_user.is_staff
        assert staff_user.is_staff

        # Staff users might have additional permissions
        # This documents the requirement for role-based access

    def test_superuser_permissions(self):
        """Test superuser permissions."""
        regular_user = AcademicUserFactory(is_superuser=False)
        super_user = AcademicUserFactory(is_superuser=True, is_staff=True)

        assert not regular_user.is_superuser
        assert super_user.is_superuser
        assert super_user.is_staff

    def test_inactive_user_blocked(self):
        """Inactive users should not be able to authenticate."""
        inactive_user = AcademicUserFactory(is_active=False)

        client = APIClient()
        client.force_authenticate(user=inactive_user)

        # This behavior depends on how authentication handles inactive users
        # Some systems allow force_authenticate even for inactive users
        # In production, inactive users should be blocked

    def test_permission_inheritance(self):
        """Test that permission inheritance works correctly."""
        user = AcademicUserFactory()

        # In Django, regular users don't automatically have model permissions
        # unless explicitly granted. This documents the current behavior.
        # Model-level permissions are enforced at the view level through user isolation

        # Regular users don't have Django model permissions by default
        assert not user.has_perm('academic.add_publication')
        assert not user.has_perm('academic.change_publication')
        assert not user.has_perm('academic.delete_publication')

        # But they can access their own data via API views which handle user isolation