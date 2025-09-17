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