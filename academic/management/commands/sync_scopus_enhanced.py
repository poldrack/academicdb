"""
Enhanced Django management command to sync publications from Scopus with full author details
"""
import logging
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth import get_user_model
from pybliometrics.scopus import AuthorRetrieval, AbstractRetrieval
import pybliometrics
import time

from academic.models import Publication, AuthorCache

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Enhanced Scopus sync that properly captures author Scopus IDs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to sync Scopus data for'
        )
        parser.add_argument(
            '--scopus-id',
            type=str,
            help='Scopus Author ID to use for sync (overrides user profile)'
        )
        parser.add_argument(
            '--max-results',
            type=int,
            default=None,
            help='Maximum number of publications to fetch'
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing publications with missing author IDs'
        )
        parser.add_argument(
            '--rate-limit',
            type=float,
            default=1.0,
            help='Seconds to wait between API calls (default: 1.0)'
        )

    def handle(self, *args, **options):
        # Initialize Scopus
        try:
            pybliometrics.scopus.init()
        except Exception as e:
            raise CommandError(f"Failed to initialize Scopus: {str(e)}")

        user_id = options.get('user_id')
        scopus_id = options.get('scopus_id')
        max_results = options.get('max_results')
        update_existing = options.get('update_existing')
        rate_limit = options.get('rate_limit', 1.0)

        if not user_id:
            raise CommandError("User ID is required (--user-id)")

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise CommandError(f"User with ID {user_id} not found")

        # Use provided Scopus ID or get from user profile
        if not scopus_id:
            scopus_id = user.scopus_id

        if not scopus_id:
            raise CommandError(f"No Scopus ID found for user {user.username}. Please provide --scopus-id or set in profile.")

        self.stdout.write(f"Starting enhanced Scopus sync for user: {user.username}")
        self.stdout.write(f"Using Scopus ID: {scopus_id}")

        try:
            # Get publications from Scopus
            publications_data = self.fetch_scopus_publications(scopus_id, max_results)
            
            if not publications_data:
                self.stdout.write(self.style.WARNING("No publications found in Scopus"))
                return

            # Import publications with enhanced author data
            created_count, updated_count, enhanced_count, error_count = self.import_publications_enhanced(
                user, publications_data, update_existing, rate_limit
            )

            # Update user's last sync time
            user.last_orcid_sync = timezone.now()  # Using same field for simplicity
            user.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Enhanced Scopus sync completed successfully!\n"
                    f"Created: {created_count} publications\n"
                    f"Updated: {updated_count} publications\n"
                    f"Enhanced with author IDs: {enhanced_count} publications\n"
                    f"Errors: {error_count} publications"
                )
            )

        except Exception as e:
            logger.error(f"Enhanced Scopus sync failed for user {user_id}: {str(e)}")
            raise CommandError(f"Sync failed: {str(e)}")

    def fetch_scopus_publications(self, scopus_id, max_results=None):
        """Fetch publications from Scopus for the given author ID"""
        try:
            self.stdout.write(f"Fetching publications for Scopus ID: {scopus_id}")
            
            # Get author and publications
            author = AuthorRetrieval(scopus_id)
            publications = author.get_documents(view='COMPLETE')
            
            if max_results:
                publications = publications[:max_results]
            
            self.stdout.write(f"Found {len(publications)} publications in Scopus")
            return publications
            
        except Exception as e:
            logger.error(f"Error fetching Scopus data: {str(e)}")
            raise

    def fetch_publication_details(self, eid):
        """Fetch detailed publication information including author Scopus IDs"""
        try:
            # Use AbstractRetrieval to get full publication details
            abstract = AbstractRetrieval(eid, view='FULL')
            
            # Extract authors with their Scopus IDs
            authors = []
            if abstract.authors:
                for author in abstract.authors:
                    author_dict = {
                        'name': author.indexed_name or f"{author.given_name} {author.surname}",
                        'scopus_id': author.auid,  # This is the Scopus author ID
                    }
                    
                    # Add additional fields if available
                    if author.given_name:
                        author_dict['given_name'] = author.given_name
                    if author.surname:
                        author_dict['surname'] = author.surname
                    if hasattr(author, 'affiliation') and author.affiliation:
                        author_dict['affiliation'] = author.affiliation
                        
                    authors.append(author_dict)
                    
                    # Cache this author for future lookups
                    affiliations = []
                    if hasattr(author, 'affiliation') and author.affiliation:
                        affiliations = [author.affiliation]
                    
                    AuthorCache.cache_author(
                        name=author_dict['name'],
                        scopus_id=author.auid,
                        given_name=author.given_name,
                        surname=author.surname,
                        affiliations=affiliations,
                        source='scopus',
                        confidence_score=1.0
                    )
            
            return {
                'authors': authors,
                'title': abstract.title,
                'doi': abstract.doi,
                'eid': abstract.eid,
                'abstract': abstract.abstract,
                'keywords': abstract.authkeywords,
                'publication_name': abstract.publicationName,
                'volume': abstract.volume,
                'page_range': abstract.pageRange,
                'cover_date': abstract.coverDate,
                'cited_by_count': abstract.citedby_count,
            }
            
        except Exception as e:
            logger.warning(f"Error fetching details for EID {eid}: {str(e)}")
            return None

    def import_publications_enhanced(self, user, publications_data, update_existing, rate_limit):
        """Import publications with enhanced author data"""
        created_count = 0
        updated_count = 0
        enhanced_count = 0
        error_count = 0

        for i, pub_data in enumerate(publications_data):
            try:
                # Extract basic publication info
                doi = pub_data.doi if hasattr(pub_data, 'doi') and pub_data.doi else None
                eid = pub_data.eid if hasattr(pub_data, 'eid') else None
                
                if not doi and not eid:
                    self.stdout.write(
                        self.style.WARNING(f"Skipping publication without DOI or EID: {pub_data.title}")
                    )
                    error_count += 1
                    continue

                # Skip if title contains skip strings
                if self.has_skip_strings(pub_data.title):
                    self.stdout.write(f"Skipping publication with skip strings: {pub_data.title}")
                    error_count += 1
                    continue

                self.stdout.write(f"\n[{i+1}/{len(publications_data)}] Processing: {pub_data.title[:80]}...")
                
                # Fetch detailed publication data with author IDs
                detailed_data = self.fetch_publication_details(eid)
                time.sleep(rate_limit)  # Rate limiting
                
                if not detailed_data:
                    self.stdout.write(f"  Warning: Could not fetch detailed data, using basic info")
                    # Fall back to basic data
                    authors = self.extract_basic_authors(pub_data)
                else:
                    authors = detailed_data['authors']
                    enhanced_count += 1
                    self.stdout.write(f"  ✓ Found {len(authors)} authors with Scopus IDs")

                # Extract publication year
                year = None
                if hasattr(pub_data, 'coverDate') and pub_data.coverDate:
                    try:
                        year = int(pub_data.coverDate.split('-')[0])
                    except (ValueError, IndexError):
                        pass
                
                if not year:
                    year = datetime.now().year

                # Build metadata
                metadata = {
                    'scopus_eid': eid,
                    'source': 'scopus',
                    'enhanced': detailed_data is not None,
                    'raw_data': {
                        'title': pub_data.title,
                        'publicationName': getattr(pub_data, 'publicationName', None),
                        'volume': getattr(pub_data, 'volume', None),
                        'pageRange': getattr(pub_data, 'pageRange', None),
                        'coverDate': getattr(pub_data, 'coverDate', None),
                        'citedby_count': getattr(pub_data, 'citedby_count', None),
                    }
                }
                
                if detailed_data:
                    metadata['abstract'] = detailed_data.get('abstract')
                    metadata['keywords'] = detailed_data.get('keywords')

                # Build identifiers
                identifiers = {}
                if eid:
                    identifiers['scopus_eid'] = eid
                if hasattr(pub_data, 'pubmed_id') and pub_data.pubmed_id:
                    identifiers['pmid'] = pub_data.pubmed_id

                # Map publication type
                pub_type = self.map_publication_type(
                    getattr(pub_data, 'aggregationType', ''),
                    getattr(pub_data, 'subtypeDescription', '')
                )

                # Check if publication exists
                existing_pub = None
                if doi:
                    existing_pub = Publication.objects.filter(owner=user, doi=doi).first()
                
                if not existing_pub and eid:
                    existing_pub = Publication.objects.filter(
                        owner=user, 
                        identifiers__scopus_eid=eid
                    ).first()

                if existing_pub:
                    # Update existing publication
                    if update_existing or not existing_pub.authors or len(existing_pub.authors) == 0:
                        api_data = {
                            'metadata': metadata,
                            'authors': authors,
                            'identifiers': identifiers,
                            'publication_name': getattr(pub_data, 'publicationName', existing_pub.publication_name),
                            'publication_type': pub_type,
                        }
                        existing_pub.save_with_edit_protection(api_data=api_data)
                        updated_count += 1
                        self.stdout.write(f"  Updated: {pub_data.title[:60]}")
                    else:
                        self.stdout.write(f"  Skipped (already exists): {pub_data.title[:60]}")
                else:
                    # Create new publication
                    new_pub = Publication(
                        owner=user,
                        doi=doi,
                        title=pub_data.title,
                        year=year,
                        publication_name=getattr(pub_data, 'publicationName', ''),
                        publication_type=pub_type,
                        source='scopus',
                        metadata=metadata,
                        authors=authors,
                        identifiers=identifiers,
                        last_api_sync=timezone.now()
                    )
                    new_pub.save()
                    created_count += 1
                    self.stdout.write(f"  Created: {pub_data.title[:60]}")

            except Exception as e:
                logger.error(f"Error processing publication: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f"  Error processing publication: {str(e)}")
                )
                error_count += 1
                continue

        return created_count, updated_count, enhanced_count, error_count

    def extract_basic_authors(self, pub_data):
        """Extract authors from basic publication data (fallback)"""
        authors = []
        author_ids = []
        
        if hasattr(pub_data, 'author_ids') and pub_data.author_ids:
            author_ids = pub_data.author_ids.split(';')

        # Process authors
        if hasattr(pub_data, 'author_names') and pub_data.author_names:
            for i, author in enumerate(pub_data.author_names.split(';')):
                author_dict = {'name': author.strip()}
                
                # Add Scopus ID if available
                if i < len(author_ids) and author_ids[i]:
                    author_dict['scopus_id'] = author_ids[i].strip()
                    
                authors.append(author_dict)
        
        return authors if authors else [{'name': 'Unknown Author'}]

    def has_skip_strings(self, title):
        """Check if title contains strings that should be skipped"""
        if not title:
            return False
        
        skip_strings = [
            'correction',
            'erratum',
            'retraction',
            'editorial',
            'commentary',
        ]
        
        title_lower = title.lower()
        return any(skip_str in title_lower for skip_str in skip_strings)

    def map_publication_type(self, aggregation_type, subtype_description):
        """Map Scopus publication types to our choices"""
        if not aggregation_type:
            return 'journal-article'
        
        agg_lower = aggregation_type.lower()
        sub_lower = subtype_description.lower() if subtype_description else ''
        
        if 'journal' in agg_lower:
            return 'journal-article'
        elif 'conference' in agg_lower or 'proceeding' in agg_lower:
            return 'conference-paper'
        elif 'book' in agg_lower:
            if 'chapter' in sub_lower:
                return 'book-chapter'
            else:
                return 'book'
        else:
            return 'other'