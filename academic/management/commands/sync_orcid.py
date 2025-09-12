"""
Django management command to synchronize publications from ORCID API
"""
import os
import requests
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from academic.models import Publication

User = get_user_model()

# Import existing ORCID utilities
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../src'))
from academicdb import orcid

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize publications from ORCID API for authenticated users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync specific user by ID (default: all users with ORCID)'
        )
        parser.add_argument(
            '--orcid-id',
            type=str,
            help='Sync specific user by ORCID ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if recently synced'
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.force = options['force']
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Determine which users to sync
        users_to_sync = self.get_users_to_sync(options)
        
        if not users_to_sync:
            self.stdout.write(self.style.WARNING('No users found to sync'))
            return

        total_synced = 0
        for user in users_to_sync:
            try:
                synced_count = self.sync_user_orcid(user)
                total_synced += synced_count
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Synced {synced_count} publications for {user.display_name}'
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Error syncing {user.display_name}: {str(e)}'
                    )
                )
                logger.exception(f'Error syncing user {user.id}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Total publications synced: {total_synced}'
            )
        )

    def get_users_to_sync(self, options):
        """Get list of users to sync based on command options"""
        if options['user_id']:
            try:
                user = User.objects.get(id=options['user_id'])
                if not user.orcid_id:
                    raise CommandError(f'User {user.display_name} has no ORCID ID')
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
            # Sync all users with ORCID connections
            return User.objects.filter(
                orcid_id__isnull=False,
                orcid_token__isnull=False
            ).exclude(orcid_id='')

    def sync_user_orcid(self, user):
        """Sync publications for a single user from ORCID"""
        if not user.is_orcid_connected():
            self.stdout.write(
                self.style.WARNING(
                    f'User {user.display_name} has no valid ORCID connection'
                )
            )
            return 0

        self.stdout.write(f'Syncing ORCID data for {user.display_name} ({user.orcid_id})')
        
        # Fetch ORCID data
        orcid_data = self.fetch_orcid_data(user)
        if not orcid_data:
            return 0

        # Extract DOIs from ORCID record
        dois = orcid.get_dois_from_orcid_record(orcid_data)
        self.stdout.write(f'Found {len(dois)} publications with DOIs in ORCID')

        if not dois:
            return 0

        # Sync publications
        synced_count = 0
        with transaction.atomic():
            for doi in dois:
                if self.sync_publication_from_doi(user, doi):
                    synced_count += 1

        # Update user's last sync time
        if not self.dry_run:
            from django.utils import timezone
            user.last_orcid_sync = timezone.now()
            user.save(update_fields=['last_orcid_sync'])

        return synced_count

    def fetch_orcid_data(self, user):
        """Fetch ORCID data using API"""
        if not user.orcid_token:
            self.stdout.write(
                self.style.ERROR(
                    f'No ORCID token for user {user.display_name}'
                )
            )
            return None

        try:
            # Use ORCID API to get works data
            headers = {
                'Authorization': f'Bearer {user.orcid_token}',
                'Accept': 'application/json'
            }
            
            # Determine API base URL (production vs sandbox)
            if 'sandbox' in user.orcid_id or os.getenv('ORCID_SANDBOX', False):
                base_url = 'https://api.sandbox.orcid.org/v3.0'
            else:
                base_url = 'https://api.orcid.org/v3.0'
            
            url = f'{base_url}/{user.orcid_id}/activities'
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Error fetching ORCID data for {user.display_name}: {str(e)}'
                )
            )
            return None

    def sync_publication_from_doi(self, user, doi):
        """Create or update publication from DOI"""
        doi = doi.lower().strip()
        
        # Check if publication already exists
        existing_pub = Publication.objects.filter(
            owner=user,
            doi=doi
        ).first()

        if existing_pub:
            self.stdout.write(
                f'  Publication already exists: {doi}'
            )
            # Could add logic here to update from external APIs
            return False

        if self.dry_run:
            self.stdout.write(f'  Would create publication: {doi}')
            return True

        # Create minimal publication record from ORCID
        # In a full implementation, this would fetch details from CrossRef/PubMed
        try:
            publication = Publication(
                owner=user,
                doi=doi,
                title=f'Publication with DOI: {doi}',  # Placeholder
                year=2023,  # Placeholder
                source='orcid',
                authors=[{'name': user.get_full_name() or user.username}],
                metadata={
                    'orcid_sync': True,
                    'needs_enrichment': True  # Flag for later enrichment
                }
            )
            publication.save()
            
            self.stdout.write(f'  Created publication: {doi}')
            return True
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'  Error creating publication {doi}: {str(e)}'
                )
            )
            return False