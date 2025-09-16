"""
Contract test for GET /api/v1/publications/ endpoint
Tests the publication list API contract
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from academic.models import Publication

User = get_user_model()


class TestPublicationsListContract(TestCase):
    """Test GET /api/v1/publications/ API contract"""
    
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
        response = self.client.get(self.url)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
    
    def test_authenticated_request_returns_200(self):
        """Authenticated requests should return 200"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_response_format(self):
        """Response should match expected JSON schema"""
        self.client.force_authenticate(user=self.user)
        
        # Create test publication
        Publication.objects.create(
            owner=self.user,
            title="Test Publication",
            year=2024,
            authors=[{"name": "Test Author"}],
            publication_type="journal-article",
            source="manual"
        )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        
        # Check pagination structure
        self.assertIn('count', data)
        self.assertIn('next', data)
        self.assertIn('previous', data)
        self.assertIn('results', data)
        
        # Check publication structure
        self.assertIsInstance(data['results'], list)
        if data['results']:
            publication = data['results'][0]
            required_fields = [
                'id', 'title', 'year', 'publication_type',
                'authors', 'doi', 'source', 'created_at'
            ]
            for field in required_fields:
                self.assertIn(field, publication)
    
    def test_user_data_isolation(self):
        """Users should only see their own publications"""
        # Create another user with publications
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='otherpass123'
        )
        
        # Create publications for both users
        pub1 = Publication.objects.create(
            owner=self.user,
            title="My Publication",
            year=2024,
            authors=[{"name": "Me"}],
            source="manual"
        )
        
        pub2 = Publication.objects.create(
            owner=other_user,
            title="Other Publication",
            year=2024,
            authors=[{"name": "Other"}],
            source="manual"
        )
        
        # Authenticate as first user
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['title'], "My Publication")
        
    def test_pagination(self):
        """Test pagination parameters"""
        self.client.force_authenticate(user=self.user)
        
        # Create 25 publications
        for i in range(25):
            Publication.objects.create(
                owner=self.user,
                title=f"Publication {i}",
                year=2020 + (i % 5),
                authors=[{"name": f"Author {i}"}],
                source="manual"
            )
        
        # Test default page size (20)
        response = self.client.get(self.url)
        data = response.json()
        self.assertEqual(len(data['results']), 20)
        self.assertIsNotNone(data['next'])
        
        # Test page 2
        response = self.client.get(self.url, {'page': 2})
        data = response.json()
        self.assertEqual(len(data['results']), 5)
        self.assertIsNone(data['next'])
        self.assertIsNotNone(data['previous'])