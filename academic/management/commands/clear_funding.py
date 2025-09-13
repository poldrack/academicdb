"""
Django management command to clear all funding records for a user
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from academic.models import Funding

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clear all funding records for specified user(s)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Clear funding for specific user by ID'
        )
        parser.add_argument(
            '--orcid-id',
            type=str,
            help='Clear funding for specific user by ORCID ID'
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Clear funding for specific user by username'
        )
        parser.add_argument(
            '--all-users',
            action='store_true',
            help='Clear funding for ALL users (use with caution!)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without making changes'
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Required to confirm deletion (safety measure)'
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        
        if not options['confirm'] and not self.dry_run:
            raise CommandError(
                'This command requires --confirm flag to proceed with deletion. '
                'Use --dry-run to see what would be deleted.'
            )
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Get users to clear funding for
        users_to_clear = self.get_users_to_clear(options)
        
        if not users_to_clear:
            self.stdout.write(self.style.WARNING('No users found to clear funding for'))
            return

        total_deleted = 0
        
        for user in users_to_clear:
            funding_count = user.funding.count() if hasattr(user, 'funding') else 0
            
            if funding_count == 0:
                self.stdout.write(f'User {user.display_name}: No funding records to delete')
                continue
                
            self.stdout.write(
                f'User {user.display_name} ({user.username}): {funding_count} funding records'
            )
            
            if self.dry_run:
                self.stdout.write(f'  Would delete {funding_count} funding records')
                total_deleted += funding_count
            else:
                try:
                    deleted_count = user.funding.all().delete()[0]
                    total_deleted += deleted_count
                    
                    # Update user's last sync time
                    from django.utils import timezone
                    user.last_orcid_sync = timezone.now()
                    user.save(update_fields=['last_orcid_sync'])
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Deleted {deleted_count} funding records')
                    )
                    
                    # Log the action
                    logger.info(f"Admin cleared {deleted_count} funding records for user {user.id}")
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Failed to delete funding records: {str(e)}')
                    )
                    logger.error(f"Error clearing funding for user {user.id}: {str(e)}")

        if self.dry_run:
            self.stdout.write(
                self.style.WARNING(f'Would delete {total_deleted} total funding records')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully deleted {total_deleted} total funding records')
            )

    def get_users_to_clear(self, options):
        """Get list of users to clear funding for"""
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
        
        elif options['username']:
            try:
                user = User.objects.get(username=options['username'])
                return [user]
            except User.DoesNotExist:
                raise CommandError(f'User with username {options["username"]} not found')
        
        elif options['all_users']:
            if not options['confirm']:
                raise CommandError(
                    'Clearing funding for ALL users requires explicit --confirm flag'
                )
            return list(User.objects.filter(is_active=True))
        
        else:
            raise CommandError(
                'Must specify one of: --user-id, --orcid-id, --username, or --all-users'
            )