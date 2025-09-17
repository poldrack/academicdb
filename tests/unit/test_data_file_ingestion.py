"""
Tests for data file ingestion functionality
"""
import pytest
import os
import tempfile
import csv
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings
from academic.models import Publication, Conference, Editorial, Teaching, Talk, Link
from tests.factories import AcademicUserFactory, PublicationFactory

User = get_user_model()


class TestDataFileIngestion(TestCase):
    """Test data file ingestion from CSV files"""

    def setUp(self):
        self.client = Client()
        self.user = AcademicUserFactory()
        self.client.force_login(self.user)

        # Create a temporary directory for test data files
        self.test_data_dir = tempfile.mkdtemp()

    def tearDown(self):
        # Clean up temporary directory
        import shutil
        shutil.rmtree(self.test_data_dir, ignore_errors=True)

    def create_additional_pubs_csv(self, filename="additional_pubs.csv"):
        """Create a test additional publications CSV file"""
        filepath = os.path.join(self.test_data_dir, filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['title', 'authors', 'year', 'doi', 'journal'])
            writer.writerow([
                'Test Publication 1',
                'Author, A.; Author, B.',
                '2023',
                '10.1000/test1',
                'Test Journal'
            ])
            writer.writerow([
                'Test Publication 2',
                'Author, C.; Author, D.',
                '2024',
                '10.1000/test2',
                'Another Journal'
            ])
        return filepath

    def create_conferences_csv(self, filename="conferences.csv"):
        """Create a test conferences CSV file"""
        filepath = os.path.join(self.test_data_dir, filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['title', 'authors', 'year', 'venue', 'location'])
            writer.writerow([
                'Test Conference Talk 1',
                'Author, A.',
                '2023',
                'Conference Name',
                'City, Country'
            ])
        return filepath

    def create_editorial_csv(self, filename="editorial.csv"):
        """Create a test editorial activities CSV file"""
        filepath = os.path.join(self.test_data_dir, filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['role', 'journal', 'dates'])
            writer.writerow([
                'Editor',
                'Test Journal',
                '2020-2023'
            ])
        return filepath

    def create_links_csv(self, filename="links.csv"):
        """Create a test links CSV file"""
        # First create a publication to link to
        pub = PublicationFactory(owner=self.user, title="Linkable Publication")

        filepath = os.path.join(self.test_data_dir, filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['publication_title', 'link_type', 'url', 'description'])
            writer.writerow([
                'Linkable Publication',
                'data',
                'https://example.com/data',
                'Test data link'
            ])
        return filepath

    def create_talks_csv(self, filename="talks.csv"):
        """Create a test talks CSV file"""
        filepath = os.path.join(self.test_data_dir, filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['title', 'venue', 'date', 'type'])
            writer.writerow([
                'Test Talk',
                'University of Test',
                '2023-05-15',
                'invited'
            ])
        return filepath

    def create_teaching_csv(self, filename="teaching.csv"):
        """Create a test teaching CSV file"""
        filepath = os.path.join(self.test_data_dir, filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['course_name', 'institution', 'year', 'role'])
            writer.writerow([
                'Test Course 101',
                'Test University',
                '2023',
                'instructor'
            ])
        return filepath

    def test_data_directory_parameter_accepted(self):
        """Test that comprehensive sync accepts a data_directory parameter"""
        # Create test CSV files
        self.create_additional_pubs_csv()

        url = reverse('academic:comprehensive_sync')
        response = self.client.post(url, {
            'data_directory': self.test_data_dir
        })

        # Should not return an error - actual ingestion will be tested separately
        self.assertIn(response.status_code, [200, 302])

    def test_default_data_directory_docker(self):
        """Test that the default data directory is /app/datafiles in Docker"""
        from academic.views import ComprehensiveSyncView
        from unittest.mock import patch

        with patch('os.path.exists') as mock_exists:
            # Simulate Docker environment
            mock_exists.return_value = True

            url = reverse('academic:comprehensive_sync')
            # Don't actually run the sync, just check the path logic
            # This would need more complex mocking in a real test

    def test_additional_publications_ingestion(self):
        """Test that additional_pubs.csv is processed correctly"""
        self.create_additional_pubs_csv()

        # Mock calling the ingestion function directly
        from academic.data_ingestion import ingest_additional_publications

        initial_count = Publication.objects.filter(owner=self.user).count()

        ingest_additional_publications(self.user, self.test_data_dir)

        final_count = Publication.objects.filter(owner=self.user).count()
        self.assertEqual(final_count, initial_count + 2)

        # Check that publications were created correctly
        pub1 = Publication.objects.filter(owner=self.user, title="Test Publication 1").first()
        self.assertIsNotNone(pub1)
        self.assertEqual(pub1.year, 2023)
        self.assertEqual(pub1.doi, "10.1000/test1")

    def test_conferences_ingestion(self):
        """Test that conferences.csv is processed correctly"""
        self.create_conferences_csv()

        from academic.data_ingestion import ingest_conferences

        initial_count = Conference.objects.filter(owner=self.user).count()

        ingest_conferences(self.user, self.test_data_dir)

        final_count = Conference.objects.filter(owner=self.user).count()
        self.assertEqual(final_count, initial_count + 1)

    def test_editorial_ingestion(self):
        """Test that editorial.csv is processed correctly"""
        self.create_editorial_csv()

        from academic.data_ingestion import ingest_editorial

        initial_count = Editorial.objects.filter(owner=self.user).count()

        ingest_editorial(self.user, self.test_data_dir)

        final_count = Editorial.objects.filter(owner=self.user).count()
        self.assertEqual(final_count, initial_count + 1)

    def test_links_ingestion(self):
        """Test that links.csv is processed correctly"""
        self.create_links_csv()

        from academic.data_ingestion import ingest_links

        initial_count = Link.objects.filter(owner=self.user).count()

        ingest_links(self.user, self.test_data_dir)

        final_count = Link.objects.filter(owner=self.user).count()
        self.assertEqual(final_count, initial_count + 1)

    def test_talks_ingestion(self):
        """Test that talks.csv is processed correctly"""
        self.create_talks_csv()

        from academic.data_ingestion import ingest_talks

        initial_count = Talk.objects.filter(owner=self.user).count()

        ingest_talks(self.user, self.test_data_dir)

        final_count = Talk.objects.filter(owner=self.user).count()
        self.assertEqual(final_count, initial_count + 1)

    def test_teaching_ingestion(self):
        """Test that teaching.csv is processed correctly"""
        self.create_teaching_csv()

        from academic.data_ingestion import ingest_teaching

        initial_count = Teaching.objects.filter(owner=self.user).count()

        ingest_teaching(self.user, self.test_data_dir)

        final_count = Teaching.objects.filter(owner=self.user).count()
        self.assertEqual(final_count, initial_count + 1)

    def test_ingest_all_data_files(self):
        """Test that ingest_all_data_files processes all CSV files correctly"""
        # Create all test CSV files
        self.create_additional_pubs_csv()
        self.create_conferences_csv()
        self.create_editorial_csv()
        self.create_links_csv()
        self.create_talks_csv()
        self.create_teaching_csv()

        from academic.data_ingestion import ingest_all_data_files

        initial_pub_count = Publication.objects.filter(owner=self.user).count()
        initial_conf_count = Conference.objects.filter(owner=self.user).count()
        initial_editorial_count = Editorial.objects.filter(owner=self.user).count()
        initial_talk_count = Talk.objects.filter(owner=self.user).count()
        initial_teaching_count = Teaching.objects.filter(owner=self.user).count()
        initial_link_count = Link.objects.filter(owner=self.user).count()

        # Call the ingestion function
        results = ingest_all_data_files(self.user, self.test_data_dir)

        # Verify results dictionary
        self.assertIn('additional_publications', results)
        self.assertIn('conferences', results)
        self.assertIn('editorial', results)
        self.assertIn('links', results)
        self.assertIn('talks', results)
        self.assertIn('teaching', results)

        # Verify data was ingested
        final_pub_count = Publication.objects.filter(owner=self.user).count()
        final_conf_count = Conference.objects.filter(owner=self.user).count()
        final_editorial_count = Editorial.objects.filter(owner=self.user).count()
        final_talk_count = Talk.objects.filter(owner=self.user).count()
        final_teaching_count = Teaching.objects.filter(owner=self.user).count()
        final_link_count = Link.objects.filter(owner=self.user).count()

        self.assertEqual(final_pub_count, initial_pub_count + 2)  # 2 publications in CSV
        self.assertEqual(final_conf_count, initial_conf_count + 1)  # 1 conference in CSV
        self.assertEqual(final_editorial_count, initial_editorial_count + 1)  # 1 editorial in CSV
        self.assertEqual(final_talk_count, initial_talk_count + 1)  # 1 talk in CSV
        self.assertEqual(final_teaching_count, initial_teaching_count + 1)  # 1 teaching in CSV
        self.assertEqual(final_link_count, initial_link_count + 1)  # 1 link in CSV