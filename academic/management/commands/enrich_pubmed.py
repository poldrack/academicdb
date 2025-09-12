"""
Django management command to enrich publications using PubMed API
"""
import os
import sys
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db import models
from academic.models import Publication

User = get_user_model()

# Import existing PubMed utilities
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../src'))
from academicdb import pubmed

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Enrich publication metadata using PubMed API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            required=True,
            help='Email address for PubMed API access (required)'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Enrich publications for specific user by ID'
        )
        parser.add_argument(
            '--search-query',
            type=str,
            help='Search PubMed for publications matching query'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be enriched without making changes'
        )
        parser.add_argument(
            '--max-results',
            type=int,
            default=1000,
            help='Maximum number of results to fetch from PubMed'
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.email = options['email']
        self.max_results = options['max_results']
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        if options['search_query']:
            # Search PubMed and create new publications
            self.search_and_create_publications(options)
        else:
            # Enrich existing publications with PubMed data
            self.enrich_existing_publications(options)

    def search_and_create_publications(self, options):
        """Search PubMed and create new publications"""
        query = options['search_query']
        user_id = options['user_id']
        
        if not user_id:
            raise CommandError('User ID is required when searching PubMed')
            
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise CommandError(f'User with ID {user_id} not found')

        self.stdout.write(f'Searching PubMed for: {query}')
        
        # Get PubMed data
        pubmed_records = pubmed.get_pubmed_data(
            query, 
            self.email, 
            retmax=self.max_results
        )
        
        if not pubmed_records:
            self.stdout.write('No PubMed records found')
            return

        # Parse publications
        publications = pubmed.parse_pubmed_pubs(pubmed_records)
        
        self.stdout.write(f'Found {len(publications)} publications')
        
        created_count = 0
        skipped_count = 0
        
        for doi, pub_data in publications.items():
            if not doi:
                skipped_count += 1
                continue
                
            # Check if publication already exists
            if Publication.objects.filter(owner=user, doi=doi).exists():
                self.stdout.write(f'  Skipping existing publication: {doi}')
                skipped_count += 1
                continue
                
            if self.dry_run:
                self.stdout.write(f'  Would create publication: {pub_data.get("title", "No title")}')
                created_count += 1
                continue
                
            # Create publication
            if self.create_publication_from_pubmed(user, pub_data):
                created_count += 1
            else:
                skipped_count += 1
                
        self.stdout.write(
            self.style.SUCCESS(
                f'Created {created_count} publications, skipped {skipped_count}'
            )
        )

    def enrich_existing_publications(self, options):
        """Enrich existing publications with PubMed data"""
        # Get publications that could benefit from PubMed enrichment
        queryset = Publication.objects.exclude(
            models.Q(doi__isnull=True) | models.Q(doi='')
        )
        
        if options['user_id']:
            try:
                user = User.objects.get(id=options['user_id'])
                queryset = queryset.filter(owner=user)
            except User.DoesNotExist:
                raise CommandError(f'User with ID {options["user_id"]} not found')
        
        # Filter to publications that might benefit from PubMed data
        queryset = queryset.filter(
            models.Q(metadata__pmid__isnull=True) |
            models.Q(metadata__pmcid__isnull=True) |
            models.Q(metadata__pubmed_enriched__isnull=True)
        )
        
        publications = list(queryset.select_related('owner'))
        
        if not publications:
            self.stdout.write(self.style.WARNING('No publications found to enrich'))
            return
            
        self.stdout.write(f'Found {len(publications)} publications to enrich')
        
        enriched_count = 0
        
        for publication in publications:
            if self.enrich_publication_with_pubmed(publication):
                enriched_count += 1
                
        self.stdout.write(
            self.style.SUCCESS(
                f'Enriched {enriched_count} publications with PubMed data'
            )
        )

    def create_publication_from_pubmed(self, user, pubmed_data):
        """Create a new publication from PubMed data"""
        try:
            # Convert PubMed authors string to list
            authors_list = self.parse_authors_string(pubmed_data.get('authors', ''))
            
            # Create publication
            publication = Publication(
                owner=user,
                doi=pubmed_data['DOI'],
                title=pubmed_data.get('title', 'Untitled'),
                year=pubmed_data.get('year'),
                publication_type='journal-article',
                publication_name=pubmed_data.get('journal'),
                authors=authors_list,
                source='pubmed',
                metadata={
                    'pmid': pubmed_data.get('PMID'),
                    'pmcid': pubmed_data.get('PMC'),
                    'abstract': pubmed_data.get('abstract'),
                    'volume': pubmed_data.get('volume'),
                    'pages': pubmed_data.get('page'),
                    'publication_date': pubmed_data.get('publication-date'),
                    'pubmed_enriched': True
                }
            )
            
            publication.save()
            
            self.stdout.write(f'  Created: {publication.title[:60]}...')
            return True
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'  Error creating publication from PubMed data: {str(e)}'
                )
            )
            logger.exception('Error creating publication from PubMed')
            return False

    def enrich_publication_with_pubmed(self, publication):
        """Enrich existing publication with PubMed data"""
        if not publication.doi:
            return False
            
        try:
            # Search PubMed by DOI
            query = f'{publication.doi}[DOI]'
            pubmed_records = pubmed.get_pubmed_data(
                query, 
                self.email, 
                retmax=1
            )
            
            if not pubmed_records or not pubmed_records['PubmedArticle']:
                return False
                
            # Parse first record
            record = pubmed_records['PubmedArticle'][0]
            parsed_record = pubmed.parse_pubmed_record(record)
            
            if self.dry_run:
                self.stdout.write(f'  Would enrich: {publication.title[:60]}...')
                return True
                
            # Update publication metadata with PubMed data
            metadata = publication.metadata or {}
            metadata.update({
                'pmid': parsed_record.get('PMID'),
                'pmcid': parsed_record.get('PMC'),
                'abstract': parsed_record.get('abstract'),
                'pubmed_volume': parsed_record.get('volume'),
                'pubmed_pages': parsed_record.get('page'),
                'pubmed_journal': parsed_record.get('journal'),
                'pubmed_enriched': True
            })
            
            publication.metadata = metadata
            publication.save(update_fields=['metadata'])
            
            self.stdout.write(f'  Enriched: {publication.title[:60]}...')
            return True
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'  Error enriching {publication.doi}: {str(e)}'
                )
            )
            logger.exception(f'Error enriching publication {publication.id}')
            return False

    def parse_authors_string(self, authors_string):
        """Convert PubMed authors string to list format"""
        if not authors_string:
            return []
            
        # PubMed format is usually "LastName Initials, LastName Initials"
        author_names = [name.strip() for name in authors_string.split(',')]
        authors_list = []
        
        for name in author_names:
            if name:
                # Split into parts (LastName Initials)
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