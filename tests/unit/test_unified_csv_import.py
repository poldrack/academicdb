"""
Tests for unified CSV import architecture

These tests verify that the unified CSV import logic works correctly
and that both API ViewSets and data_ingestion use the same underlying logic.
"""
import pytest
import csv
import io
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from rest_framework.test import APIClient
from tests.factories import AcademicUserFactory
from academic.csv_importers import (
    CSVImporter,
    PublicationCSVImporter,
    TeachingCSVImporter,
    TalkCSVImporter,
    ConferenceCSVImporter,
    EditorialCSVImporter
)
from academic.models import Publication, Teaching, Talk, Conference, Editorial


@pytest.fixture
def user():
    """Create a test user"""
    return AcademicUserFactory()


@pytest.fixture
def csv_content():
    """Sample CSV content for testing"""
    return {
        'publication': [
            ['type', 'year', 'authors', 'title', 'journal', 'volume', 'page', 'DOI', 'publisher', 'ISBN', 'editors'],
            ['journal-article', '2023', 'John Doe, Jane Smith', 'Test Publication', 'Test Journal', '1', '1-10', '10.1234/test', '', '', '']
        ],
        'teaching': [
            ['level', 'name'],
            ['Undergraduate', 'Introduction to Psychology']
        ],
        'talk': [
            ['year', 'place', 'invited'],
            ['2023', 'Test Place', 'true']
        ],
        'conference': [
            ['authors', 'year', 'title', 'location', 'month', 'link'],
            ['John Doe', '2023', 'Test Conference Presentation', 'Test Location', 'June', 'https://example.com']
        ],
        'editorial': [
            ['role', 'journal', 'dates'],
            ['editor', 'Test Journal', '2023-2024']
        ]
    }


def create_csv_file(content_list, filename='test.csv'):
    """Helper to create CSV file from content"""
    output = io.StringIO()
    writer = csv.writer(output)
    for row in content_list:
        writer.writerow(row)

    return SimpleUploadedFile(
        filename,
        output.getvalue().encode('utf-8'),
        content_type='text/csv'
    )


@pytest.mark.django_db
class TestBaseCSVImporter:
    """Test the base CSV importer functionality"""

    def test_base_importer_cannot_be_instantiated_directly(self):
        """Base importer should not be instantiated directly"""
        with pytest.raises(NotImplementedError):
            importer = CSVImporter()
            importer.get_model()

    def test_base_importer_file_validation(self, user, csv_content):
        """Test file validation in base importer"""
        # Create a concrete importer for testing
        importer = PublicationCSVImporter()

        # Test missing file
        result = importer.import_csv(user, None)
        assert result['error'] == 'No file provided'

        # Test non-CSV file
        txt_file = SimpleUploadedFile('test.txt', b'content', content_type='text/plain')
        result = importer.import_csv(user, txt_file)
        assert result['error'] == 'File must be a CSV'


@pytest.mark.django_db
class TestPublicationCSVImporter:
    """Test publication CSV import functionality"""

    def test_publication_csv_import_success(self, user, csv_content):
        """Test successful publication CSV import"""
        csv_file = create_csv_file(csv_content['publication'])
        importer = PublicationCSVImporter()

        result = importer.import_csv(user, csv_file)

        assert result['created'] == 1
        assert result['updated'] == 0
        assert len(result['errors']) == 0

        # Verify publication was created
        pub = Publication.objects.filter(owner=user).first()
        assert pub is not None
        assert pub.title == 'Test Publication'
        assert pub.year == 2023
        assert pub.publication_type == 'journal-article'

    def test_publication_csv_import_duplicate_handling(self, user, csv_content):
        """Test handling of duplicate publications"""
        csv_file = create_csv_file(csv_content['publication'])
        importer = PublicationCSVImporter()

        # First import
        result1 = importer.import_csv(user, csv_file)
        assert result1['created'] == 1

        # Second import (same data)
        csv_file2 = create_csv_file(csv_content['publication'])
        result2 = importer.import_csv(user, csv_file2)
        assert result2['created'] == 0
        assert result2['updated'] == 1  # Should update existing


@pytest.mark.django_db
class TestTeachingCSVImporter:
    """Test teaching CSV import functionality"""

    def test_teaching_csv_import_success(self, user, csv_content):
        """Test successful teaching CSV import"""
        csv_file = create_csv_file(csv_content['teaching'])
        importer = TeachingCSVImporter()

        result = importer.import_csv(user, csv_file)

        assert result['created'] == 1
        assert result['updated'] == 0
        assert len(result['errors']) == 0

        # Verify teaching was created
        teaching = Teaching.objects.filter(owner=user).first()
        assert teaching is not None
        assert teaching.name == 'Introduction to Psychology'
        assert teaching.level == 'Undergraduate'


@pytest.mark.django_db
class TestTalkCSVImporter:
    """Test talk CSV import functionality"""

    def test_talk_csv_import_success(self, user, csv_content):
        """Test successful talk CSV import"""
        csv_file = create_csv_file(csv_content['talk'])
        importer = TalkCSVImporter()

        result = importer.import_csv(user, csv_file)

        assert result['created'] == 1
        assert result['updated'] == 0
        assert len(result['errors']) == 0

        # Verify talk was created
        talk = Talk.objects.filter(owner=user).first()
        assert talk is not None
        assert talk.year == 2023
        assert talk.place == 'Test Place'
        assert talk.invited == True


@pytest.mark.django_db
class TestConferenceCSVImporter:
    """Test conference CSV import functionality"""

    def test_conference_csv_import_success(self, user, csv_content):
        """Test successful conference CSV import"""
        csv_file = create_csv_file(csv_content['conference'])
        importer = ConferenceCSVImporter()

        result = importer.import_csv(user, csv_file)

        assert result['created'] == 1
        assert result['updated'] == 0
        assert len(result['errors']) == 0

        # Verify conference was created
        conference = Conference.objects.filter(owner=user).first()
        assert conference is not None
        assert conference.authors == 'John Doe'
        assert conference.year == 2023
        assert conference.title == 'Test Conference Presentation'
        assert conference.location == 'Test Location'
        assert conference.month == 'June'
        assert conference.link == 'https://example.com'


@pytest.mark.django_db
class TestEditorialCSVImporter:
    """Test editorial CSV import functionality"""

    def test_editorial_csv_import_success(self, user, csv_content):
        """Test successful editorial CSV import"""
        csv_file = create_csv_file(csv_content['editorial'])
        importer = EditorialCSVImporter()

        result = importer.import_csv(user, csv_file)

        assert result['created'] == 1
        assert result['updated'] == 0
        assert len(result['errors']) == 0

        # Verify editorial was created
        editorial = Editorial.objects.filter(owner=user).first()
        assert editorial is not None
        assert editorial.role == 'editor'
        assert editorial.journal == 'Test Journal'


@pytest.mark.django_db
class TestUnifiedCSVImportConsistency:
    """Test that all CSV importers produce consistent results"""

    def test_all_importers_have_consistent_interface(self):
        """Test that all importers follow the same interface"""
        importers = [
            PublicationCSVImporter(),
            TeachingCSVImporter(),
            TalkCSVImporter(),
            ConferenceCSVImporter(),
            EditorialCSVImporter()
        ]

        for importer in importers:
            # All should have import_csv method
            assert hasattr(importer, 'import_csv')
            assert callable(importer.import_csv)

            # All should have get_model method
            assert hasattr(importer, 'get_model')
            assert callable(importer.get_model)

            # All should have map_csv_row method
            assert hasattr(importer, 'map_csv_row')
            assert callable(importer.map_csv_row)

    def test_all_importers_return_consistent_response_format(self, user, csv_content):
        """Test that all importers return responses in the same format"""
        test_cases = [
            (PublicationCSVImporter(), csv_content['publication']),
            (TeachingCSVImporter(), csv_content['teaching']),
            (TalkCSVImporter(), csv_content['talk']),
            (ConferenceCSVImporter(), csv_content['conference']),
            (EditorialCSVImporter(), csv_content['editorial'])
        ]

        for importer, content in test_cases:
            csv_file = create_csv_file(content)
            result = importer.import_csv(user, csv_file)

            # All should return the same response structure
            assert 'created' in result
            assert 'updated' in result
            assert 'errors' in result
            assert 'created_ids' in result
            assert 'updated_ids' in result

            # Types should be consistent
            assert isinstance(result['created'], int)
            assert isinstance(result['updated'], int)
            assert isinstance(result['errors'], list)
            assert isinstance(result['created_ids'], list)
            assert isinstance(result['updated_ids'], list)


@pytest.mark.django_db
class TestCSVImportErrorHandling:
    """Test error handling in CSV import"""

    def test_invalid_csv_content_handling(self, user):
        """Test handling of invalid CSV content"""
        # Create CSV with invalid content (missing required columns)
        invalid_content = [
            ['invalid_header'],
            ['invalid_data']
        ]
        csv_file = create_csv_file(invalid_content)
        importer = PublicationCSVImporter()

        result = importer.import_csv(user, csv_file)

        # Should return error for missing required columns
        assert 'error' in result
        assert 'Missing required columns' in result['error']

    def test_empty_csv_handling(self, user):
        """Test handling of empty CSV files"""
        empty_content = []
        csv_file = create_csv_file(empty_content)
        importer = PublicationCSVImporter()

        result = importer.import_csv(user, csv_file)

        # Should handle gracefully
        assert result['created'] == 0
        assert result['updated'] == 0

    def test_missing_required_columns(self, user):
        """Test handling of CSV missing required columns"""
        # Create CSV missing required 'title' column for publications
        invalid_content = [
            ['year', 'authors'],  # Missing 'title' which is required
            ['2023', 'John Doe']
        ]
        csv_file = create_csv_file(invalid_content)
        importer = PublicationCSVImporter()

        result = importer.import_csv(user, csv_file)

        # Should return error for missing required columns
        assert 'error' in result
        assert 'Missing required columns' in result['error']
        assert 'title' in result['error']

    def test_invalid_columns(self, user):
        """Test handling of CSV with invalid column names"""
        # Create CSV with invalid column names
        invalid_content = [
            ['title', 'invalid_column', 'another_invalid'],
            ['Test Title', 'value', 'value2']
        ]
        csv_file = create_csv_file(invalid_content)
        importer = PublicationCSVImporter()

        result = importer.import_csv(user, csv_file)

        # Should return error for invalid columns
        assert 'error' in result
        assert 'Invalid columns' in result['error']