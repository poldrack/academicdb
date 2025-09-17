"""
Tests for CV generation endpoints
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from tests.factories import AcademicUserFactory

User = get_user_model()


class TestCVEndpoints(TestCase):
    """Test CV generation functionality"""

    def setUp(self):
        self.client = Client()
        self.user = AcademicUserFactory()
        self.client.force_login(self.user)

    def test_cv_download_tex_accessible(self):
        """Test that CV LaTeX download works"""
        url = reverse('academic:cv_download', kwargs={'format_type': 'tex'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertIn('cv_', response['Content-Disposition'])

    def test_cv_download_pdf_accessible(self):
        """Test that CV PDF download works (or fails gracefully)"""
        url = reverse('academic:cv_download', kwargs={'format_type': 'pdf'})
        response = self.client.get(url)
        # Should either return a PDF (200) or redirect (302) if LaTeX compilation fails
        self.assertIn(response.status_code, [200, 302])