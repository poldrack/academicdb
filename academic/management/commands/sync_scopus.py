"""
Django management command to sync publications from Scopus
"""
import logging
import os
import re
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth import get_user_model
from pybliometrics.scopus import AuthorRetrieval, ScopusSearch
import pybliometrics
import requests

from academic.models import Publication, APIRecordCache
from academic.utils import init_pybliometrics

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Sync publications from Scopus for a specific user'

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

    def handle(self, *args, **options):
        # Initialize Scopus
        try:
            init_pybliometrics()
        except Exception as e:
            raise CommandError(f"Failed to initialize Scopus: {str(e)}")

        user_id = options.get('user_id')
        scopus_id = options.get('scopus_id')
        max_results = options.get('max_results')

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

        self.stdout.write(f"Starting Scopus sync for user: {user.username}")
        self.stdout.write(f"Using Scopus ID: {scopus_id}")

        try:
            # Get publications from Scopus
            publications_data = self.fetch_scopus_publications(scopus_id, max_results)
            
            if not publications_data:
                self.stdout.write(self.style.WARNING("No publications found in Scopus"))
                return

            # Import publications
            created_count, updated_count, error_count = self.import_publications(
                user, publications_data
            )

            # Update user's last sync time
            user.last_orcid_sync = timezone.now()  # Using same field for simplicity
            user.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Scopus sync completed successfully!\n"
                    f"Created: {created_count} publications\n"
                    f"Updated: {updated_count} publications\n"
                    f"Errors: {error_count} publications"
                )
            )

        except Exception as e:
            logger.error(f"Scopus sync failed for user {user_id}: {str(e)}")
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

    def import_publications(self, user, publications_data):
        """Import publications into the database"""
        created_count = 0
        updated_count = 0
        error_count = 0

        for pub_data in publications_data:
            try:
                # Extract basic publication info
                doi = pub_data.doi if hasattr(pub_data, 'doi') and pub_data.doi else None
                if doi:
                    doi = doi.lower().strip()  # Normalize DOI to lowercase
                    # Replace repeated slashes with single slash
                    doi = re.sub(r'/+', '/', doi)

                    # Check if DOI should be skipped based on user preferences
                    skip_dois = user.get_skip_dois_list()
                    if doi in skip_dois:
                        self.stdout.write(f"Skipping DOI (in user skip list): {doi}")
                        continue

                eid = pub_data.eid if hasattr(pub_data, 'eid') else None

                # Cache the raw Scopus data for future use
                scopus_id = eid if eid else doi  # Use EID as primary Scopus identifier, fallback to DOI
                if scopus_id:
                    try:
                        # Convert pub_data to dictionary for caching
                        pub_dict = {}
                        for attr in dir(pub_data):
                            if not attr.startswith('_') and hasattr(pub_data, attr):
                                value = getattr(pub_data, attr)
                                if not callable(value):
                                    pub_dict[attr] = value

                        APIRecordCache.cache_record(
                            api_source='scopus',
                            api_id=scopus_id,
                            raw_data=pub_dict,
                            doi=doi,
                            scopus_id=eid
                        )
                        self.stdout.write(f"    Cached Scopus data for: {scopus_id}")
                    except Exception as e:
                        logger.warning(f"Failed to cache Scopus data for {scopus_id}: {str(e)}")

                if not doi and not eid:
                    self.stdout.write(
                        self.style.WARNING(f"Skipping publication without DOI or EID: {pub_data.title}")
                    )
                    error_count += 1
                    continue

                # Skip if title contains skip strings (replicating original logic)
                if self.has_skip_strings(pub_data.title):
                    self.stdout.write(f"Skipping publication with skip strings: {pub_data.title}")
                    error_count += 1
                    continue

                # Use DOI if available, otherwise use EID as identifier
                identifier = doi if doi else eid

                # Extract publication year
                year = None
                if hasattr(pub_data, 'coverDate') and pub_data.coverDate:
                    try:
                        year = int(pub_data.coverDate.split('-')[0])
                    except (ValueError, IndexError):
                        pass
                
                if not year:
                    year = datetime.now().year
                    self.stdout.write(f"Using current year for publication: {pub_data.title}")

                # Extract authors and their IDs
                authors = []
                author_ids = []
                affiliation_ids = []
                
                if hasattr(pub_data, 'author_ids') and pub_data.author_ids:
                    author_ids = pub_data.author_ids.split(';')
                    
                if hasattr(pub_data, 'author_afids') and pub_data.author_afids:
                    affiliation_ids = pub_data.author_afids.split(';')

                # Process authors (use author_names field from Scopus)
                if hasattr(pub_data, 'author_names') and pub_data.author_names:
                    for i, author in enumerate(pub_data.author_names.split(';')):
                        author_dict = {'name': author.strip()}
                        
                        # Add Scopus ID if available
                        if i < len(author_ids) and author_ids[i]:
                            author_dict['scopus_id'] = author_ids[i].strip()
                            
                        # Add affiliation ID if available
                        if i < len(affiliation_ids) and affiliation_ids[i]:
                            author_dict['affiliation_id'] = affiliation_ids[i].strip()
                            
                        authors.append(author_dict)
                
                # Debug output to verify authors are being processed
                if authors:
                    self.stdout.write(f"  Found {len(authors)} authors: {[a['name'] for a in authors[:3]]}...")
                else:
                    self.stdout.write(f"  Warning: No authors found for {pub_data.title}")
                    # Fallback: create a placeholder if no authors found
                    authors = [{'name': 'Unknown Author'}]

                # Build metadata
                metadata = {
                    'scopus_eid': eid,
                    'source': 'scopus',
                    'raw_data': {
                        'title': pub_data.title,
                        'publicationName': getattr(pub_data, 'publicationName', None),
                        'volume': getattr(pub_data, 'volume', None),
                        'pageRange': getattr(pub_data, 'pageRange', None),
                        'coverDate': getattr(pub_data, 'coverDate', None),
                        'citedby_count': getattr(pub_data, 'citedby_count', None),
                        'author_count': getattr(pub_data, 'author_count', None),
                        'aggregationType': getattr(pub_data, 'aggregationType', None),
                        'subtypeDescription': getattr(pub_data, 'subtypeDescription', None),
                    }
                }

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

                # Extract volume and page range for first-class fields
                volume = getattr(pub_data, 'volume', None)
                page_range = getattr(pub_data, 'pageRange', None)

                # Check if publication exists (including versioned variants)
                existing_pub = None
                if doi:
                    # First try exact match
                    existing_pub = Publication.objects.filter(owner=user, doi=doi).first()

                    # If not found, check for versioned variants
                    if not existing_pub:
                        potential_duplicates = Publication.find_potential_duplicates_by_doi(doi, user)
                        if potential_duplicates.exists():
                            # Get the latest version (highest version number)
                            latest_pub = None
                            latest_version = -1

                            for pub in potential_duplicates:
                                _, version = Publication.normalize_doi_for_deduplication(pub.doi)
                                if version is None:
                                    version = 0  # Treat unversioned as v0

                                if version > latest_version:
                                    latest_version = version
                                    latest_pub = pub

                            if latest_pub:
                                # Check if the new DOI has a higher version
                                _, new_version = Publication.normalize_doi_for_deduplication(doi)
                                if new_version is None:
                                    new_version = 0

                                if new_version > latest_version:
                                    # New DOI is newer, update the existing publication
                                    existing_pub = latest_pub
                                    self.stdout.write(f"Updating DOI from {existing_pub.doi} to {doi} (newer version)")
                                    existing_pub.doi = doi
                                else:
                                    # Existing version is newer or same, skip this import
                                    self.stdout.write(f"Skipping {doi} - newer version {latest_pub.doi} already exists")
                                    continue

                if not existing_pub and eid:
                    existing_pub = Publication.objects.filter(
                        owner=user,
                        identifiers__scopus_eid=eid
                    ).first()

                if existing_pub:
                    # Update existing publication with new Scopus data
                    api_data = {
                        'metadata': metadata,
                        'authors': authors,
                        'identifiers': identifiers,
                        'publication_name': getattr(pub_data, 'publicationName', existing_pub.publication_name),
                        'publication_type': pub_type,
                    }
                    # Only update volume/page_range if not manually edited and new data is available
                    if volume and not existing_pub.manual_edits.get('volume', False):
                        api_data['volume'] = volume
                    if page_range and not existing_pub.manual_edits.get('page_range', False):
                        api_data['page_range'] = page_range

                    existing_pub.save_with_edit_protection(api_data=api_data)
                    updated_count += 1
                    self.stdout.write(f"Updated: {pub_data.title}")
                else:
                    # Create new publication
                    new_pub = Publication(
                        owner=user,
                        doi=doi,
                        title=pub_data.title,
                        year=year,
                        publication_name=getattr(pub_data, 'publicationName', ''),
                        publication_type=pub_type,
                        volume=volume,
                        page_range=page_range,
                        source='scopus',
                        metadata=metadata,
                        authors=authors,
                        identifiers=identifiers,
                        last_api_sync=timezone.now()
                    )
                    new_pub.save()
                    created_count += 1
                    self.stdout.write(f"Created: {pub_data.title}")

            except Exception as e:
                logger.error(f"Error processing publication: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f"Error processing publication: {str(e)}")
                )
                error_count += 1
                continue

        return created_count, updated_count, error_count

    def has_skip_strings(self, title):
        """Check if title contains strings that should be skipped (from original code)"""
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
            return 'book'
        elif 'patent' in agg_lower:
            return 'patent'
        elif 'report' in agg_lower:
            return 'report'
        else:
            return 'journal-article'  # Default