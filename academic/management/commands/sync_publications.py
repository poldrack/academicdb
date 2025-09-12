"""
Django management command to comprehensively sync publications from multiple sources
"""
import os
import logging
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import transaction
from academic.models import Publication

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Comprehensive publication synchronization from ORCID, PubMed, and CrossRef'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync publications for specific user by ID'
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Email address for PubMed API access (required for PubMed sync)'
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
            '--skip-crossref',
            action='store_true',
            help='Skip CrossRef enrichment'
        )
        parser.add_argument(
            '--skip-pubmed',
            action='store_true',
            help='Skip PubMed enrichment'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if recently synced'
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.force = options['force']
        self.user_id = options.get('user_id')
        self.email = options.get('email')
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Get user(s) to sync
        users_to_sync = self.get_users_to_sync()
        
        if not users_to_sync:
            self.stdout.write(self.style.WARNING('No users found to sync'))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'Starting comprehensive sync for {len(users_to_sync)} user(s)'
            )
        )

        total_stats = {
            'users_processed': 0,
            'publications_before': 0,
            'publications_after': 0,
            'new_publications': 0,
            'enriched_publications': 0
        }

        for user in users_to_sync:
            try:
                user_stats = self.sync_user_publications(user, options)
                
                # Aggregate stats
                total_stats['users_processed'] += 1
                total_stats['publications_before'] += user_stats['publications_before']
                total_stats['publications_after'] += user_stats['publications_after']
                total_stats['new_publications'] += user_stats['new_publications']
                total_stats['enriched_publications'] += user_stats['enriched_publications']
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Completed sync for {user.display_name}: '
                        f'{user_stats["new_publications"]} new, '
                        f'{user_stats["enriched_publications"]} enriched'
                    )
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Error syncing {user.display_name}: {str(e)}'
                    )
                )
                logger.exception(f'Error syncing user {user.id}')

        # Final summary
        self.print_final_summary(total_stats)

    def get_users_to_sync(self):
        """Get list of users to sync"""
        if self.user_id:
            try:
                user = User.objects.get(id=self.user_id)
                return [user]
            except User.DoesNotExist:
                raise CommandError(f'User with ID {self.user_id} not found')
        else:
            # Sync all users with ORCID connections
            return list(User.objects.filter(
                orcid_id__isnull=False,
                orcid_token__isnull=False
            ).exclude(orcid_id=''))

    def sync_user_publications(self, user, options):
        """Sync publications for a single user through all stages"""
        self.stdout.write(f'\n🔄 Syncing publications for {user.display_name} ({user.orcid_id})')
        
        # Count initial publications
        initial_count = Publication.objects.filter(owner=user).count()
        
        user_stats = {
            'publications_before': initial_count,
            'publications_after': 0,
            'new_publications': 0,
            'enriched_publications': 0
        }

        # Stage 1: ORCID Sync (get DOIs)
        if not options['skip_orcid']:
            self.stdout.write('  📋 Stage 1: Syncing from ORCID...')
            new_from_orcid = self.sync_from_orcid(user, options)
            user_stats['new_publications'] += new_from_orcid
        
        # Stage 2: CrossRef Enrichment (get metadata from DOIs)
        if not options['skip_crossref']:
            self.stdout.write('  📚 Stage 2: Enriching with CrossRef...')
            enriched_crossref = self.enrich_with_crossref(user, options)
            user_stats['enriched_publications'] += enriched_crossref
        
        # Stage 3: PubMed Enrichment (get additional metadata)
        if not options['skip_pubmed'] and self.email:
            self.stdout.write('  🧬 Stage 3: Enriching with PubMed...')
            enriched_pubmed = self.enrich_with_pubmed(user, options)
            user_stats['enriched_publications'] += enriched_pubmed
        
        # Final count
        user_stats['publications_after'] = Publication.objects.filter(owner=user).count()
        
        return user_stats

    def sync_from_orcid(self, user, options):
        """Sync publications from ORCID"""
        try:
            # Call the ORCID sync command
            call_command(
                'sync_orcid',
                user_id=user.id,
                dry_run=self.dry_run,
                force=self.force,
                verbosity=0  # Reduce output
            )
            
            # Count new publications (rough estimate)
            # In a real implementation, we'd return this from the sync_orcid command
            return 0  # Placeholder
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'    Error in ORCID sync: {str(e)}')
            )
            return 0

    def enrich_with_crossref(self, user, options):
        """Enrich publications with CrossRef data"""
        try:
            # Count publications that need enrichment
            publications_needing_enrichment = Publication.objects.filter(
                owner=user,
                doi__isnull=False
            ).exclude(
                doi=''
            ).exclude(
                metadata__crossref_enriched=True
            )
            
            if not publications_needing_enrichment.exists():
                self.stdout.write('    No publications need CrossRef enrichment')
                return 0
            
            count_before = publications_needing_enrichment.count()
            
            # Call the CrossRef enrichment command
            call_command(
                'enrich_crossref',
                user_id=user.id,
                dry_run=self.dry_run,
                force=self.force,
                verbosity=0
            )
            
            return count_before  # Assume all were enriched
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'    Error in CrossRef enrichment: {str(e)}')
            )
            return 0

    def enrich_with_pubmed(self, user, options):
        """Enrich publications with PubMed data"""
        if not self.email:
            self.stdout.write('    Skipping PubMed enrichment (no email provided)')
            return 0
            
        try:
            # Count publications that could benefit from PubMed data
            publications_for_pubmed = Publication.objects.filter(
                owner=user,
                doi__isnull=False,
                publication_type='journal-article'
            ).exclude(
                doi=''
            ).exclude(
                metadata__pubmed_enriched=True
            )
            
            if not publications_for_pubmed.exists():
                self.stdout.write('    No publications need PubMed enrichment')
                return 0
                
            count_before = publications_for_pubmed.count()
            
            # Call the PubMed enrichment command
            call_command(
                'enrich_pubmed',
                email=self.email,
                user_id=user.id,
                dry_run=self.dry_run,
                verbosity=0
            )
            
            return count_before  # Assume all were enriched
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'    Error in PubMed enrichment: {str(e)}')
            )
            return 0

    def print_final_summary(self, stats):
        """Print final synchronization summary"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS('📊 SYNCHRONIZATION COMPLETE')
        )
        self.stdout.write('='*60)
        
        self.stdout.write(f"Users processed: {stats['users_processed']}")
        self.stdout.write(f"Publications before: {stats['publications_before']}")
        self.stdout.write(f"Publications after: {stats['publications_after']}")
        self.stdout.write(f"New publications: {stats['new_publications']}")
        self.stdout.write(f"Enriched publications: {stats['enriched_publications']}")
        
        if stats['publications_after'] > stats['publications_before']:
            net_increase = stats['publications_after'] - stats['publications_before']
            self.stdout.write(
                self.style.SUCCESS(f"Net increase: +{net_increase} publications")
            )
        
        self.stdout.write('\n💡 Next steps:')
        self.stdout.write('   • Review publications in Django admin')
        self.stdout.write('   • Check for any publications needing manual review')
        self.stdout.write('   • Set up periodic sync using cron or celery')
        self.stdout.write('='*60)