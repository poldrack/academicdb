"""
Test CV formatting functionality, particularly author string formatting
"""
import pytest
from academic.cv_renderer import mk_author_string, format_publication
from academic.models import Publication, AcademicUser


class TestAuthorStringFormatting:
    """Test author string formatting for CV generation"""

    def test_short_author_list_formatting(self):
        """Test that short author lists are formatted correctly"""
        authors = ["Smith, J", "Jones, A"]
        result = mk_author_string(authors)
        # Should end with ". " for short lists
        assert result.endswith(". ")
        assert result == "Smith, J, Jones, A. "

    def test_long_author_list_with_et_al_formatting(self):
        """Test that long author lists with et al. have proper spacing"""
        # Create a list with more than 10 authors to trigger et al.
        authors = [f"Author{i}, A" for i in range(15)]
        result = mk_author_string(authors, maxlen=10, n_to_show=3)

        # Should end with "et al." not "et al. "
        assert result.endswith("et al.")
        assert "Author0, A, Author1, A, Author2, A et al." == result

    def test_cv_citation_spacing_with_et_al(self):
        """Test that CV citations have proper spacing between et al. and year"""
        # This test should reproduce the reported spacing issue
        # When mk_author_string returns "Author1, A, Author2, A, Author3, A et al."
        # and it's used in f"{authors_str}({year})", we get "et al.(2024)"
        # instead of "et al. (2024)"

        authors = [f"Author{i}, A" for i in range(15)]
        authors_str = mk_author_string(authors, maxlen=10, n_to_show=3)
        year = 2024

        # This simulates the current problematic formatting
        problematic_format = f"{authors_str}({year})"

        # This confirms the problem existed
        assert "et al.(2024)" in problematic_format

        # After the fix, the format_publication function should handle this correctly
        # The fix is now implemented in the format_publication function


@pytest.mark.django_db
class TestPublicationCVFormatting:
    """Test complete publication formatting for CV"""

    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing"""
        return AcademicUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            orcid_id='0000-0000-0000-0001'
        )

    @pytest.fixture
    def sample_publication_many_authors(self, sample_user):
        """Create a sample publication with many authors"""
        authors_data = [{"name": f"Author{i}, A"} for i in range(15)]

        return Publication.objects.create(
            owner=sample_user,
            title="Test Publication with Many Authors",
            year=2024,
            doi="10.1000/test.2024.001",
            authors=authors_data,
            publication_name="Test Journal"
        )

    def test_publication_cv_format_et_al_spacing(self, sample_publication_many_authors):
        """Test that publication CV formatting has proper et al. spacing"""
        formatted = format_publication(sample_publication_many_authors)

        # Should not contain "et al.(" - this is the bug we're fixing
        assert "et al.(" not in formatted

        # Should contain "et al. (" with proper spacing
        assert "et al. (" in formatted