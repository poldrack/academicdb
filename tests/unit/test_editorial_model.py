"""
Test Editorial model functionality
"""
import pytest
from datetime import date
from academic.models import Editorial, AcademicUser


@pytest.mark.django_db
class TestEditorialModel:
    """Test Editorial model"""

    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing"""
        return AcademicUser.objects.create_user(
            username='editorialuser',
            email='editorial@example.com',
            orcid_id='0000-0000-0000-0009',
            first_name='Editorial',
            last_name='User'
        )

    def test_editorial_creation(self, sample_user):
        """Test creating an editorial activity"""
        editorial = Editorial.objects.create(
            owner=sample_user,
            role='Senior Editor',
            journal='Psychological Science',
            dates='2024-'
        )

        assert editorial.role == 'Senior Editor'
        assert editorial.journal == 'Psychological Science'
        assert editorial.dates == '2024-'
        assert editorial.owner == sample_user

    def test_editorial_str_representation(self, sample_user):
        """Test string representation of Editorial model"""
        editorial = Editorial.objects.create(
            owner=sample_user,
            role='Editorial board',
            journal='Nature',
            dates='2020-2024'
        )

        expected = 'Editorial board, Nature, 2020-2024'
        assert str(editorial) == expected