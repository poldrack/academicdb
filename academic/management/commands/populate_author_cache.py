"""
Django management command to populate the author cache with existing publication data
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from academic.models import Publication, AuthorCache

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate author cache with existing publication data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to populate cache for (optional - if not provided, processes all users)'
        )
        parser.add_argument(
            '--clear-cache',
            action='store_true',
            help='Clear existing cache before populating'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cached without making changes'
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        clear_cache = options.get('clear_cache')
        dry_run = options.get('dry_run')

        if clear_cache:
            if dry_run:
                self.stdout.write("DRY RUN: Would clear existing cache")
            else:
                count = AuthorCache.objects.count()
                AuthorCache.objects.all().delete()
                self.stdout.write(f"Cleared {count} existing cache entries")

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

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Process publications
        stats = {
            'processed_publications': 0,
            'processed_authors': 0,
            'cached_authors': 0,
            'updated_authors': 0,
            'skipped_authors': 0
        }

        for pub in publications:
            stats['processed_publications'] += 1
            
            if not pub.authors:
                continue
                
            self.stdout.write(f"Processing: {pub.title[:80]}...")
            
            for author in pub.authors:
                stats['processed_authors'] += 1
                
                if not isinstance(author, dict):
                    stats['skipped_authors'] += 1
                    continue
                    
                author_name = author.get('name', '')
                scopus_id = author.get('scopus_id')
                orcid_id = author.get('orcid_id')
                given_name = author.get('given_name', '')
                surname = author.get('surname', '')
                
                if not author_name and not scopus_id and not orcid_id:
                    stats['skipped_authors'] += 1
                    continue
                
                if dry_run:
                    self.stdout.write(f"  Would cache: {author_name} (Scopus: {scopus_id})")
                    stats['cached_authors'] += 1
                else:
                    # Check if we're updating or creating
                    normalized = AuthorCache.normalize_name(author_name)
                    existing = AuthorCache.objects.filter(normalized_name=normalized).first()
                    
                    cached_author = AuthorCache.cache_author(
                        name=author_name,
                        scopus_id=scopus_id,
                        orcid_id=orcid_id,
                        given_name=given_name,
                        surname=surname,
                        source=pub.source or 'unknown',
                        confidence_score=0.8  # Lower confidence for existing data
                    )
                    
                    if existing:
                        stats['updated_authors'] += 1
                    else:
                        stats['cached_authors'] += 1

        # Print summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\\n=== CACHE POPULATION SUMMARY ===\\n"
                f"Processed publications: {stats['processed_publications']}\\n"
                f"Processed authors: {stats['processed_authors']}\\n"
                f"Cached new authors: {stats['cached_authors']}\\n"
                f"Updated existing authors: {stats['updated_authors']}\\n"
                f"Skipped authors: {stats['skipped_authors']}\\n"
                f"Total cache entries: {AuthorCache.objects.count()}"
            )
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\\nDRY RUN - No actual changes were made"))