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

        # Check if author counts match - this is critical for accurate positional matching
        pub_author_count = len(updated_authors)
        scopus_author_count = len(scopus_authors)

        if pub_author_count != scopus_author_count:
            self.stdout.write(
                f"  ⚠️  Author count mismatch: Publication has {pub_author_count} authors, "
                f"Scopus has {scopus_author_count} authors"
            )
            self.stdout.write("  Using Scopus author list as authoritative source")

            # Replace entire author list with Scopus data when counts don't match
            return self.replace_authors_with_scopus_data(publication, scopus_authors, dry_run)

        # If counts match, proceed with positional matching
        self.stdout.write(f"  Author counts match ({pub_author_count}), using positional matching")
        max_authors = len(updated_authors)

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

            # Verify that this positional match makes sense by doing basic name validation
            pub_author_name = pub_author.get('name', 'Unknown')
            scopus_author_name = scopus_author.get('name', 'Unknown')

            # Basic validation: check if names are completely different (might indicate skipped author)
            if not self.names_reasonably_similar(pub_author_name, scopus_author_name):
                self.stdout.write(
                    f"    ⚠️  Position {i+1}: Names seem very different - "
                    f"{pub_author_name} vs {scopus_author_name}"
                )
                self.stdout.write("    Proceeding with positional match anyway (counts match)")

            # Update with Scopus ID using positional matching
            updated_authors[i]['scopus_id'] = scopus_author['scopus_id']

            # Optionally enrich with additional data
            if scopus_author.get('affiliation') and not pub_author.get('affiliation'):
                updated_authors[i]['affiliation'] = scopus_author['affiliation']

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

    def replace_authors_with_scopus_data(self, publication, scopus_authors, dry_run=False):
        """
        Replace the entire author list with Scopus data when author counts don't match.
        This ensures accuracy when there are discrepancies in author information.
        Returns the number of authors replaced.
        """
        if not scopus_authors:
            self.stdout.write("  No Scopus authors to replace with")
            return 0

        # Convert Scopus authors to the publication's author format
        new_authors = []
        for scopus_author in scopus_authors:
            author_dict = {
                'name': scopus_author.get('name', 'Unknown'),
                'scopus_id': scopus_author.get('scopus_id')
            }

            # Add additional fields if available
            if scopus_author.get('given_name'):
                author_dict['given_name'] = scopus_author['given_name']
            if scopus_author.get('surname'):
                author_dict['surname'] = scopus_author['surname']
            if scopus_author.get('initials'):
                author_dict['initials'] = scopus_author['initials']
            if scopus_author.get('affiliation'):
                author_dict['affiliation'] = scopus_author['affiliation']

            new_authors.append(author_dict)

        # Show what we're replacing
        old_count = len(publication.authors) if publication.authors else 0
        new_count = len(new_authors)
        self.stdout.write(f"  Replacing {old_count} authors with {new_count} Scopus authors:")

        for i, author in enumerate(new_authors):
            self.stdout.write(f"    Author {i+1}: {author['name']} (ID: {author.get('scopus_id', 'N/A')})")

        # Save the replacement
        if not dry_run:
            publication.authors = new_authors

            # Mark as having manual edits to preserve the Scopus data
            if not publication.manual_edits:
                publication.manual_edits = {}
            publication.manual_edits['authors'] = True

            # Add to edit history for audit trail
            if not publication.edit_history:
                publication.edit_history = []
            publication.edit_history.append({
                'timestamp': time.time(),
                'field': 'authors',
                'action': 'scopus_replacement',
                'reason': 'author_count_mismatch',
                'old_count': old_count,
                'new_count': new_count
            })

            publication.save()

        return new_count

    def update_authors_by_name_matching(self, publication, scopus_authors, dry_run=False):
        """
        Update publication authors with Scopus IDs using name-based matching
        Used when author counts don't match between publication and Scopus
        Returns the number of authors updated
        """
        updated_count = 0

        if not publication.authors:
            return 0

        # Create a copy of authors for updating
        updated_authors = publication.authors.copy()

        # Track which Scopus authors have been matched to avoid duplicates
        matched_scopus_indices = set()

        for i, pub_author in enumerate(updated_authors):
            if not isinstance(pub_author, dict):
                # Convert string author to dict format
                updated_authors[i] = {'name': str(pub_author)}
                pub_author = updated_authors[i]

            # Skip if already has Scopus ID (unless force flag is set)
            if pub_author.get('scopus_id') and not self.force_update:
                continue

            pub_author_name = pub_author.get('name', 'Unknown')

            # Try to find matching Scopus author by name
            best_match = None
            best_match_index = None

            for j, scopus_author in enumerate(scopus_authors):
                # Skip if this Scopus author already matched
                if j in matched_scopus_indices:
                    continue

                if self.authors_match(pub_author_name, scopus_author):
                    best_match = scopus_author
                    best_match_index = j
                    break

            if best_match:
                # Update with Scopus ID
                updated_authors[i]['scopus_id'] = best_match['scopus_id']

                # Optionally enrich with additional data
                if best_match.get('affiliation') and not pub_author.get('affiliation'):
                    updated_authors[i]['affiliation'] = best_match['affiliation']

                # Mark this Scopus author as matched
                matched_scopus_indices.add(best_match_index)

                scopus_author_name = best_match.get('name', 'Unknown')
                self.stdout.write(
                    f"    Name match: {pub_author_name} -> {scopus_author_name} "
                    f"(ID: {best_match['scopus_id']})"
                )
                updated_count += 1
            else:
                self.stdout.write(f"    No match found for: {pub_author_name}")

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

    def names_reasonably_similar(self, name1, name2):
        """
        Check if two names are reasonably similar for positional matching validation.
        This helps detect when an author might have been skipped in one of the records.
        Improved to handle cases like "J He" vs "He J." more robustly.
        """
        if not name1 or not name2:
            return False

        # Clean names for comparison
        clean1 = name1.lower().strip().replace(',', ' ').replace('.', '')
        clean2 = name2.lower().strip().replace(',', ' ').replace('.', '')

        # Exact match
        if clean1 == clean2:
            return True

        # Split into parts
        parts1 = [p for p in clean1.split() if p]  # Remove empty strings
        parts2 = [p for p in clean2.split() if p]  # Remove empty strings

        if not parts1 or not parts2:
            return False

        # Handle common case: "J He" vs "He J." (initial + surname vs surname + initial)
        if len(parts1) == 2 and len(parts2) == 2:
            # Check if one is initial+surname and the other is surname+initial
            if ((len(parts1[0]) == 1 and len(parts1[1]) > 1) and
                (len(parts2[1]) == 1 and len(parts2[0]) > 1) and
                parts1[0] == parts2[1] and parts1[1] == parts2[0]):
                return True

            # Check if they're in the same order but with different formatting
            if ((len(parts1[0]) == 1 and len(parts2[0]) == 1) and
                (len(parts1[1]) > 1 and len(parts2[1]) > 1) and
                parts1[0] == parts2[0] and parts1[1] == parts2[1]):
                return True

        # Check if any significant parts match (surnames, full first names)
        # At least one word longer than 2 characters should match
        for part1 in parts1:
            if len(part1) > 2:  # Skip initials for this check
                for part2 in parts2:
                    if len(part2) > 2 and part1 == part2:
                        return True

        # Check if last names match (assuming last word is surname)
        if len(parts1[-1]) > 1 and len(parts2[-1]) > 1:  # Allow single letter surnames
            if parts1[-1] == parts2[-1]:
                return True

        # Check if first names match (assuming first word is first name)
        if len(parts1[0]) > 1 and len(parts2[0]) > 1:  # Allow single letter first names
            if parts1[0] == parts2[0]:
                return True

        # Check for initial matches (handle "J" matching "J")
        # This covers cases where names have same initials but different formatting
        initials1 = [p for p in parts1 if len(p) == 1]
        initials2 = [p for p in parts2 if len(p) == 1]
        surnames1 = [p for p in parts1 if len(p) > 1]
        surnames2 = [p for p in parts2 if len(p) > 1]

        # If both have initials and surnames, check if they match
        if initials1 and initials2 and surnames1 and surnames2:
            # Check if any initial matches and any surname matches
            initial_match = any(i1 == i2 for i1 in initials1 for i2 in initials2)
            surname_match = any(s1 == s2 for s1 in surnames1 for s2 in surnames2)
            if initial_match and surname_match:
                return True

        return False