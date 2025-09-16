"""
Tests for Link model and related functionality.
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from academic.models import Link, Publication
from tests.factories import AcademicUserFactory, PublicationFactory, LinkFactory

User = get_user_model()


class TestLinkModel(TestCase):
    """Test Link model functionality."""

    def setUp(self):
        self.user = AcademicUserFactory()
        self.publication = PublicationFactory(owner=self.user)

    def test_link_creation(self):
        """Test basic link creation."""
        link = LinkFactory(
            owner=self.user,
            type='Code',
            doi=self.publication.doi,
            url='https://github.com/test/repo'
        )

        self.assertEqual(link.owner, self.user)
        self.assertEqual(link.type, 'Code')
        self.assertEqual(link.doi, self.publication.doi)
        self.assertEqual(link.url, 'https://github.com/test/repo')

    def test_link_str_representation(self):
        """Test string representation of Link."""
        link = LinkFactory(
            owner=self.user,
            type='Data',
            doi='10.1234/test',
            url='https://data.example.com'
        )

        expected = "Data: 10.1234/test -> https://data.example.com"
        self.assertEqual(str(link), expected)

    def test_doi_normalization_on_save(self):
        """Test that DOI is normalized when saving."""
        link = LinkFactory(
            owner=self.user,
            doi='https://doi.org/10.1234/test.123'
        )

        # DOI should be normalized (remove https://doi.org/ prefix)
        self.assertEqual(link.doi, '10.1234/test.123')

    def test_doi_normalization_variants(self):
        """Test normalization of different DOI formats."""
        test_cases = [
            ('https://doi.org/10.1234/test', '10.1234/test'),
            ('http://doi.org/10.1234/test', '10.1234/test'),
            ('doi:10.1234/test', '10.1234/test'),
            ('10.1234/test', '10.1234/test'),  # Already normalized
        ]

        for input_doi, expected_doi in test_cases:
            link = LinkFactory(owner=self.user, doi=input_doi)
            self.assertEqual(link.doi, expected_doi)

    def test_unique_constraint(self):
        """Test that the unique constraint works."""
        # Create first link
        LinkFactory(
            owner=self.user,
            type='Code',
            doi='10.1234/test',
            url='https://github.com/test'
        )

        # Try to create duplicate link - this should fail
        with self.assertRaises(Exception):  # IntegrityError
            LinkFactory(
                owner=self.user,
                type='Code',
                doi='10.1234/test',
                url='https://github.com/test'
            )

    def test_different_users_can_have_same_link(self):
        """Test that different users can have links to the same resource."""
        user2 = AcademicUserFactory()

        # Both users can have the same link
        link1 = LinkFactory(
            owner=self.user,
            type='Code',
            doi='10.1234/test',
            url='https://github.com/shared'
        )

        link2 = LinkFactory(
            owner=user2,
            type='Code',
            doi='10.1234/test',
            url='https://github.com/shared'
        )

        self.assertNotEqual(link1.id, link2.id)
        self.assertEqual(link1.url, link2.url)


class TestLinkMethods(TestCase):
    """Test Link model methods."""

    def setUp(self):
        self.user = AcademicUserFactory()
        self.publication = PublicationFactory(owner=self.user, doi='10.1234/test.123')

    def test_get_links_for_publication(self):
        """Test getting links for a specific publication."""
        # Create links for this publication
        link1 = LinkFactory(
            owner=self.user,
            type='Code',
            doi=self.publication.doi
        )
        link2 = LinkFactory(
            owner=self.user,
            type='Data',
            doi=self.publication.doi
        )

        # Create link for different publication
        other_pub = PublicationFactory(owner=self.user, doi='10.1234/other.456')
        LinkFactory(
            owner=self.user,
            type='OSF',
            doi=other_pub.doi
        )

        # Get links for our publication
        links = Link.get_links_for_publication(self.publication)

        self.assertEqual(len(links), 2)
        link_types = [link.type for link in links]
        self.assertIn('Code', link_types)
        self.assertIn('Data', link_types)

    def test_associate_with_publications(self):
        """Test associating links with publications."""
        # Create publications
        pub1 = PublicationFactory(owner=self.user, doi='10.1234/pub1')
        pub2 = PublicationFactory(owner=self.user, doi='10.1234/pub2')

        # Create links
        LinkFactory(owner=self.user, doi=pub1.doi, type='Code')
        LinkFactory(owner=self.user, doi=pub2.doi, type='Data')
        LinkFactory(owner=self.user, doi='10.1234/nonexistent', type='OSF')

        # Test association
        associated_count, not_found_dois = Link.associate_with_publications(self.user)

        self.assertEqual(associated_count, 2)  # pub1 and pub2 found
        self.assertEqual(len(not_found_dois), 1)  # nonexistent DOI
        self.assertIn('10.1234/nonexistent', not_found_dois)

    def test_associate_with_publications_no_links(self):
        """Test association when user has no links."""
        associated_count, not_found_dois = Link.associate_with_publications(self.user)

        self.assertEqual(associated_count, 0)
        self.assertEqual(len(not_found_dois), 0)

    def test_user_isolation(self):
        """Test that links are isolated between users."""
        user2 = AcademicUserFactory()

        # Create publications for both users with same DOI
        pub1 = PublicationFactory(owner=self.user, doi='10.1234/shared')
        pub2 = PublicationFactory(owner=user2, doi='10.1234/shared')

        # Create links for both users
        link1 = LinkFactory(owner=self.user, doi='10.1234/shared', type='Code')
        link2 = LinkFactory(owner=user2, doi='10.1234/shared', type='Data')

        # Test that each user only sees their own links
        user1_links = Link.get_links_for_publication(pub1)
        user2_links = Link.get_links_for_publication(pub2)

        self.assertEqual(len(user1_links), 1)
        self.assertEqual(user1_links[0].type, 'Code')
        self.assertEqual(len(user2_links), 1)
        self.assertEqual(user2_links[0].type, 'Data')


class TestLinkValidation(TestCase):
    """Test Link model validation."""

    def setUp(self):
        self.user = AcademicUserFactory()

    def test_clean_method_normalizes_doi(self):
        """Test that clean method normalizes DOI."""
        link = Link(
            owner=self.user,
            type='Code',
            doi='https://doi.org/10.1234/test',
            url='https://github.com/test'
        )

        link.clean()
        self.assertEqual(link.doi, '10.1234/test')

    def test_type_choices(self):
        """Test that type choices are validated."""
        # Valid type
        link = LinkFactory(owner=self.user, type='Code')
        self.assertEqual(link.type, 'Code')

        # Test all valid choices
        valid_types = ['Code', 'Data', 'OSF', 'Other']
        for type_choice in valid_types:
            link = LinkFactory(owner=self.user, type=type_choice)
            self.assertEqual(link.type, type_choice)

    def test_required_fields(self):
        """Test that required fields are enforced during validation."""
        from django.core.exceptions import ValidationError

        # Create link with missing required fields
        link = Link(owner=self.user)

        # Should raise ValidationError when full_clean() is called
        with self.assertRaises(ValidationError):
            link.full_clean()


class TestLinkViews(TestCase):
    """Test Link views and templates."""

    def setUp(self):
        self.client = Client()
        self.user = AcademicUserFactory()
        self.client.force_login(self.user)
        self.publication = PublicationFactory(owner=self.user, doi='10.1234/test.123')

    def test_links_show_on_publication_detail_page(self):
        """Test that links appear on the publication detail page."""
        # Create links for the publication
        link1 = LinkFactory(owner=self.user, type='Code', doi=self.publication.doi, url='https://github.com/test')
        link2 = LinkFactory(owner=self.user, type='Data', doi=self.publication.doi, url='https://data.test.com')

        # Visit the publication detail page
        url = reverse('academic:publication_detail', kwargs={'pk': self.publication.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check that links are in the context
        self.assertIn('external_links', response.context)
        external_links = response.context['external_links']
        self.assertEqual(len(external_links), 2)

        # Check that links appear in the HTML
        self.assertIn('Code', response.content.decode())
        self.assertIn('Data', response.content.decode())
        self.assertIn('https://github.com/test', response.content.decode())
        self.assertIn('https://data.test.com', response.content.decode())

    def test_link_count_shows_on_publication_list(self):
        """Test that link count appears on the publication list page."""
        # Create links
        LinkFactory(owner=self.user, type='Code', doi=self.publication.doi)
        LinkFactory(owner=self.user, type='Data', doi=self.publication.doi)

        # Visit the publication list page
        url = reverse('academic:publication_list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check that the publication has link_count attribute
        publications = response.context['publications']
        self.assertTrue(len(publications) > 0)

        # Find our publication
        for pub in publications:
            if pub.id == self.publication.id:
                self.assertEqual(pub.link_count, 2)
                break
        else:
            self.fail("Publication not found in list")

        # Check that link badge appears in HTML
        self.assertIn('class="badge bg-success', response.content.decode())
        self.assertIn('fa-link', response.content.decode())

    def test_links_list_page(self):
        """Test the links list page."""
        # Create links
        link1 = LinkFactory(owner=self.user, type='Code', doi='10.1234/test1')
        link2 = LinkFactory(owner=self.user, type='Data', doi='10.1234/test2')

        # Visit the links list page
        url = reverse('academic:links_list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('links', response.context)
        self.assertEqual(len(response.context['links']), 2)

        # Check content
        self.assertIn('Code', response.content.decode())
        self.assertIn('Data', response.content.decode())
        self.assertIn('10.1234/test1', response.content.decode())
        self.assertIn('10.1234/test2', response.content.decode())

    def test_user_isolation_in_views(self):
        """Test that users only see their own links in views."""
        # Create another user with links
        other_user = AcademicUserFactory()
        other_pub = PublicationFactory(owner=other_user, doi='10.1234/other')
        LinkFactory(owner=other_user, type='Code', doi=other_pub.doi)

        # Create link for our user
        LinkFactory(owner=self.user, type='Data', doi=self.publication.doi)

        # Check publication detail page
        url = reverse('academic:publication_detail', kwargs={'pk': self.publication.pk})
        response = self.client.get(url)

        external_links = response.context['external_links']
        self.assertEqual(len(external_links), 1)
        self.assertEqual(external_links[0].type, 'Data')

        # Check links list page
        url = reverse('academic:links_list')
        response = self.client.get(url)

        links = response.context['links']
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].type, 'Data')