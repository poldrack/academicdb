"""
Test CV formatting functionality, particularly author string formatting
"""
import pytest
from datetime import date
from academic.cv_renderer import mk_author_string, format_publication, get_heading, get_education, get_distinctions, get_funding, get_preprints, get_conferences, get_editorial_activities
from academic.models import Publication, AcademicUser, ProfessionalActivity, Funding, Conference, Editorial


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


@pytest.mark.django_db
class TestCVAddressFormatting:
    """Test CV heading and address formatting"""

    @pytest.fixture
    def sample_user_with_address(self):
        """Create a sample user with full address information"""
        return AcademicUser.objects.create_user(
            username='addressuser',
            email='address@example.com',
            orcid_id='0000-0000-0000-0002',
            first_name='John',
            last_name='Doe',
            department='Department of Testing',
            institution='Test University',
            address1='123 Main Street',
            city='Test City',
            state='CA',
            zip_code='12345',
            country='USA'
        )

    def test_heading_excludes_country(self, sample_user_with_address):
        """Test that the CV heading does not include country in the address"""
        heading = get_heading(sample_user_with_address)

        # Should include all address components except country
        assert 'Department of Testing' in heading
        assert 'Test University' in heading
        assert '123 Main Street' in heading
        assert 'Test City, CA, 12345' in heading

        # Should NOT include country
        assert 'USA' not in heading


@pytest.mark.django_db
class TestEducationAndTraining:
    """Test education and training section formatting"""

    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing"""
        return AcademicUser.objects.create_user(
            username='eduuser',
            email='edu@example.com',
            orcid_id='0000-0000-0000-0003',
            first_name='Jane',
            last_name='Smith'
        )

    @pytest.fixture
    def education_activities(self, sample_user):
        """Create education and qualification activities"""
        # Create an education activity
        education = ProfessionalActivity.objects.create(
            owner=sample_user,
            activity_type='education',
            title='Ph.D. in Computer Science',
            organization='Stanford University',
            city='Stanford',
            region='CA',
            start_date=date(2010, 9, 1),
            end_date=date(2015, 6, 1)
        )

        # Create a qualification activity (e.g., postdoc)
        qualification = ProfessionalActivity.objects.create(
            owner=sample_user,
            activity_type='qualification',
            title='Postdoctoral Training',
            organization='MIT',
            city='Cambridge',
            region='MA',
            start_date=date(2015, 7, 1),
            end_date=date(2017, 6, 30)
        )

        return education, qualification

    def test_education_includes_both_education_and_qualification(self, sample_user, education_activities):
        """Test that get_education includes both education and qualification activities"""
        education_section = get_education(sample_user)

        # Should include the education entry
        assert 'Ph.D. in Computer Science' in education_section
        assert 'Stanford University' in education_section

        # Should ALSO include the qualification entry (postdoc)
        assert 'Postdoctoral Training' in education_section
        assert 'MIT' in education_section

    def test_education_ordered_chronologically_forward(self, sample_user):
        """Test that education entries are ordered chronologically (earliest first)"""
        # Create multiple education entries with different dates
        ProfessionalActivity.objects.create(
            owner=sample_user,
            activity_type='education',
            title='Bachelor of Science',
            organization='University A',
            start_date=date(2005, 9, 1),
            end_date=date(2009, 6, 1)
        )

        ProfessionalActivity.objects.create(
            owner=sample_user,
            activity_type='education',
            title='Master of Science',
            organization='University B',
            start_date=date(2009, 9, 1),
            end_date=date(2011, 6, 1)
        )

        ProfessionalActivity.objects.create(
            owner=sample_user,
            activity_type='education',
            title='Ph.D.',
            organization='University C',
            start_date=date(2011, 9, 1),
            end_date=date(2015, 6, 1)
        )

        education_section = get_education(sample_user)

        # Find positions of each degree in the output
        bachelor_pos = education_section.find('Bachelor of Science')
        master_pos = education_section.find('Master of Science')
        phd_pos = education_section.find('Ph.D.')

        # Bachelor's should come first (earliest chronologically)
        # Then Master's, then Ph.D. (forward chronological order)
        assert bachelor_pos < master_pos, "Bachelor's should appear before Master's in forward chronological order"
        assert master_pos < phd_pos, "Master's should appear before Ph.D. in forward chronological order"


@pytest.mark.django_db
class TestHonorsAndAwards:
    """Test honors and awards section formatting"""

    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing"""
        return AcademicUser.objects.create_user(
            username='honorsuser',
            email='honors@example.com',
            orcid_id='0000-0000-0000-0004',
            first_name='John',
            last_name='Awards'
        )

    @pytest.fixture
    def award_activities(self, sample_user):
        """Create distinction and invited position activities"""
        # Create a distinction/award
        distinction = ProfessionalActivity.objects.create(
            owner=sample_user,
            activity_type='distinction',
            title='Best Paper Award',
            organization='IEEE Computer Society',
            start_date=date(2020, 5, 1)
        )

        # Create an invited position
        invited_position = ProfessionalActivity.objects.create(
            owner=sample_user,
            activity_type='invited_position',
            title='Visiting Scholar',
            organization='Harvard University',
            start_date=date(2019, 9, 1),
            end_date=date(2020, 8, 31)
        )

        return distinction, invited_position

    def test_honors_includes_both_distinctions_and_invited_positions(self, sample_user, award_activities):
        """Test that get_distinctions includes both distinction and invited_position activities"""
        honors_section = get_distinctions(sample_user)

        # Should include the distinction entry
        assert 'Best Paper Award' in honors_section
        assert 'IEEE Computer Society' in honors_section

        # Should ALSO include the invited position entry
        assert 'Visiting Scholar' in honors_section
        assert 'Harvard University' in honors_section


@pytest.mark.django_db
class TestFundingSorting:
    """Test funding section sorting"""

    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing"""
        return AcademicUser.objects.create_user(
            username='fundinguser',
            email='funding@example.com',
            orcid_id='0000-0000-0000-0005',
            first_name='Grant',
            last_name='Getter'
        )

    @pytest.fixture
    def funding_grants(self, sample_user):
        """Create funding grants with different end dates"""
        # Grant ending in 2023 (should appear later in output)
        grant1 = Funding.objects.create(
            owner=sample_user,
            agency='NSF',
            title='Early Research Grant',
            role='PI',
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31),
            grant_number='NSF-001'
        )

        # Grant ending in 2026, but starting EARLIER than the one below
        grant2 = Funding.objects.create(
            owner=sample_user,
            agency='NIH',
            title='Late Research Grant',
            role='PI',
            start_date=date(2019, 1, 1),  # Earlier start date - will appear first under current sorting
            end_date=date(2026, 12, 31),  # Later end date - should appear first under desired sorting
            grant_number='NIH-002'
        )

        # Another active grant ending in 2025, but starting LATER than the one above
        grant3 = Funding.objects.create(
            owner=sample_user,
            agency='DOE',
            title='Middle Research Grant',
            role='PI',
            start_date=date(2024, 1, 1),  # Later start date - will appear second under current sorting
            end_date=date(2025, 12, 31),   # Earlier end date - should appear second under desired sorting
            grant_number='DOE-003'
        )

        return grant1, grant2, grant3

    def test_funding_sorted_by_end_date(self, sample_user, funding_grants):
        """Test that funding is sorted by end date in descending order within each section"""
        funding_section = get_funding(sample_user)

        # Find positions of the active grants in the output
        late_grant_pos = funding_section.find('Late Research Grant')  # ends 2026
        middle_grant_pos = funding_section.find('Middle Research Grant')  # ends 2025

        # Within the active section, the grant ending in 2026 should appear before the one ending in 2025
        assert late_grant_pos < middle_grant_pos, "Active funding should be sorted by end date in descending order"


@pytest.mark.django_db
class TestFundingGrantNumbers:
    """Test grant number display in funding section"""

    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing"""
        return AcademicUser.objects.create_user(
            username='grantuser',
            email='grant@example.com',
            orcid_id='0000-0000-0000-0006',
            first_name='Grant',
            last_name='Numbers'
        )

    @pytest.fixture
    def funding_with_grant_number(self, sample_user):
        """Create funding with grant number"""
        return Funding.objects.create(
            owner=sample_user,
            agency='National Science Foundation',
            title='Research Grant with Number',
            role='pi',
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31),
            grant_number='NSF-12345'
        )

    def test_grant_number_displayed_after_agency(self, sample_user, funding_with_grant_number):
        """Test that grant number is displayed after agency name when present"""
        funding_section = get_funding(sample_user)

        # Should include the grant number after the agency name
        assert 'National Science Foundation NSF-12345' in funding_section

    def test_grant_number_with_url_creates_link(self, sample_user):
        """Test that grant number with URL creates a clickable link"""
        # Create funding with both grant number and URL
        funding_with_url = Funding.objects.create(
            owner=sample_user,
            agency='National Institutes of Health',
            title='Research Grant with URL',
            role='pi',
            start_date=date(2021, 1, 1),
            end_date=date(2024, 12, 31),
            grant_number='NIH-67890',
            additional_info={'url': 'https://grants.nih.gov/67890'}
        )

        funding_section = get_funding(sample_user)

        # Should include a LaTeX hyperlink
        assert '\\href{https://grants.nih.gov/67890}{\\textit{NIH-67890}}' in funding_section


@pytest.mark.django_db
class TestPreprintSorting:
    """Test preprint section sorting"""

    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing"""
        return AcademicUser.objects.create_user(
            username='preprintuser',
            email='preprint@example.com',
            orcid_id='0000-0000-0000-0007',
            first_name='Pre',
            last_name='Print'
        )

    @pytest.fixture
    def preprint_publications(self, sample_user):
        """Create preprint publications with different years and authors"""
        # 2023 preprint with "Alpha" as first author (alphabetically first)
        preprint1 = Publication.objects.create(
            owner=sample_user,
            title='2023 Preprint by Alpha',
            year=2023,
            doi='10.1101/2023.01.01.alpha',
            publication_type='preprint',
            publication_name='bioRxiv',
            authors=[{"name": "Alpha, A"}, {"name": "Beta, B"}]
        )

        # 2024 preprint with "Zulu" as first author (alphabetically last)
        preprint2 = Publication.objects.create(
            owner=sample_user,
            title='2024 Preprint by Zulu',
            year=2024,
            doi='10.1101/2024.01.01.zulu',
            publication_type='preprint',
            publication_name='bioRxiv',
            authors=[{"name": "Zulu, Z"}, {"name": "Yankee, Y"}]
        )

        return preprint1, preprint2

    def test_preprints_sorted_by_reverse_chronological_order(self, sample_user, preprint_publications):
        """Test that preprints are sorted by year in descending order (most recent first)"""
        preprint_section = get_preprints(sample_user)

        # Find positions of the two preprints in the output
        preprint_2023_pos = preprint_section.find('2023 Preprint by Alpha')
        preprint_2024_pos = preprint_section.find('2024 Preprint by Zulu')

        # The 2024 preprint should appear before the 2023 preprint (reverse chronological)
        assert preprint_2024_pos < preprint_2023_pos, "Preprints should be sorted by year in descending order"


@pytest.mark.django_db
class TestConferenceSorting:
    """Test conference presentation sorting"""

    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing"""
        return AcademicUser.objects.create_user(
            username='confuser',
            email='conf@example.com',
            orcid_id='0000-0000-0000-0008',
            first_name='Conf',
            last_name='Speaker'
        )

    @pytest.fixture
    def conference_presentations(self, sample_user):
        """Create conference presentations in same year with different months"""
        # February presentation (should appear after November alphabetically but chronologically later)
        conf1 = Conference.objects.create(
            owner=sample_user,
            title='February Conference Talk',
            year=2024,
            month='February',
            location='Conference Center A',
            conference_name='Spring Conference'
        )

        # November presentation (should appear first chronologically despite being alphabetically later)
        conf2 = Conference.objects.create(
            owner=sample_user,
            title='November Conference Talk',
            year=2024,
            month='November',
            location='Conference Center B',
            conference_name='Fall Conference'
        )

        return conf1, conf2

    def test_conferences_sorted_by_month_within_year(self, sample_user, conference_presentations):
        """Test that conference presentations are sorted by month in reverse chronological order within the year"""
        conference_section = get_conferences(sample_user)

        # Find positions of the two presentations in the output
        february_pos = conference_section.find('February Conference Talk')
        november_pos = conference_section.find('November Conference Talk')

        # November should appear before February (reverse chronological order)
        assert november_pos < february_pos, "Conference presentations should be sorted by month in reverse chronological order within the year"


@pytest.mark.django_db
class TestEditorialActivitiesCV:
    """Test editorial activities in CV generation"""

    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing"""
        return AcademicUser.objects.create_user(
            username='editorialcvuser',
            email='editorialcv@example.com',
            orcid_id='0000-0000-0000-0010',
            first_name='Editorial',
            last_name='CVUser'
        )

    @pytest.fixture
    def editorial_activities(self, sample_user):
        """Create editorial activities grouped by role"""
        # Senior Editor activities
        Editorial.objects.create(
            owner=sample_user,
            role='Senior Editor',
            journal='Psychological Science',
            dates='2024-'
        )

        # Editorial board activities
        Editorial.objects.create(
            owner=sample_user,
            role='Editorial board',
            journal='Trends in Cognitive Sciences',
            dates=''
        )

        Editorial.objects.create(
            owner=sample_user,
            role='Editorial board',
            journal='Cerebral Cortex',
            dates=''
        )

        # Handling Editor activities
        Editorial.objects.create(
            owner=sample_user,
            role='Handling Editor (ad hoc)',
            journal='Proceedings of the National Academy of Sciences',
            dates=''
        )

    def test_editorial_activities_grouped_by_role(self, sample_user, editorial_activities):
        """Test that editorial activities are grouped by role in CV using compact format"""
        editorial_section = get_editorial_activities(sample_user)

        # Should include the Editorial duties section
        assert '\\section*{Editorial duties}' in editorial_section

        # Should use compact format without subsections
        assert '\\subsection*{' not in editorial_section

        # Should group by role with colon format
        assert 'Editorial board:' in editorial_section
        assert 'Handling Editor (ad hoc):' in editorial_section
        assert 'Senior Editor:' in editorial_section

        # Should include all journals
        assert 'Psychological Science, 2024-' in editorial_section
        assert 'Trends in Cognitive Sciences' in editorial_section
        assert 'Cerebral Cortex' in editorial_section
        assert 'Proceedings of the National Academy of Sciences' in editorial_section

    def test_editorial_activities_compact_format(self, sample_user):
        """Test that editorial activities use compact format with journals listed after each role"""
        # Create multiple editorial activities with same and different roles
        Editorial.objects.create(
            owner=sample_user,
            role='Senior Editor',
            journal='Psychological Science',
            dates='2024-'
        )

        Editorial.objects.create(
            owner=sample_user,
            role='Handling Editor (ad hoc)',
            journal='Proceedings of the National Academy of Sciences',
            dates=''
        )

        Editorial.objects.create(
            owner=sample_user,
            role='Handling Editor (ad hoc)',
            journal='eLife',
            dates=''
        )

        Editorial.objects.create(
            owner=sample_user,
            role='Editorial board',
            journal='Trends in Cognitive Sciences',
            dates=''
        )

        Editorial.objects.create(
            owner=sample_user,
            role='Editorial board',
            journal='Cerebral Cortex',
            dates=''
        )

        Editorial.objects.create(
            owner=sample_user,
            role='Editorial board',
            journal='Human Brain Mapping',
            dates=''
        )

        editorial_section = get_editorial_activities(sample_user)

        # Should NOT use subsections (compact format)
        assert '\\subsection*{' not in editorial_section, "Compact format should not use subsections"

        # Should use compact format: "Role: journal1, journal2, journal3"
        # Senior Editor should be on one line (with dates)
        assert 'Senior Editor: Psychological Science, 2024-' in editorial_section

        # Handling Editor should list both journals on same line (alphabetical order)
        assert 'Handling Editor (ad hoc): Proceedings of the National Academy of Sciences, eLife' in editorial_section

        # Editorial board should list all journals on same line (alphabetical order due to sorting)
        assert 'Editorial board: Cerebral Cortex, Human Brain Mapping, Trends in Cognitive Sciences' in editorial_section