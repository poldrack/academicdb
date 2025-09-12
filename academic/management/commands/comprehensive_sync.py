"""
Django management command for comprehensive database synchronization.
This command orchestrates all sync operations in the correct order.
"""
import logging
import time
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from django.db import models
from io import StringIO
import sys

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Comprehensive synchronization of academic database from all external sources'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync specific user by ID (default: all users)'
        )
        parser.add_argument(
            '--orcid-id',
            type=str,
            help='Sync specific user by ORCID ID'
        )
        parser.add_argument(
            '--skip-recent',
            action='store_true',
            help='Skip users synced within last 24 hours'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes'
        )
        parser.add_argument(
            '--skip-orcid',
            action='store_true',
            help='Skip ORCID synchronization'
        )
        parser.add_argument(
            '--skip-pubmed',
            action='store_true',
            help='Skip PubMed synchronization'
        )
        parser.add_argument(
            '--skip-scopus',
            action='store_true',
            help='Skip Scopus synchronization'
        )
        parser.add_argument(
            '--skip-enrichment',
            action='store_true',
            help='Skip CrossRef enrichment'
        )
        parser.add_argument(
            '--skip-postprocessing',
            action='store_true',
            help='Skip post-processing (coauthors, PMC lookup, etc.)'
        )
        parser.add_argument(
            '--parallel',
            action='store_true',
            help='Run database syncs in parallel (experimental)'
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.skip_recent = options['skip_recent']
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Get users to sync
        users_to_sync = self.get_users_to_sync(options)
        
        if not users_to_sync:
            self.stdout.write(self.style.WARNING('No users found to sync'))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'Starting comprehensive sync for {len(users_to_sync)} users'
            )
        )

        # Track overall statistics
        total_stats = {
            'users_processed': 0,
            'users_failed': 0,
            'total_publications': 0,
            'orcid_synced': 0,
            'pubmed_synced': 0,
            'scopus_synced': 0,
            'enriched': 0,
            'errors': []
        }

        for user in users_to_sync:
            try:
                self.stdout.write(f'\n{"="*60}')
                self.stdout.write(f'Syncing user: {user.display_name} (ID: {user.id})')
                self.stdout.write(f'{"="*60}')
                
                user_stats = self.sync_user_comprehensive(user, options)
                
                # Update total stats
                total_stats['users_processed'] += 1
                for key in ['total_publications', 'orcid_synced', 'pubmed_synced', 
                           'scopus_synced', 'enriched']:
                    total_stats[key] += user_stats.get(key, 0)
                
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Completed sync for {user.display_name}')
                )
                
            except Exception as e:
                total_stats['users_failed'] += 1
                total_stats['errors'].append(f'{user.display_name}: {str(e)}')
                self.stdout.write(
                    self.style.ERROR(f'✗ Failed sync for {user.display_name}: {str(e)}')
                )
                logger.exception(f'Comprehensive sync failed for user {user.id}')

        # Final summary
        self.print_final_summary(total_stats)

    def get_users_to_sync(self, options):
        """Get list of users to sync based on command options"""
        if options['user_id']:
            try:
                user = User.objects.get(id=options['user_id'])
                return [user]
            except User.DoesNotExist:
                raise CommandError(f'User with ID {options["user_id"]} not found')
        
        elif options['orcid_id']:
            try:
                user = User.objects.get(orcid_id=options['orcid_id'])
                return [user]
            except User.DoesNotExist:
                raise CommandError(f'User with ORCID ID {options["orcid_id"]} not found')
        
        else:
            # Get all active users
            queryset = User.objects.filter(is_active=True)
            
            # Skip recently synced users if requested
            if self.skip_recent:
                cutoff = timezone.now() - timedelta(hours=24)
                queryset = queryset.filter(
                    models.Q(last_orcid_sync__lt=cutoff) |
                    models.Q(last_orcid_sync__isnull=True)
                )
            
            return list(queryset.order_by('id'))

    def sync_user_comprehensive(self, user, options):
        """Perform comprehensive sync for a single user"""
        user_stats = {
            'total_publications': 0,
            'orcid_synced': 0,
            'pubmed_synced': 0,
            'scopus_synced': 0,
            'enriched': 0
        }
        
        start_time = time.time()
        
        # Get initial publication count
        initial_count = user.publications.count() if hasattr(user, 'publications') else 0
        
        # Phase 1: Database Synchronization
        self.stdout.write(f'\n📥 Phase 1: Database Synchronization')
        
        if not options['skip_orcid']:
            orcid_count = self.sync_orcid_for_user(user, options)
            user_stats['orcid_synced'] = orcid_count
        
        if not options['skip_pubmed']:
            pubmed_count = self.sync_pubmed_for_user(user, options) 
            user_stats['pubmed_synced'] = pubmed_count
            
        if not options['skip_scopus']:
            scopus_count = self.sync_scopus_for_user(user, options)
            user_stats['scopus_synced'] = scopus_count

        # Phase 2: Data Enrichment
        if not options['skip_enrichment']:
            self.stdout.write(f'\n🔍 Phase 2: Data Enrichment')
            enriched_count = self.enrich_publications_for_user(user, options)
            user_stats['enriched'] = enriched_count

        # Phase 3: Post-Processing
        if not options['skip_postprocessing']:
            self.stdout.write(f'\n⚙️ Phase 3: Post-Processing')
            self.run_postprocessing_for_user(user, options)

        # Calculate final stats
        final_count = user.publications.count() if hasattr(user, 'publications') else 0
        user_stats['total_publications'] = final_count - initial_count
        
        elapsed = time.time() - start_time
        self.stdout.write(
            f'\n📊 User sync completed in {elapsed:.1f}s: '
            f'{user_stats["total_publications"]} new publications'
        )
        
        return user_stats

    def sync_orcid_for_user(self, user, options):
        """Sync ORCID data for user"""
        if not user.is_orcid_connected:
            self.stdout.write(f'  ⚠️  ORCID not connected for {user.display_name}')
            return 0
            
        try:
            self.stdout.write(f'  🔄 Syncing ORCID data...')
            output = self.run_command_with_capture('sync_orcid', user_id=user.id, verbosity=0)
            
            # Parse output for sync count
            sync_count = self.parse_sync_count(output, 'Synced')
            self.stdout.write(f'  ✓ ORCID: {sync_count} publications')
            return sync_count
            
        except Exception as e:
            self.stdout.write(f'  ✗ ORCID sync failed: {str(e)}')
            return 0

    def sync_pubmed_for_user(self, user, options):
        """Sync PubMed data for user"""
        if not user.has_pubmed_query:
            self.stdout.write(f'  ⚠️  No PubMed query for {user.display_name}')
            return 0
            
        try:
            self.stdout.write(f'  🔄 Syncing PubMed data...')
            output = self.run_command_with_capture('sync_pubmed', user_id=user.id, verbosity=0)
            
            # Parse output for sync count
            sync_count = self.parse_sync_count(output, 'Created')
            self.stdout.write(f'  ✓ PubMed: {sync_count} publications')
            return sync_count
            
        except Exception as e:
            self.stdout.write(f'  ✗ PubMed sync failed: {str(e)}')
            return 0

    def sync_scopus_for_user(self, user, options):
        """Sync Scopus data for user"""
        if not user.has_scopus_id:
            self.stdout.write(f'  ⚠️  No Scopus ID for {user.display_name}')
            return 0
            
        try:
            self.stdout.write(f'  🔄 Syncing Scopus data...')
            output = self.run_command_with_capture('sync_scopus', user_id=user.id, verbosity=0)
            
            # Parse output for sync count
            sync_count = self.parse_sync_count(output, 'Created')
            self.stdout.write(f'  ✓ Scopus: {sync_count} publications')
            return sync_count
            
        except Exception as e:
            self.stdout.write(f'  ✗ Scopus sync failed: {str(e)}')
            return 0

    def enrich_publications_for_user(self, user, options):
        """Enrich publications with CrossRef data"""
        try:
            self.stdout.write(f'  🔍 Enriching with CrossRef...')
            output = self.run_command_with_capture('enrich_crossref', user_id=user.id, verbosity=0)
            
            # Parse output for enrichment count
            enriched_count = self.parse_sync_count(output, 'enriched')
            self.stdout.write(f'  ✓ Enriched: {enriched_count} publications')
            return enriched_count
            
        except Exception as e:
            self.stdout.write(f'  ✗ CrossRef enrichment failed: {str(e)}')
            return 0

    def run_postprocessing_for_user(self, user, options):
        """Run post-processing tasks"""
        postprocessing_tasks = [
            ('lookup_pmc_ids', 'PMC ID lookup'),
            ('lookup_author_scopus_ids', 'Author Scopus ID lookup'),
        ]
        
        for command_name, description in postprocessing_tasks:
            try:
                self.stdout.write(f'  ⚙️ Running {description}...')
                self.run_command_with_capture(command_name, user_id=user.id, verbosity=0)
                self.stdout.write(f'  ✓ {description} completed')
                
            except Exception as e:
                self.stdout.write(f'  ✗ {description} failed: {str(e)}')
                continue

        # Extract coauthors (optional, doesn't fail the sync)
        try:
            self.stdout.write(f'  🤝 Extracting coauthor data...')
            self.run_command_with_capture('extract_coauthors', user_id=user.id, verbosity=0)
            self.stdout.write(f'  ✓ Coauthor extraction completed')
        except Exception as e:
            self.stdout.write(f'  ⚠️  Coauthor extraction failed: {str(e)}')

    def run_command_with_capture(self, command_name, **kwargs):
        """Run a Django management command and capture its output"""
        if self.dry_run:
            return f"DRY RUN: Would run {command_name}"
            
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        
        try:
            call_command(command_name, **kwargs)
            output = captured_output.getvalue()
            return output
        finally:
            sys.stdout = old_stdout

    def parse_sync_count(self, output, keyword):
        """Parse sync count from command output"""
        try:
            lines = output.split('\n')
            for line in lines:
                if keyword.lower() in line.lower():
                    # Try to extract number from line
                    import re
                    numbers = re.findall(r'\d+', line)
                    if numbers:
                        return int(numbers[0])
            return 0
        except:
            return 0

    def print_final_summary(self, stats):
        """Print final summary of sync results"""
        self.stdout.write(f'\n{"="*80}')
        self.stdout.write(f'COMPREHENSIVE SYNC SUMMARY')
        self.stdout.write(f'{"="*80}')
        
        self.stdout.write(f'Users processed: {stats["users_processed"]}')
        self.stdout.write(f'Users failed: {stats["users_failed"]}')
        self.stdout.write(f'Total new publications: {stats["total_publications"]}')
        self.stdout.write(f'ORCID synced: {stats["orcid_synced"]}')
        self.stdout.write(f'PubMed synced: {stats["pubmed_synced"]}')
        self.stdout.write(f'Scopus synced: {stats["scopus_synced"]}')
        self.stdout.write(f'Publications enriched: {stats["enriched"]}')
        
        if stats['errors']:
            self.stdout.write(f'\n❌ ERRORS:')
            for error in stats['errors']:
                self.stdout.write(f'  • {error}')
        
        if stats['users_failed'] == 0:
            self.stdout.write(
                self.style.SUCCESS('\n🎉 All syncs completed successfully!')
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'\n⚠️  {stats["users_failed"]} users had errors during sync'
                )
            )