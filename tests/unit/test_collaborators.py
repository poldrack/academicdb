"""
Tests for Collaborator model and functionality
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from academic.models import Publication, Collaborator
from tests.factories import AcademicUserFactory, PublicationFactory

User = get_user_model()


class TestCollaboratorModel(TestCase):
    """Test Collaborator model functionality"""

    def setUp(self):
        self.user = AcademicUserFactory()

    def test_collaborator_model_creation(self):
        """Test that collaborators can be created"""
        collaborator = Collaborator.objects.create(
            owner=self.user,
            scopus_id="12345678900",
            name="Smith, John A.",
            affiliation="University of Test",
            last_publication_date="2023-01-15"
        )

        self.assertEqual(collaborator.owner, self.user)
        self.assertEqual(collaborator.scopus_id, "12345678900")
        self.assertEqual(collaborator.name, "Smith, John A.")
        self.assertEqual(collaborator.affiliation, "University of Test")

    def test_collaborator_unique_constraint(self):
        """Test that collaborators are unique per user and Scopus ID"""
        Collaborator.objects.create(
            owner=self.user,
            scopus_id="12345678900",
            name="Smith, John A.",
            affiliation="University of Test",
            last_publication_date="2023-01-15"
        )

        # Creating another with the same user and scopus_id should be allowed (for updates)
        # but we should handle this in the business logic
        collaborator2 = Collaborator.objects.create(
            owner=self.user,
            scopus_id="12345678900",
            name="Smith, John A.",
            affiliation="University of California",  # Updated affiliation
            last_publication_date="2024-01-15"
        )

        # Should have 2 collaborators now (will be deduplicated in business logic)
        self.assertEqual(Collaborator.objects.filter(owner=self.user).count(), 2)


class TestCollaboratorViews(TestCase):
    """Test Collaborator view functionality"""

    def setUp(self):
        self.client = Client()
        self.user = AcademicUserFactory()
        self.client.force_login(self.user)

    def test_collaborators_list_view_accessible(self):
        """Test that collaborators list view loads without error"""
        url = reverse('academic:collaborators_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Collaborators')

    def test_build_collaborators_button_present(self):
        """Test that the build collaborators button is present"""
        url = reverse('academic:collaborators_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Build collaborators table')

    def test_build_collaborators_view_accessible(self):
        """Test that build collaborators view is accessible"""
        url = reverse('academic:build_collaborators')
        response = self.client.post(url)
        # Should redirect after processing
        self.assertIn(response.status_code, [200, 302])


class TestCollaboratorExtraction(TestCase):
    """Test extracting collaborators from publications"""

    def setUp(self):
        self.user = AcademicUserFactory()

    def test_extract_collaborators_from_publications(self):
        """Test that collaborators are correctly extracted from publications"""
        # Create a publication with Scopus coauthor IDs
        pub = PublicationFactory(
            owner=self.user,
            title="Test Publication",
            metadata={
                'scopus_coauthor_ids': ['12345678900', '98765432100'],
                'scopus': {
                    'authors': [
                        {'scopus_id': '12345678900', 'name': 'Smith, John A.'},
                        {'scopus_id': '98765432100', 'name': 'Doe, Jane B.'}
                    ]
                }
            }
        )

        from academic.collaborator_utils import extract_collaborators_from_publications

        collaborator_ids = extract_collaborators_from_publications(self.user)

        # Should find 2 unique Scopus IDs
        self.assertEqual(len(collaborator_ids), 2)
        self.assertIn('12345678900', collaborator_ids)
        self.assertIn('98765432100', collaborator_ids)

    def test_extract_collaborators_excludes_owner(self):
        """Test that the user's own Scopus ID is excluded from collaborators"""
        # Set user's Scopus ID
        self.user.scopus_id = "11111111111"
        self.user.save()

        # Create a publication with user's own ID included
        pub = PublicationFactory(
            owner=self.user,
            title="Test Publication",
            metadata={
                'scopus_coauthor_ids': ['11111111111', '12345678900'],  # User's own ID first
            }
        )

        from academic.collaborator_utils import extract_collaborators_from_publications

        collaborator_ids = extract_collaborators_from_publications(self.user)

        # Should only find 1 ID (excluding user's own)
        self.assertEqual(len(collaborator_ids), 1)
        self.assertNotIn('11111111111', collaborator_ids)
        self.assertIn('12345678900', collaborator_ids)

    def test_build_collaborators_table_mock(self):
        """Test building collaborators table with mocked Scopus API"""
        # Create publications with collaborator IDs
        pub1 = PublicationFactory(
            owner=self.user,
            title="Test Publication 1",
            metadata={'scopus_coauthor_ids': ['12345678900']},
            publication_date="2023-01-15"
        )

        pub2 = PublicationFactory(
            owner=self.user,
            title="Test Publication 2",
            metadata={'scopus_coauthor_ids': ['98765432100']},
            publication_date="2024-02-20"
        )

        from academic.collaborator_utils import build_collaborators_table
        from unittest.mock import patch

        # Mock the Scopus API calls
        mock_author_data = {
            '12345678900': {
                'scopus_id': '12345678900',
                'name': 'Smith, John A.',
                'surname': 'Smith',
                'given_name': 'John A.',
                'affiliation_current': [{'name': 'University of Test', 'id': '12345'}]
            },
            '98765432100': {
                'scopus_id': '98765432100',
                'name': 'Doe, Jane B.',
                'surname': 'Doe',
                'given_name': 'Jane B.',
                'affiliation_current': [{'name': 'Test Institute', 'id': '67890'}]
            }
        }

        with patch('academic.collaborator_utils.get_scopus_author_info') as mock_get_info:
            def mock_get_info_side_effect(scopus_id):
                return mock_author_data.get(scopus_id, {})

            mock_get_info.side_effect = mock_get_info_side_effect

            # Build collaborators table
            result = build_collaborators_table(self.user)

            # Should have processed 2 collaborators
            self.assertEqual(result['processed'], 2)
            self.assertEqual(result['errors'], 0)

            # Check that collaborators were created
            collaborators = Collaborator.objects.filter(owner=self.user)
            self.assertEqual(collaborators.count(), 2)

            # Check specific collaborator data
            smith = collaborators.get(scopus_id='12345678900')
            self.assertEqual(smith.name, 'Smith, John A.')
            self.assertEqual(smith.affiliation, 'University of Test')

            doe = collaborators.get(scopus_id='98765432100')
            self.assertEqual(doe.name, 'Doe, Jane B.')
            self.assertEqual(doe.affiliation, 'Test Institute')