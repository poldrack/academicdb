"""
Django management command to enrich existing publications with Scopus author IDs
Uses DOI-based lookups for more accurate results
"""
import logging
import time
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from pybliometrics.scopus import AbstractRetrieval, ScopusSearch
import pybliometrics
from crossref.restful import Works

from academic.models import Publication

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Enrich existing publications with Scopus author IDs using DOI/EID lookups'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to process publications for (optional - if not provided, processes all users)'
        )
        parser.add_argument(
            '--source',
            choices=['orcid', 'pubmed', 'scopus', 'all'],
            default='all',
            help='Only process publications from specific source'
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
            '--max-publications',
            type=int,
            default=None,
            help='Maximum number of publications to process'
        )
        parser.add_argument(
            '--only-missing',
            action='store_true',
            help='Only process publications with no Scopus IDs for any author'
        )

    def handle(self, *args, **options):
        # Initialize Scopus
        try:
            pybliometrics.scopus.init()
        except Exception as e:
            raise CommandError(f"Failed to initialize Scopus: {str(e)}")

        user_id = options.get('user_id')
        source_filter = options.get('source')
        dry_run = options.get('dry_run')
        rate_limit = options.get('rate_limit')
        max_publications = options.get('max_publications')
        only_missing = options.get('only_missing')

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

        # Apply source filter
        if source_filter != 'all':
            publications = publications.filter(source=source_filter)
            self.stdout.write(f"Filtering to source: {source_filter}")

        # Apply only_missing filter
        if only_missing:
            # This is a bit complex - we want publications where no author has a scopus_id
            publications_to_process = []
            for pub in publications:
                if not pub.authors:
                    continue
                has_scopus = False
                for author in pub.authors:
                    if isinstance(author, dict) and author.get('scopus_id'):
                        has_scopus = True
                        break
                if not has_scopus:
                    publications_to_process.append(pub)
            
            self.stdout.write(f"Found {len(publications_to_process)} publications with no Scopus IDs")
            publications = publications_to_process[:max_publications] if max_publications else publications_to_process
        else:
            if max_publications:
                publications = publications[:max_publications]

        if not publications:
            self.stdout.write(self.style.WARNING("No publications found to process"))
            return

        total_to_process = len(publications) if isinstance(publications, list) else publications.count()
        self.stdout.write(f"Processing {total_to_process} publications")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Process publications
        stats = {
            'processed': 0,
            'enriched': 0,
            'already_complete': 0,
            'no_doi_eid': 0,
            'not_found': 0,
            'errors': 0,
            'authors_added': 0
        }

        for i, pub in enumerate(publications):
            if i >= total_to_process:
                break
                
            self.stdout.write(f"\n[{i+1}/{total_to_process}] Processing: {pub.title[:80]}...")
            
            result = self.enrich_publication(pub, dry_run, rate_limit)
            stats[result['status']] += 1
            if 'authors_added' in result:
                stats['authors_added'] += result['authors_added']
            
            # Show progress message
            if result['status'] == 'enriched':
                self.stdout.write(f"  ✓ Enriched with {result['authors_added']} author IDs")
            elif result['status'] == 'already_complete':
                self.stdout.write(f"  ⚫ Already has Scopus IDs")
            elif result['status'] == 'no_doi_eid':
                self.stdout.write(f"  ⚠ No DOI or EID available")
            elif result['status'] == 'not_found':
                self.stdout.write(f"  ✗ Not found in Scopus")
            elif result['status'] == 'errors':
                self.stdout.write(f"  ✗ Error: {result.get('error', 'Unknown')}")
            
            stats['processed'] += 1

        # Print summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== ENRICHMENT SUMMARY ===\n"
                f"Processed: {stats['processed']}\n"
                f"Enriched: {stats['enriched']}\n"
                f"Already complete: {stats['already_complete']}\n"
                f"No DOI/EID: {stats['no_doi_eid']}\n"
                f"Not found in Scopus: {stats['not_found']}\n"
                f"Errors: {stats['errors']}\n"
                f"Total author IDs added: {stats['authors_added']}"
            )
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No actual changes were made"))

    def enrich_publication(self, publication, dry_run, rate_limit):
        """Enrich a single publication with Scopus author IDs"""
        
        # Check if already has Scopus IDs
        if self.has_complete_scopus_ids(publication):
            return {'status': 'already_complete'}
        
        # Try to find publication in Scopus
        scopus_data = None
        
        # Method 1: Use Scopus EID if available
        if publication.identifiers and publication.identifiers.get('scopus_eid'):
            eid = publication.identifiers['scopus_eid']
            scopus_data = self.fetch_by_eid(eid)
            time.sleep(rate_limit)
        
        # Method 2: Use DOI if available
        if not scopus_data and publication.doi:
            scopus_data = self.fetch_by_doi(publication.doi)
            time.sleep(rate_limit)
        
        # Method 3: Search by title if no identifiers
        if not scopus_data and not publication.doi and not (publication.identifiers and publication.identifiers.get('scopus_eid')):
            scopus_data = self.search_by_title(publication.title, publication.year)
            time.sleep(rate_limit)
        
        if not scopus_data:
            if not publication.doi and not (publication.identifiers and publication.identifiers.get('scopus_eid')):
                return {'status': 'no_doi_eid'}
            else:
                return {'status': 'not_found'}
        
        # Enrich authors with Scopus IDs
        try:
            enriched_authors, authors_added = self.merge_author_data(
                publication.authors or [],
                scopus_data['authors']
            )
            
            if authors_added > 0 and not dry_run:
                # Update publication
                publication.authors = enriched_authors
                
                # Update metadata to indicate enrichment
                if not publication.metadata:
                    publication.metadata = {}
                publication.metadata['scopus_enriched'] = True
                publication.metadata['scopus_enrichment_date'] = time.strftime('%Y-%m-%d')
                
                # Also update identifiers if we found new ones
                if scopus_data.get('eid') and not publication.identifiers.get('scopus_eid'):
                    publication.identifiers['scopus_eid'] = scopus_data['eid']
                
                publication.save()
                
            return {
                'status': 'enriched' if authors_added > 0 else 'already_complete',
                'authors_added': authors_added
            }
            
        except Exception as e:
            logger.error(f"Error enriching publication {publication.id}: {str(e)}")
            return {'status': 'errors', 'error': str(e)}

    def has_complete_scopus_ids(self, publication):
        """Check if publication already has Scopus IDs for most authors"""
        if not publication.authors:
            return False
        
        authors_with_scopus = 0
        total_authors = len(publication.authors)
        
        for author in publication.authors:
            if isinstance(author, dict) and author.get('scopus_id'):
                authors_with_scopus += 1
        
        # Consider complete if >80% of authors have Scopus IDs
        return (authors_with_scopus / total_authors) > 0.8 if total_authors > 0 else False

    def fetch_by_eid(self, eid):
        """Fetch publication details by Scopus EID"""
        try:
            abstract = AbstractRetrieval(eid, view='FULL')
            
            authors = []
            if abstract.authors:
                for author in abstract.authors:
                    authors.append({
                        'name': author.indexed_name or f"{author.given_name} {author.surname}",
                        'scopus_id': author.auid,
                        'given_name': author.given_name,
                        'surname': author.surname,
                    })
            
            return {
                'eid': abstract.eid,
                'doi': abstract.doi,
                'title': abstract.title,
                'authors': authors
            }
        except Exception as e:
            logger.warning(f"Error fetching EID {eid}: {str(e)}")
            return None

    def fetch_by_doi(self, doi):
        """Fetch publication details by DOI"""
        try:
            # Search for the DOI in Scopus
            search = ScopusSearch(f'DOI({doi})', subscriber=False)
            
            if search.results and len(search.results) > 0:
                # Get the EID from search results
                eid = search.results[0].eid
                # Fetch full details
                return self.fetch_by_eid(eid)
            
            return None
            
        except Exception as e:
            logger.warning(f"Error fetching DOI {doi}: {str(e)}")
            return None

    def search_by_title(self, title, year):
        """Search for publication by title and year"""
        try:
            # Clean title for search
            clean_title = title.replace('"', '').replace("'", "")[:200]
            
            # Search query
            query = f'TITLE("{clean_title}") AND PUBYEAR = {year}'
            search = ScopusSearch(query, subscriber=False)
            
            if search.results and len(search.results) > 0:
                # Get the first result's EID
                eid = search.results[0].eid
                # Fetch full details
                return self.fetch_by_eid(eid)
            
            return None
            
        except Exception as e:
            logger.warning(f"Error searching for title: {str(e)}")
            return None

    def merge_author_data(self, existing_authors, scopus_authors):
        """Merge Scopus author data with existing authors"""
        enriched_authors = []
        authors_added = 0
        
        # Create a mapping of normalized names for matching
        def normalize_name(name):
            """Normalize author name for matching"""
            if not name:
                return ""
            # Remove extra spaces, convert to lowercase
            name = ' '.join(name.split()).lower()
            # Remove punctuation
            name = name.replace(',', '').replace('.', '').replace('-', ' ')
            return name
        
        # Build Scopus author lookup
        scopus_lookup = {}
        for s_author in scopus_authors:
            normalized = normalize_name(s_author['name'])
            scopus_lookup[normalized] = s_author
        
        # Process existing authors
        for e_author in existing_authors:
            if not isinstance(e_author, dict):
                enriched_authors.append(e_author)
                continue
            
            # Copy existing author data
            enriched = e_author.copy()
            
            # If no Scopus ID, try to find match
            if not enriched.get('scopus_id'):
                normalized = normalize_name(e_author.get('name', ''))
                
                if normalized in scopus_lookup:
                    # Found a match!
                    scopus_match = scopus_lookup[normalized]
                    enriched['scopus_id'] = scopus_match['scopus_id']
                    if scopus_match.get('given_name'):
                        enriched['given_name'] = scopus_match['given_name']
                    if scopus_match.get('surname'):
                        enriched['surname'] = scopus_match['surname']
                    authors_added += 1
            
            enriched_authors.append(enriched)
        
        # If we have more Scopus authors than existing, they might be missing
        if len(scopus_authors) > len(existing_authors):
            # Add any Scopus authors not already in the list
            existing_normalized = set(normalize_name(a.get('name', '')) 
                                    for a in existing_authors 
                                    if isinstance(a, dict))
            
            for s_author in scopus_authors:
                if normalize_name(s_author['name']) not in existing_normalized:
                    enriched_authors.append(s_author)
                    authors_added += 1
        
        return enriched_authors, authors_added