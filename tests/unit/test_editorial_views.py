"""
Tests for Editorial views and functionality
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from academic.models import Editorial
from tests.factories import AcademicUserFactory

User = get_user_model()


class TestEditorialViews(TestCase):
    """Test Editorial view functionality"""

    def setUp(self):
        self.client = Client()
        self.user = AcademicUserFactory()
        self.client.force_login(self.user)

    def test_editorial_list_view_accessible(self):
        """Test that editorial list view loads without error"""
        url = reverse('academic:editorial_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Editorial Activities')

    def test_editorial_create_view_accessible(self):
        """Test that editorial create view loads without error"""
        url = reverse('academic:editorial_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_editorial_create_post(self):
        """Test creating a new editorial activity via POST"""
        url = reverse('academic:editorial_create')
        data = {
            'role': 'Senior Editor',
            'journal': 'Test Journal',
            'dates': '2020-2024'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation

        # Check that editorial was created
        editorial = Editorial.objects.get(owner=self.user)
        self.assertEqual(editorial.role, 'Senior Editor')
        self.assertEqual(editorial.journal, 'Test Journal')
        self.assertEqual(editorial.dates, '2020-2024')
        self.assertEqual(editorial.source, 'manual')

    def test_editorial_delete_all_button_present(self):
        """Test that delete all button is present on editorial list page when activities exist"""
        # Create an editorial activity so the button shows
        Editorial.objects.create(
            owner=self.user,
            role='Editor',
            journal='Test Journal',
            dates='2020-2024',
            source='manual'
        )

        url = reverse('academic:editorial_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Delete All')

    def test_editorial_delete_all_view_accessible(self):
        """Test that editorial delete all view is accessible"""
        url = reverse('academic:editorial_delete_all')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_editorial_delete_all_functionality(self):
        """Test that delete all removes all editorial activities for the user"""
        # Create some editorial activities
        Editorial.objects.create(
            owner=self.user,
            role='Editor',
            journal='Journal 1',
            dates='2020-2024',
            source='manual'
        )
        Editorial.objects.create(
            owner=self.user,
            role='Associate Editor',
            journal='Journal 2',
            dates='2021-2025',
            source='manual'
        )

        # Create editorial for another user to ensure it's not deleted
        other_user = AcademicUserFactory()
        Editorial.objects.create(
            owner=other_user,
            role='Editor',
            journal='Other Journal',
            dates='2022-2026',
            source='manual'
        )

        # Verify initial state
        self.assertEqual(Editorial.objects.filter(owner=self.user).count(), 2)
        self.assertEqual(Editorial.objects.filter(owner=other_user).count(), 1)

        # Delete all for current user
        url = reverse('academic:editorial_delete_all')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # Redirect after deletion

        # Verify only current user's editorial activities were deleted
        self.assertEqual(Editorial.objects.filter(owner=self.user).count(), 0)
        self.assertEqual(Editorial.objects.filter(owner=other_user).count(), 1)