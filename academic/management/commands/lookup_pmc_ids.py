"""
Django management command to lookup PMC IDs for existing publications using DOI or PMID
"""
import logging
import requests
import time
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from Bio import Entrez

from academic.models import Publication, PMCCache

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Lookup PMC IDs for existing publications using DOI or PMID'

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
            help='Seconds to wait between API calls (default: 1.0)'
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        dry_run = options.get('dry_run')
        rate_limit = options.get('rate_limit')

        # Set email for Entrez
        Entrez.email = 'noreply@example.com'

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

        if not publications.exists():
            self.stdout.write(self.style.WARNING("No publications found"))
            return

        # Filter to publications that don't already have PMC IDs
        publications_without_pmc = []
        already_have_pmc = 0
        skipped_ignored = 0
        skipped_preprints = 0
        skipped_no_pmid = 0

        for pub in publications:
            # Skip ignored publications
            if pub.is_ignored:
                skipped_ignored += 1
                continue

            # Skip preprints (they won't have PMC IDs)
            if pub.is_preprint:
                skipped_preprints += 1
                continue

            # Skip if no PMID and no DOI (PMC requires at least one)
            pmid = pub.identifiers.get('pmid') if pub.identifiers else None
            if not pmid and not pub.doi:
                skipped_no_pmid += 1
                continue

            if pub.identifiers and pub.identifiers.get('pmcid'):
                already_have_pmc += 1
            else:
                publications_without_pmc.append(pub)

        self.stdout.write(f"Found {len(publications_without_pmc)} publications without PMC IDs")
        self.stdout.write(f"Publications already with PMC IDs: {already_have_pmc}")
        if skipped_ignored > 0:
            self.stdout.write(f"Skipped ignored publications: {skipped_ignored}")
        if skipped_preprints > 0:
            self.stdout.write(f"Skipped preprints: {skipped_preprints}")
        if skipped_no_pmid > 0:
            self.stdout.write(f"Skipped publications without PMID or DOI: {skipped_no_pmid}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        if not publications_without_pmc:
            self.stdout.write(self.style.SUCCESS("All publications already have PMC IDs where available!"))
            return

        # Lookup PMC IDs
        successful_lookups = 0
        failed_lookups = 0
        updated_count = 0

        for pub in publications_without_pmc:
            self.stdout.write(f"\nLooking up PMC ID for: {pub.title[:100]}...")

            try:
                pmc_id, was_cached = self.lookup_pmc_id(pub)

                if pmc_id:
                    self.stdout.write(f"  Found PMC ID: {pmc_id}")
                    successful_lookups += 1

                    if not dry_run:
                        self.update_publication_pmc_id(pub, pmc_id)
                    updated_count += 1
                else:
                    self.stdout.write(f"  No PMC ID found")
                    failed_lookups += 1

                # Rate limiting - only delay if we made an API call (not cache hit)
                if not was_cached:
                    time.sleep(rate_limit)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error: {str(e)}"))
                failed_lookups += 1
                # Still apply rate limit on errors since they might be API-related
                time.sleep(rate_limit)

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== SUMMARY ===\n"
                f"PMC IDs found: {successful_lookups}\n"
                f"No PMC ID found: {failed_lookups}\n"
                f"Publications updated: {updated_count}\n"
                f"Already had PMC IDs: {already_have_pmc}"
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No actual changes were made"))

    def lookup_pmc_id(self, publication):
        """
        Lookup PMC ID for a publication using DOI or PMID
        First checks cache, then makes API calls if needed

        Returns:
            tuple: (pmc_id, was_cached) where was_cached is True if result came from cache
        """
        pmc_id = None

        # Try PMID first if available (more direct)
        pmid = publication.identifiers.get('pmid') if publication.identifiers else None
        if pmid:
            # Check cache first
            cached_pmcid = PMCCache.get_cached_pmcid(pmid, publication.doi)
            if cached_pmcid:
                self.stdout.write(f"    Found in cache: {cached_pmcid}")
                return cached_pmcid, True

            # If not in cache, lookup via API
            pmc_id = self.lookup_pmc_by_pmid(pmid)
            if pmc_id:
                # Cache the result
                PMCCache.cache_pmcid_mapping(pmid, pmc_id, publication.doi)
                return pmc_id, False

        # Try DOI if no PMC found via PMID
        if publication.doi and not pmid:  # Only use DOI if we don't have PMID
            pmc_id = self.lookup_pmc_by_doi(publication.doi)
            if pmc_id:
                # If we found PMID during DOI lookup, also cache that mapping
                # This will be handled in lookup_pmc_by_doi method
                return pmc_id, False

        # Don't search by title - too unreliable

        return None, False

    def lookup_pmc_by_doi(self, doi):
        """Lookup PMC ID using DOI via PubMed API"""
        try:
            self.stdout.write(f"    Searching by DOI: {doi}")

            # Search PubMed for the DOI
            search_handle = Entrez.esearch(
                db='pubmed',
                term=f'{doi}[DOI]',
                retmax=1
            )
            search_result = Entrez.read(search_handle)
            search_handle.close()

            if search_result['IdList']:
                pmid = search_result['IdList'][0]
                # Now look up the PMC ID using the found PMID
                # But don't print duplicate messages
                pmc_id = self.lookup_pmc_by_pmid(pmid, print_message=False)
                if pmc_id:
                    # Cache the mapping we found
                    PMCCache.cache_pmcid_mapping(pmid, pmc_id, doi)
                return pmc_id

        except Exception as e:
            logger.warning(f"Error looking up PMC by DOI {doi}: {str(e)}")

        return None

    def lookup_pmc_by_pmid(self, pmid, print_message=True):
        """Lookup PMC ID using PMID via PubMed API"""
        try:
            if print_message:
                self.stdout.write(f"    Searching by PMID: {pmid}")

            # Fetch the publication record
            fetch_handle = Entrez.efetch(
                db='pubmed',
                id=str(pmid),
                retmode='xml'
            )
            records = Entrez.read(fetch_handle)
            fetch_handle.close()

            if records['PubmedArticle']:
                record = records['PubmedArticle'][0]
                return self.extract_pmc_from_record(record)

        except Exception as e:
            logger.warning(f"Error looking up PMC by PMID {pmid}: {str(e)}")

        return None

    def extract_pmc_from_record(self, record):
        """Extract PMC ID from PubMed record"""
        try:
            if ('PubmedData' in record and 'ArticleIdList' in record['PubmedData']):
                for article_id in record['PubmedData']['ArticleIdList']:
                    if hasattr(article_id, 'attributes') and article_id.attributes.get('IdType') == 'pmc':
                        pmc_id = str(article_id)
                        # Ensure PMC ID starts with PMC
                        if not pmc_id.startswith('PMC'):
                            pmc_id = 'PMC' + pmc_id
                        return pmc_id
        except Exception as e:
            logger.warning(f"Error extracting PMC from record: {str(e)}")

        return None

    def update_publication_pmc_id(self, publication, pmc_id):
        """Update the PMC ID for a publication"""
        try:
            if not publication.identifiers:
                publication.identifiers = {}

            publication.identifiers['pmcid'] = pmc_id

            # Don't add PMC link to the links dictionary since it will be
            # displayed automatically via the identifiers.pmcid field
            # This prevents duplicate PMC links in the UI

            # Mark as manually edited to preserve this information
            if not publication.manual_edits:
                publication.manual_edits = {}
            publication.manual_edits['identifiers'] = True

            publication.save()

        except Exception as e:
            logger.error(f"Error updating publication {publication.id}: {str(e)}")