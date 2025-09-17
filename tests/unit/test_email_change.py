"""
Tests for email change functionality in profile
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from tests.factories import AcademicUserFactory


User = get_user_model()


@pytest.mark.django_db
class TestEmailChange:
    """Test suite for email change functionality"""

    def test_email_field_is_editable(self, client):
        """Test that the email field is editable in the profile form"""
        user = AcademicUserFactory(email="old@example.com")
        client.force_login(user)

        url = reverse('academic:profile')
        response = client.get(url)

        # Check that email field is not readonly
        assert 'readonly' not in str(response.content)
        assert 'name="email"' in str(response.content)
        assert 'old@example.com' in str(response.content)

    def test_email_change_success(self, client):
        """Test successful email change"""
        user = AcademicUserFactory(email="old@example.com")
        client.force_login(user)

        url = reverse('academic:profile')
        response = client.post(url, {
            'email': 'new@example.com',
            'first_name': user.first_name,
            'last_name': user.last_name,
            'institution': user.institution or '',
            'department': user.department or '',
            'scopus_id': user.scopus_id or '',
            'pubmed_query': user.pubmed_query or '',
            'skip_dois': user.skip_dois or '',
            'research_areas': '',
            'middle_name': user.middle_name or '',
            'address1': user.address1 or '',
            'address2': user.address2 or '',
            'city': user.city or '',
            'state': user.state or '',
            'zip_code': user.zip_code or '',
            'country': user.country or '',
            'phone': user.phone or '',
            'citation_style': 'apa',
        })

        # Should redirect after successful update
        assert response.status_code == 302

        # Email should be updated
        user.refresh_from_db()
        assert user.email == 'new@example.com'

    def test_email_uniqueness_validation(self, client):
        """Test that duplicate emails are rejected"""
        user1 = AcademicUserFactory(email="user1@example.com")
        user2 = AcademicUserFactory(email="user2@example.com")
        client.force_login(user1)

        url = reverse('academic:profile')
        response = client.post(url, {
            'email': 'user2@example.com',  # Try to use user2's email
            'first_name': user1.first_name,
            'last_name': user1.last_name,
            'institution': user1.institution or '',
            'department': user1.department or '',
            'scopus_id': user1.scopus_id or '',
            'pubmed_query': user1.pubmed_query or '',
            'skip_dois': user1.skip_dois or '',
            'research_areas': '',
            'middle_name': user1.middle_name or '',
            'address1': user1.address1 or '',
            'address2': user1.address2 or '',
            'city': user1.city or '',
            'state': user1.state or '',
            'zip_code': user1.zip_code or '',
            'country': user1.country or '',
            'phone': user1.phone or '',
            'citation_style': 'apa',
        })

        # Should redirect with error message
        assert response.status_code == 302

        # Email should NOT be updated
        user1.refresh_from_db()
        assert user1.email == 'user1@example.com'

    def test_empty_email_not_allowed(self, client):
        """Test that empty email is not allowed"""
        user = AcademicUserFactory(email="user@example.com")
        client.force_login(user)

        url = reverse('academic:profile')
        response = client.post(url, {
            'email': '',  # Empty email
            'first_name': user.first_name,
            'last_name': user.last_name,
            'institution': user.institution or '',
            'department': user.department or '',
            'scopus_id': user.scopus_id or '',
            'pubmed_query': user.pubmed_query or '',
            'skip_dois': user.skip_dois or '',
            'research_areas': '',
            'middle_name': user.middle_name or '',
            'address1': user.address1 or '',
            'address2': user.address2 or '',
            'city': user.city or '',
            'state': user.state or '',
            'zip_code': user.zip_code or '',
            'country': user.country or '',
            'phone': user.phone or '',
            'citation_style': 'apa',
        })

        # Email should NOT be changed to empty
        user.refresh_from_db()
        assert user.email == 'user@example.com'

    def test_same_email_allowed(self, client):
        """Test that submitting the same email doesn't cause issues"""
        user = AcademicUserFactory(email="user@example.com")
        client.force_login(user)

        url = reverse('academic:profile')
        response = client.post(url, {
            'email': 'user@example.com',  # Same email
            'first_name': 'Updated',
            'last_name': user.last_name,
            'institution': user.institution or '',
            'department': user.department or '',
            'scopus_id': user.scopus_id or '',
            'pubmed_query': user.pubmed_query or '',
            'skip_dois': user.skip_dois or '',
            'research_areas': '',
            'middle_name': user.middle_name or '',
            'address1': user.address1 or '',
            'address2': user.address2 or '',
            'city': user.city or '',
            'state': user.state or '',
            'zip_code': user.zip_code or '',
            'country': user.country or '',
            'phone': user.phone or '',
            'citation_style': 'apa',
        })

        # Should redirect successfully
        assert response.status_code == 302

        # Email should remain the same, name should update
        user.refresh_from_db()
        assert user.email == 'user@example.com'
        assert user.first_name == 'Updated'