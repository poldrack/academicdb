"""
Tests for Dashboard views and functionality
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from tests.factories import AcademicUserFactory

User = get_user_model()


class TestDashboardViews(TestCase):
    """Test Dashboard view functionality"""

    def setUp(self):
        self.client = Client()
        self.user = AcademicUserFactory()
        self.client.force_login(self.user)

    def test_dashboard_view_accessible(self):
        """Test that dashboard view loads without error"""
        url = reverse('academic:dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard')

    def test_recent_activity_panel_not_present(self):
        """Test that the recent activity panel is NOT displayed on the dashboard"""
        url = reverse('academic:dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Recent activity panel should not be present
        self.assertNotContains(response, 'Recent Activity')
        self.assertNotContains(response, 'No recent activity')