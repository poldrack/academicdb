"""
Simple conftest for characterization tests without DRF dependencies.
"""
import pytest


@pytest.fixture
def academic_user(db):
    """Create a basic academic user for testing."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        orcid_id='0000-0000-0000-0001',
        institution='Test University',
        department='Computer Science'
    )