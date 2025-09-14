"""
Django management command to enrich publications with Scopus author IDs by looking up via DOI
"""
import logging
import time
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from pybliometrics.scopus import AbstractRetrieval
import pybliometrics

from academic.models import Publication

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Enrich publications with Scopus author IDs by looking up publications via DOI'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to process publications for (optional - if not provided, processes all users)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )
        parser.add_argument(
            '--rate-limit',
            type=float,
            default=1.0,
            help='Seconds to wait between Scopus API calls (default: 1.0)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if authors already have Scopus IDs'
        )

    def handle(self, *args, **options):
        # Initialize Scopus
        try:
            pybliometrics.scopus.init()
        except Exception as e:
            raise CommandError(f"Failed to initialize Scopus: {str(e)}")

        user_id = options.get('user_id')
        dry_run = options.get('dry_run')
        rate_limit = options.get('rate_limit')
        force = options.get('force')
        self.force_update = force  # Store as instance variable

        # Get publications to process
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                publications = Publication.objects.filter(owner=user)
                self.stdout.write(f"Processing publications for user: {user.username}")
            except User.DoesNotExist:
                raise CommandError(f"User with ID {user_id} not found")
        else:
            publications = Publication.objects.all()
            self.stdout.write("Processing publications for all users")

        # Filter to publications with DOIs
        publications = publications.exclude(doi__isnull=True).exclude(doi__exact='')

        if not publications.exists():
            self.stdout.write(self.style.WARNING("No publications with DOIs found"))
            return

        self.stdout.write(f"Found {publications.count()} publications with DOIs to process")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Process statistics
        processed = 0
        enriched = 0
        already_complete = 0
        failed = 0
        not_in_scopus = 0

        for pub in publications:
            # Skip if all authors already have Scopus IDs (unless force flag is set)
            if not force and self.all_authors_have_scopus_ids(pub):
                already_complete += 1
                self.stdout.write(f"✓ {pub.title[:60]}... - Already complete")
                continue

            self.stdout.write(f"\nProcessing: {pub.title[:60]}...")
            self.stdout.write(f"  DOI: {pub.doi}")

            try:
                # Look up the publication in Scopus by DOI
                scopus_data = self.get_scopus_data_by_doi(pub.doi)

                if scopus_data:
                    # Extract author information from Scopus
                    scopus_authors = self.extract_scopus_authors(scopus_data)

                    if scopus_authors:
                        self.stdout.write(f"  Found {len(scopus_authors)} authors in Scopus")

                        # Match and update authors
                        updated = self.update_publication_authors(pub, scopus_authors, dry_run)

                        if updated:
                            enriched += 1
                            self.stdout.write(self.style.SUCCESS(f"  ✓ Enriched {updated} authors with Scopus IDs"))
                        else:
                            self.stdout.write("  No new Scopus IDs added")
                    else:
                        self.stdout.write("  No author data in Scopus record")
                else:
                    not_in_scopus += 1
                    self.stdout.write("  Not found in Scopus")

                processed += 1

                # Rate limiting
                time.sleep(rate_limit)

            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
                time.sleep(rate_limit)  # Still wait on errors

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'='*60}\n"
                f"SUMMARY\n"
                f"{'='*60}\n"
                f"Total processed: {processed}\n"
                f"Publications enriched: {enriched}\n"
                f"Already complete: {already_complete}\n"
                f"Not in Scopus: {not_in_scopus}\n"
                f"Failed: {failed}"
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No actual changes were made"))

    def all_authors_have_scopus_ids(self, publication):
        """Check if all authors in a publication already have Scopus IDs"""
        if not publication.authors:
            return False

        for author in publication.authors:
            if isinstance(author, dict) and not author.get('scopus_id'):
                return False

        return True

    def get_scopus_data_by_doi(self, doi):
        """Retrieve publication data from Scopus using DOI"""
        try:
            # Use AbstractRetrieval to get full publication details
            # id_type='doi' tells Scopus we're searching by DOI
            abstract = AbstractRetrieval(doi, id_type='doi', view='FULL')
            return abstract
        except Exception as e:
            logger.debug(f"Could not retrieve Scopus data for DOI {doi}: {str(e)}")
            return None

    def extract_scopus_authors(self, scopus_data):
        """Extract author information from Scopus data"""
        authors = []

        try:
            if hasattr(scopus_data, 'authors') and scopus_data.authors:
                for author in scopus_data.authors:
                    author_info = {
                        'scopus_id': author.auid,
                        'name': author.indexed_name,  # Format: "Lastname F."
                        'given_name': getattr(author, 'given_name', None),
                        'surname': getattr(author, 'surname', None),
                        'initials': getattr(author, 'initials', None),
                        'affiliation': []
                    }

                    # Add affiliation if available
                    if hasattr(author, 'affiliation') and author.affiliation:
                        if isinstance(author.affiliation, list):
                            author_info['affiliation'] = [aff.name for aff in author.affiliation if hasattr(aff, 'name')]
                        elif hasattr(author.affiliation, 'name'):
                            author_info['affiliation'] = [author.affiliation.name]

                    authors.append(author_info)

        except Exception as e:
            logger.error(f"Error extracting authors from Scopus data: {str(e)}")

        return authors

    def update_publication_authors(self, publication, scopus_authors, dry_run=False):
        """
        Update publication authors with Scopus IDs using positional matching
        Since DOI is the same, authors should be in the same order
        Returns the number of authors updated
        """
        updated_count = 0

        if not publication.authors:
            return 0

        # Create a copy of authors for updating
        updated_authors = publication.authors.copy()

        # Only proceed if we have the same number of authors or fewer in our publication
        # (Some sources may have fewer authors listed)
        max_authors = min(len(updated_authors), len(scopus_authors))

        for i in range(max_authors):
            pub_author = updated_authors[i]
            scopus_author = scopus_authors[i]

            if not isinstance(pub_author, dict):
                # Convert string author to dict format
                updated_authors[i] = {'name': str(pub_author)}
                pub_author = updated_authors[i]

            # Skip if already has Scopus ID (unless force flag is set in parent)
            if pub_author.get('scopus_id') and not self.force_update:
                continue

            # Update with Scopus ID using positional matching
            updated_authors[i]['scopus_id'] = scopus_author['scopus_id']

            # Optionally enrich with additional data
            if scopus_author.get('affiliation') and not pub_author.get('affiliation'):
                updated_authors[i]['affiliation'] = scopus_author['affiliation']

            pub_author_name = pub_author.get('name', 'Unknown')
            scopus_author_name = scopus_author.get('name', 'Unknown')
            self.stdout.write(f"    Position {i+1}: {pub_author_name} -> {scopus_author_name} (ID: {scopus_author['scopus_id']})")
            updated_count += 1

        # Save the updated authors
        if updated_count > 0 and not dry_run:
            publication.authors = updated_authors

            # Mark as having manual edits to preserve the Scopus IDs
            if not publication.manual_edits:
                publication.manual_edits = {}
            publication.manual_edits['authors'] = True

            publication.save()

        return updated_count

    def authors_match(self, pub_author_name, scopus_author):
        """
        Check if a publication author matches a Scopus author
        Uses multiple matching strategies
        """
        # Clean and normalize names
        pub_name_clean = pub_author_name.lower().strip()

        # Try indexed name (e.g., "Smith J.")
        if scopus_author.get('name'):
            scopus_indexed = scopus_author['name'].lower().strip().rstrip('.')
            if pub_name_clean == scopus_indexed:
                return True

            # Try reverse order (e.g., "J. Smith" vs "Smith J.")
            if self.names_match_reversed(pub_name_clean, scopus_indexed):
                return True

        # Try full name matching if we have surname and given name
        if scopus_author.get('surname') and scopus_author.get('given_name'):
            scopus_full = f"{scopus_author['given_name']} {scopus_author['surname']}".lower()
            scopus_full_reversed = f"{scopus_author['surname']} {scopus_author['given_name']}".lower()

            if pub_name_clean == scopus_full or pub_name_clean == scopus_full_reversed:
                return True

            # Try with initials
            if scopus_author.get('initials'):
                scopus_with_initials = f"{scopus_author['initials']} {scopus_author['surname']}".lower()
                scopus_with_initials_reversed = f"{scopus_author['surname']} {scopus_author['initials']}".lower()

                if pub_name_clean == scopus_with_initials or pub_name_clean == scopus_with_initials_reversed:
                    return True

        # Try matching last name and first initial
        return self.match_lastname_and_initial(pub_name_clean, scopus_author)

    def names_match_reversed(self, name1, name2):
        """Check if names match when order is reversed"""
        # Split and reverse
        parts1 = name1.replace(',', ' ').split()
        parts2 = name2.replace(',', ' ').split()

        if len(parts1) == 2 and len(parts2) == 2:
            # Try both orderings
            return (parts1[0] == parts2[1] and parts1[1] == parts2[0]) or \
                   (parts1[0] == parts2[0] and parts1[1] == parts2[1])

        return False

    def match_lastname_and_initial(self, pub_name, scopus_author):
        """Match based on last name and first initial"""
        surname = scopus_author.get('surname', '') or ''
        surname = surname.lower()
        initials = scopus_author.get('initials', '') or ''
        initials = initials.lower()

        if not surname:
            return False

        # Parse publication author name
        name_parts = pub_name.replace(',', ' ').split()

        if len(name_parts) >= 2:
            # Check if surname matches any part
            for i, part in enumerate(name_parts):
                if part == surname:
                    # Check if we have matching initials
                    other_parts = name_parts[:i] + name_parts[i+1:]
                    for other in other_parts:
                        if other and initials and other[0] == initials[0]:
                            return True

        return False