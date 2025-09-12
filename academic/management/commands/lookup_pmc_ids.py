"""
Django management command to lookup PMC IDs for existing publications using DOI or PMID
"""
import logging
import requests
import time
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from Bio import Entrez

from academic.models import Publication

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

        for pub in publications:
            if pub.identifiers and pub.identifiers.get('pmcid'):
                already_have_pmc += 1
            else:
                publications_without_pmc.append(pub)

        self.stdout.write(f"Found {len(publications_without_pmc)} publications without PMC IDs")
        self.stdout.write(f"Publications already with PMC IDs: {already_have_pmc}")

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
                pmc_id = self.lookup_pmc_id(pub)
                
                if pmc_id:
                    self.stdout.write(f"  Found PMC ID: {pmc_id}")
                    successful_lookups += 1
                    
                    if not dry_run:
                        self.update_publication_pmc_id(pub, pmc_id)
                    updated_count += 1
                else:
                    self.stdout.write(f"  No PMC ID found")
                    failed_lookups += 1
                
                # Rate limiting
                time.sleep(rate_limit)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error: {str(e)}"))
                failed_lookups += 1
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
        """
        pmc_id = None
        
        # Try DOI first if available
        if publication.doi:
            pmc_id = self.lookup_pmc_by_doi(publication.doi)
            if pmc_id:
                return pmc_id
        
        # Try PMID if available
        pmid = publication.identifiers.get('pmid') if publication.identifiers else None
        if pmid:
            pmc_id = self.lookup_pmc_by_pmid(pmid)
            if pmc_id:
                return pmc_id
        
        # Try searching by title as last resort
        if publication.title:
            pmc_id = self.lookup_pmc_by_title(publication.title)
            if pmc_id:
                return pmc_id
        
        return None

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
                return self.lookup_pmc_by_pmid(pmid)
                
        except Exception as e:
            logger.warning(f"Error looking up PMC by DOI {doi}: {str(e)}")
        
        return None

    def lookup_pmc_by_pmid(self, pmid):
        """Lookup PMC ID using PMID via PubMed API"""
        try:
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

    def lookup_pmc_by_title(self, title):
        """Lookup PMC ID by searching for title"""
        try:
            self.stdout.write(f"    Searching by title: {title[:50]}...")
            
            # Clean title for search
            clean_title = title.replace('"', '').replace('[', '').replace(']', '')
            
            # Search PubMed for the title
            search_handle = Entrez.esearch(
                db='pubmed',
                term=f'"{clean_title}"[Title]',
                retmax=1
            )
            search_result = Entrez.read(search_handle)
            search_handle.close()
            
            if search_result['IdList']:
                pmid = search_result['IdList'][0]
                return self.lookup_pmc_by_pmid(pmid)
                
        except Exception as e:
            logger.warning(f"Error looking up PMC by title: {str(e)}")
        
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
            
            # Add to links if not present
            if not publication.links:
                publication.links = {}
            
            if 'pmc' not in publication.links:
                publication.links['pmc'] = f'https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/'
            
            # Mark as manually edited to preserve this information
            if not publication.manual_edits:
                publication.manual_edits = {}
            publication.manual_edits['identifiers'] = True
            
            publication.save()
            
        except Exception as e:
            logger.error(f"Error updating publication {publication.id}: {str(e)}")