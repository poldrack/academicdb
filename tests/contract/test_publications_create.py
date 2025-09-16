"""
Contract test for POST /api/v1/publications/ endpoint
Tests the publication creation API contract
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from academic.models import Publication

User = get_user_model()


class TestPublicationsCreateContract(TestCase):
    """Test POST /api/v1/publications/ API contract"""
    
    def setUp(self):
        """Set up test client and user"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.url = reverse('api:publication-list')  # This will fail until we create the API
        
    def test_unauthenticated_request_returns_401(self):
        """Unauthenticated requests should return 401"""
        data = {
            "title": "Test Publication",
            "year": 2024,
            "authors": [{"name": "Test Author"}]
        }
        response = self.client.post(self.url, data, format='json')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_valid_publication_creation(self):
        """Valid publication data should create publication and return 201"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            "title": "A Novel Approach to Machine Learning",
            "year": 2024,
            "publication_type": "journal-article",
            "publication_name": "Journal of AI Research",
            "doi": "10.1234/example.doi",
            "authors": [
                {"name": "John Doe", "affiliation": "MIT"},
                {"name": "Jane Smith", "affiliation": "Stanford"}
            ]
        }
        
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check response contains created publication
        created = response.json()
        self.assertEqual(created['title'], data['title'])
        self.assertEqual(created['year'], data['year'])
        self.assertIn('id', created)
        self.assertIn('created_at', created)
        
        # Verify publication was created in database
        self.assertEqual(Publication.objects.count(), 1)
        pub = Publication.objects.first()
        self.assertEqual(pub.owner, self.user)
        self.assertEqual(pub.source, 'manual')
    
    def test_invalid_data_returns_400(self):
        """Invalid publication data should return 400"""
        self.client.force_authenticate(user=self.user)
        
        # Missing required fields
        data = {
            "year": 2024
        }
        
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        errors = response.json()
        self.assertIn('title', errors)
        self.assertIn('authors', errors)
    
    def test_doi_validation(self):
        """Invalid DOI format should return 400"""
        self.client.force_authenticate(user=self.user)
        
        data = {
            "title": "Test Publication",
            "year": 2024,
            "doi": "invalid-doi-format",
            "authors": [{"name": "Test Author"}]
        }
        
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        errors = response.json()
        self.assertIn('doi', errors)
    
    def test_year_validation(self):
        """Year outside valid range should return 400"""
        self.client.force_authenticate(user=self.user)
        
        # Test year too old
        data = {
            "title": "Ancient Publication",
            "year": 1899,
            "authors": [{"name": "Old Author"}]
        }
        
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        errors = response.json()
        self.assertIn('year', errors)
    
    def test_duplicate_doi_returns_400(self):
        """Duplicate DOI for same user should return 400"""
        self.client.force_authenticate(user=self.user)
        
        # Create first publication
        Publication.objects.create(
            owner=self.user,
            title="First Publication",
            year=2024,
            doi="10.1234/first",
            authors=[{"name": "Author"}],
            source="manual"
        )
        
        # Try to create duplicate
        data = {
            "title": "Second Publication",
            "year": 2024,
            "doi": "10.1234/first",  # Same DOI
            "authors": [{"name": "Another Author"}]
        }
        
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        errors = response.json()
        self.assertIn('doi', errors)