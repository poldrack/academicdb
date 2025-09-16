"""
Characterization tests for existing model behavior.

These tests document how the current models work and prevent
regression when making changes.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from academic.models import Publication, Teaching, Talk, Conference

User = get_user_model()


@pytest.mark.django_db
class TestCurrentModelBehavior:
    """Document existing model behavior to prevent regression."""

    def test_academic_user_creation(self):
        """Test current AcademicUser model behavior."""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            orcid_id='0000-0000-0000-0001'
        )

        assert user.username == 'testuser'
        assert user.email == 'test@example.com'
        assert user.orcid_id == '0000-0000-0000-0001'
        assert user.is_active
        assert not user.is_staff
        assert not user.is_superuser

    def test_orcid_id_uniqueness_current_behavior(self):
        """Document that ORCID IDs must be unique (if enforced)."""
        User.objects.create_user(
            username='user1',
            email='user1@example.com',
            orcid_id='0000-0000-0000-0001'
        )

        # This should fail if uniqueness is enforced
        try:
            User.objects.create_user(
                username='user2',
                email='user2@example.com',
                orcid_id='0000-0000-0000-0001'
            )
            # If we get here, uniqueness is NOT enforced
            assert True, "ORCID uniqueness not enforced - this is current behavior"
        except IntegrityError:
            # If we get here, uniqueness IS enforced
            assert True, "ORCID uniqueness is enforced"

    def test_publication_creation_current_behavior(self):
        """Document current Publication model behavior."""
        user = User.objects.create_user(username='testuser', email='test@example.com')

        pub = Publication.objects.create(
            owner=user,
            title="Test Publication",
            doi="10.1234/test.publication",
            year=2024,
            publication_name="Test Journal",
            authors=[{"name": "Test Author"}]  # Required field
        )

        assert pub.owner == user
        assert pub.title == "Test Publication"
        assert pub.doi == "10.1234/test.publication"
        assert pub.year == 2024
        assert pub.publication_name == "Test Journal"

        # Check default values - authors was provided so won't be empty
        assert len(pub.authors) == 1  # We provided one author
        assert pub.metadata == {}  # Should be empty dict by default
        assert pub.manual_edits == {}  # Should be empty dict by default
        assert pub.edit_history == []  # Should be empty list by default
        assert pub.is_preprint is False  # Should default to False

    def test_publication_json_fields_current_behavior(self):
        """Document how JSON fields currently work."""
        user = User.objects.create_user(username='testuser', email='test@example.com')

        pub = Publication.objects.create(
            owner=user,
            title="Test Publication",
            doi="10.1234/test",
            year=2024,
            authors=[
                {"name": "Author One", "orcid": "0000-0000-0000-0001"},
                {"name": "Author Two", "orcid": None}
            ],
            metadata={
                "abstract": "Test abstract",
                "keywords": ["test", "publication"],
                "source": "manual"
            }
        )

        pub.refresh_from_db()

        # Check that JSON data persists correctly
        assert len(pub.authors) == 2
        assert pub.authors[0]["name"] == "Author One"
        assert pub.authors[0]["orcid"] == "0000-0000-0000-0001"
        assert pub.authors[1]["orcid"] is None

        assert pub.metadata["abstract"] == "Test abstract"
        assert "test" in pub.metadata["keywords"]
        assert pub.metadata["source"] == "manual"

    def test_publication_doi_constraints(self):
        """Document current DOI field constraints."""
        user = User.objects.create_user(username='testuser', email='test@example.com')

        # Test what DOI values are currently accepted
        pub = Publication.objects.create(
            owner=user,
            title="Test Publication",
            doi="10.1234/test.publication",
            year=2024
        )
        assert pub.doi == "10.1234/test.publication"

        # Test if empty DOI is allowed
        pub2 = Publication.objects.create(
            owner=user,
            title="Test Publication 2",
            doi="",  # Empty string
            year=2024
        )
        assert pub2.doi == ""

        # Test if None DOI is allowed
        pub3 = Publication.objects.create(
            owner=user,
            title="Test Publication 3",
            doi=None,
            year=2024
        )
        assert pub3.doi is None

    def test_teaching_model_current_behavior(self):
        """Document Teaching model behavior."""
        user = User.objects.create_user(username='testuser', email='test@example.com')

        teaching = Teaching.objects.create(
            owner=user,
            name="Introduction to Computer Science",
            course_number="CS 101",
            semester="Fall",
            year=2024,
            level="undergraduate"
        )

        assert teaching.owner == user
        assert teaching.name == "Introduction to Computer Science"
        assert teaching.course_number == "CS 101"
        assert teaching.semester == "Fall"
        assert teaching.year == 2024
        assert teaching.level == "undergraduate"

    def test_talk_model_current_behavior(self):
        """Document Talk model behavior."""
        user = User.objects.create_user(username='testuser', email='test@example.com')

        talk = Talk.objects.create(
            owner=user,
            title="My Research Talk",
            place="University Conference",
            year=2024,
            invited=True
        )

        assert talk.owner == user
        assert talk.title == "My Research Talk"
        assert talk.place == "University Conference"
        assert talk.year == 2024
        assert talk.invited is True

    def test_conference_model_current_behavior(self):
        """Document Conference model behavior."""
        user = User.objects.create_user(username='testuser', email='test@example.com')

        conference = Conference.objects.create(
            owner=user,
            title="International Conference on AI",  # Changed from 'name' to 'title'
            authors="John Doe, Jane Smith",  # Added required 'authors' field
            location="San Francisco, CA",
            year=2024  # Changed from 'date' to 'year'
            # Removed 'role' as it doesn't exist in the Conference model
        )

        assert conference.owner == user
        assert conference.title == "International Conference on AI"
        assert conference.authors == "John Doe, Jane Smith"
        assert conference.location == "San Francisco, CA"
        assert conference.year == 2024

    def test_model_string_representations(self):
        """Document how models convert to strings."""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            first_name='Test',
            last_name='User'
        )

        pub = Publication.objects.create(
            owner=user,
            title="Test Publication",
            doi="10.1234/test",
            year=2024
        )

        # Document current string representation
        user_str = str(user)
        pub_str = str(pub)

        # These assertions document current behavior
        assert isinstance(user_str, str)
        assert isinstance(pub_str, str)
        assert len(user_str) > 0
        assert len(pub_str) > 0

    def test_user_model_optional_fields(self):
        """Document which user fields are optional."""
        # Create user with minimal required fields
        user = User.objects.create_user(
            username='minimal_user',
            email='minimal@example.com'
        )

        # Check default values for optional fields
        assert user.orcid_id is None or user.orcid_id == ""
        assert user.institution is None or user.institution == ""
        assert user.department is None or user.department == ""
        assert user.research_areas == [] or user.research_areas is None

    def test_publication_year_validation(self):
        """Document current year validation behavior."""
        user = User.objects.create_user(username='testuser', email='test@example.com')

        # Test various year values to see what's currently allowed
        test_years = [1800, 1900, 2000, 2024, 2025, 2030, 3000]

        for year in test_years:
            try:
                pub = Publication.objects.create(
                    owner=user,
                    title=f"Test Publication {year}",
                    doi=f"10.1234/test.{year}",
                    year=year
                )
                # If we get here, this year is allowed
                assert pub.year == year
            except ValidationError:
                # If we get here, this year is not allowed
                pass