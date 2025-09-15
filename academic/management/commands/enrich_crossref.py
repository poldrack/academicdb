"""
Django management command to enrich publications using CrossRef API
"""
import os
import sys
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db import models
from academic.models import Publication, APIRecordCache

User = get_user_model()

# Import existing CrossRef utilities
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../src'))
from academicdb import crossref_utils

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Enrich publication metadata using CrossRef API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Enrich publications for specific user by ID'
        )
        parser.add_argument(
            '--publication-id',
            type=int,
            help='Enrich specific publication by ID'
        )
        parser.add_argument(
            '--doi',
            type=str,
            help='Enrich publication with specific DOI'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be enriched without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force enrichment even if already enriched'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of publications to process in one batch'
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.force = options['force']
        self.batch_size = options['batch_size']
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Get publications to enrich
        publications = self.get_publications_to_enrich(options)
        
        if not publications:
            self.stdout.write(self.style.WARNING('No publications found to enrich'))
            return

        self.stdout.write(f'Found {len(publications)} publications to enrich')

        # Process in batches
        enriched_count = 0
        for i in range(0, len(publications), self.batch_size):
            batch = publications[i:i + self.batch_size]
            batch_dois = [pub.doi for pub in batch if pub.doi]
            
            if not batch_dois:
                continue
                
            self.stdout.write(f'Processing batch {i//self.batch_size + 1}: {len(batch_dois)} DOIs')
            
            # Fetch CrossRef records for batch
            crossref_records = self.fetch_crossref_records(batch_dois)
            
            # Update publications with enriched data
            for pub in batch:
                if pub.doi and pub.doi in crossref_records:
                    if self.enrich_publication(pub, crossref_records[pub.doi]):
                        enriched_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully enriched {enriched_count} publications'
            )
        )

    def get_publications_to_enrich(self, options):
        """Get publications that need enrichment"""
        queryset = Publication.objects.all()

        if options['user_id']:
            try:
                user = User.objects.get(id=options['user_id'])
                queryset = queryset.filter(owner=user)
            except User.DoesNotExist:
                raise CommandError(f'User with ID {options["user_id"]} not found')
        
        elif options['publication_id']:
            try:
                pub = Publication.objects.get(id=options['publication_id'])
                return [pub]
            except Publication.DoesNotExist:
                raise CommandError(f'Publication with ID {options["publication_id"]} not found')
        
        elif options['doi']:
            try:
                pub = Publication.objects.get(doi=options['doi'])
                return [pub]
            except Publication.DoesNotExist:
                raise CommandError(f'Publication with DOI {options["doi"]} not found')

        # Filter to publications that need enrichment
        if not self.force:
            # Count how many are already enriched for logging
            total_with_dois = queryset.exclude(doi__isnull=True).exclude(doi='').count()
            already_enriched = queryset.filter(metadata__crossref_enriched=True).count()

            # Exclude publications that have already been enriched with CrossRef
            queryset = queryset.exclude(
                metadata__crossref_enriched=True
            )

            if already_enriched > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Skipping {already_enriched} publications already enriched with CrossRef data'
                    )
                )

        # Only enrich publications with DOIs
        queryset = queryset.exclude(doi__isnull=True).exclude(doi='')

        return list(queryset.select_related('owner'))

    def fetch_crossref_records(self, dois):
        """Fetch CrossRef records for multiple DOIs with intelligent caching"""
        self.stdout.write(f'  Fetching CrossRef data for {len(dois)} DOIs...')

        crossref_records = {}
        uncached_dois = []
        cache_hits = 0

        # First, check cache for each DOI
        for doi in dois:
            cached_record = APIRecordCache.get_cached_record('crossref', doi=doi)
            if cached_record and cached_record.raw_data:
                crossref_records[doi] = cached_record.raw_data
                cache_hits += 1
            else:
                uncached_dois.append(doi)

        if cache_hits > 0:
            self.stdout.write(f'  Found {cache_hits} records in cache')

        # Fetch uncached DOIs from API
        if uncached_dois:
            self.stdout.write(f'  Fetching {len(uncached_dois)} DOIs from CrossRef API...')
            try:
                api_records = crossref_utils.get_crossref_records(uncached_dois)

                # Cache the new records and add to results
                for doi, record in api_records.items():
                    # Cache the record for future use
                    APIRecordCache.cache_record(
                        api_source='crossref',
                        api_id=doi,
                        raw_data=record,
                        doi=doi
                    )
                    crossref_records[doi] = record

                self.stdout.write(f'  Retrieved and cached {len(api_records)} new CrossRef records')

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Error fetching CrossRef records from API: {str(e)}'
                    )
                )
                logger.exception('Error fetching CrossRef records from API')

        total_retrieved = len(crossref_records)
        self.stdout.write(f'  Total records available: {total_retrieved} ({cache_hits} from cache, {total_retrieved - cache_hits} from API)')

        return crossref_records

    def enrich_publication(self, publication, crossref_record):
        """Enrich a single publication with CrossRef data"""
        try:
            # Parse CrossRef record using existing utility
            parsed_record = crossref_utils.parse_crossref_record(
                crossref_record,
                verbose=False
            )
            
            if not parsed_record:
                self.stdout.write(f'  Skipped {publication.doi} - parsing failed')
                return False

            if self.dry_run:
                self.stdout.write(f'  Would enrich: {publication.doi}')
                return True

            # Update publication with CrossRef data while preserving manual edits
            updated = self.update_publication_fields(publication, parsed_record)
            
            if updated:
                # Mark as enriched and update metadata
                from django.utils import timezone
                publication.metadata = publication.metadata or {}
                publication.metadata['crossref_enriched'] = True
                publication.metadata['crossref_enriched_at'] = timezone.now().isoformat()
                publication.metadata['needs_enrichment'] = False
                publication.metadata['crossref_source'] = 'CrossRef API'

                publication.save()
                self.stdout.write(f'  Enriched: {publication.title[:60]}...')
                return True
            else:
                self.stdout.write(f'  No updates needed: {publication.doi}')
                return False
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'  Error enriching {publication.doi}: {str(e)}'
                )
            )
            logger.exception(f'Error enriching publication {publication.id}')
            return False

    def update_publication_fields(self, publication, crossref_data):
        """Update publication fields with CrossRef data, respecting manual edits"""
        updated = False
        
        # Check manual edits to avoid overwriting user changes
        manual_edits = publication.manual_edits or {}
        
        # Field mappings from CrossRef to our model
        field_mappings = {
            'title': 'title',
            'year': 'year',
            'journal': 'publication_name',
            'type': 'publication_type',
            'volume': 'volume',
            'page': 'pages',
            'publication-date': 'publication_date',
            'authors': 'authors_string',  # We'll convert this to authors list
        }
        
        for crossref_field, model_field in field_mappings.items():
            if crossref_field in crossref_data:
                # Don't update if user manually edited this field
                if manual_edits.get(model_field):
                    continue
                    
                value = crossref_data[crossref_field]
                
                # Special handling for different fields
                if model_field == 'authors_string':
                    # Convert author string to list format
                    if value and value != getattr(publication, 'authors', None):
                        authors_list = self.parse_authors_string(value)
                        publication.authors = authors_list
                        updated = True
                        
                elif model_field == 'publication_type':
                    # Map CrossRef type to our choices
                    mapped_type = self.map_publication_type(value)
                    if mapped_type != publication.publication_type:
                        publication.publication_type = mapped_type
                        updated = True
                        
                else:
                    # Direct field mapping
                    if hasattr(publication, model_field):
                        current_value = getattr(publication, model_field)
                        if value != current_value:
                            setattr(publication, model_field, value)
                            updated = True

        return updated

    def parse_authors_string(self, authors_string):
        """Convert CrossRef authors string to list format"""
        if not authors_string:
            return []
            
        # Split by comma and create author objects
        author_names = [name.strip() for name in authors_string.split(',')]
        authors_list = []
        
        for name in author_names:
            if name:
                # Try to split into last name and initials
                parts = name.strip().split(' ')
                if len(parts) >= 2:
                    last_name = parts[0]
                    initials = ' '.join(parts[1:])
                    authors_list.append({
                        'name': f'{initials} {last_name}',
                        'last_name': last_name,
                        'initials': initials
                    })
                else:
                    authors_list.append({'name': name})
                    
        return authors_list

    def map_publication_type(self, crossref_type):
        """Map CrossRef publication type to our model choices"""
        type_mapping = {
            'journal-article': 'journal-article',
            'proceedings-article': 'conference-paper',
            'book-chapter': 'book-chapter',
            'book': 'book',
            'posted-content': 'preprint',
        }
        return type_mapping.get(crossref_type, 'journal-article')