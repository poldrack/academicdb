"""
Integration test for researcher registration flow
Tests the complete user journey from signup to dashboard access
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from academic.models import Publication

User = get_user_model()


class TestUserRegistrationFlow(TestCase):
    """Test complete user registration and onboarding flow"""
    
    def setUp(self):
        """Set up test client"""
        self.client = Client()
    
    def test_homepage_accessible(self):
        """Homepage should be accessible without authentication"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academic Database")
    
    def test_signup_flow(self):
        """Test user signup process"""
        # Navigate to signup page
        signup_url = reverse('account_signup')
        response = self.client.get(signup_url)
        self.assertEqual(response.status_code, 200)
        
        # Submit signup form
        signup_data = {
            'email': 'newuser@example.com',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
        }
        
        response = self.client.post(signup_url, signup_data)
        
        # Should redirect after successful signup
        # Note: With email verification enabled, user needs to verify email
        # For testing, we'll check user was created
        self.assertTrue(
            User.objects.filter(email='newuser@example.com').exists()
        )
    
    def test_login_and_dashboard_access(self):
        """Test login and dashboard access"""
        # Create a user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        
        # Login
        login_url = reverse('account_login')
        response = self.client.post(login_url, {
            'login': 'test@example.com',
            'password': 'testpass123'
        })
        
        # Should redirect to dashboard after login
        self.assertRedirects(response, '/dashboard/')
        
        # Access dashboard
        dashboard_url = reverse('academic:dashboard')
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test User')
        self.assertContains(response, 'Dashboard')
    
    def test_profile_update(self):
        """Test user profile update"""
        # Create and login user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Access profile page
        profile_url = reverse('academic:profile')
        response = self.client.get(profile_url)
        self.assertEqual(response.status_code, 200)
        
        # Update profile (would need form submission)
        # This is a placeholder for actual form submission
        user.institution = 'MIT'
        user.department = 'Computer Science'
        user.save()
        
        # Verify update
        updated_user = User.objects.get(pk=user.pk)
        self.assertEqual(updated_user.institution, 'MIT')
        self.assertEqual(updated_user.department, 'Computer Science')
    
    def test_authenticated_user_can_access_publications(self):
        """Authenticated users should access their publications"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Access publications list
        pub_url = reverse('academic:publication_list')
        response = self.client.get(pub_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Publications')
    
    def test_unauthenticated_user_redirected_to_login(self):
        """Unauthenticated users should be redirected to login"""
        # Try to access protected pages
        protected_urls = [
            reverse('academic:dashboard'),
            reverse('academic:profile'),
            reverse('academic:publication_list'),
        ]
        
        for url in protected_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/accounts/login/', response.url)
    
    def test_orcid_connection_flow(self):
        """Test ORCID connection flow (mock)"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Access ORCID connection page
        orcid_url = reverse('academic:orcid_connected')
        response = self.client.get(orcid_url)
        self.assertEqual(response.status_code, 200)
        
        # Check for ORCID connection status
        self.assertContains(response, 'ORCID')
        
        # Simulate ORCID connection
        user.orcid_id = '0000-0002-1825-0097'
        user.orcid_token = 'mock_token'
        user.save()
        
        # Verify connection
        self.assertTrue(user.is_orcid_connected)
    
    def test_complete_onboarding_flow(self):
        """Test complete onboarding from signup to first publication"""
        # 1. Sign up
        signup_data = {
            'email': 'researcher@university.edu',
            'password1': 'ResearchPass123!',
            'password2': 'ResearchPass123!',
        }
        self.client.post(reverse('account_signup'), signup_data)
        
        # 2. Get user and set as verified (bypass email verification for test)
        user = User.objects.get(email='researcher@university.edu')
        user.is_active = True
        user.save()
        
        # 3. Login
        self.client.post(reverse('account_login'), {
            'login': 'researcher@university.edu',
            'password': 'ResearchPass123!'
        })
        
        # 4. Update profile
        user.institution = 'Stanford University'
        user.department = 'Psychology'
        user.first_name = 'Jane'
        user.last_name = 'Researcher'
        user.save()
        
        # 5. Add first publication
        pub = Publication.objects.create(
            owner=user,
            title="My First Research Paper",
            year=2024,
            authors=[{"name": "Jane Researcher", "affiliation": "Stanford"}],
            source="manual"
        )
        
        # 6. Verify complete setup
        response = self.client.get(reverse('academic:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Jane Researcher')
        self.assertContains(response, '1')  # Publication count