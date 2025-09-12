"""
Django management command to clear all publications for a user
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from academic.models import Publication

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clear all publications for specified user(s)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Clear publications for specific user by ID'
        )
        parser.add_argument(
            '--orcid-id',
            type=str,
            help='Clear publications for specific user by ORCID ID'
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Clear publications for specific user by username'
        )
        parser.add_argument(
            '--all-users',
            action='store_true',
            help='Clear publications for ALL users (use with caution!)'
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

        # Get users to clear publications for
        users_to_clear = self.get_users_to_clear(options)
        
        if not users_to_clear:
            self.stdout.write(self.style.WARNING('No users found to clear publications for'))
            return

        total_deleted = 0
        
        for user in users_to_clear:
            pub_count = user.publications.count() if hasattr(user, 'publications') else 0
            
            if pub_count == 0:
                self.stdout.write(f'User {user.display_name}: No publications to delete')
                continue
                
            self.stdout.write(
                f'User {user.display_name} ({user.username}): {pub_count} publications'
            )
            
            if self.dry_run:
                self.stdout.write(f'  Would delete {pub_count} publications')
                total_deleted += pub_count
            else:
                try:
                    deleted_count = user.publications.all().delete()[0]
                    total_deleted += deleted_count
                    
                    # Update user's last sync time
                    from django.utils import timezone
                    user.last_orcid_sync = timezone.now()
                    user.save(update_fields=['last_orcid_sync'])
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Deleted {deleted_count} publications')
                    )
                    
                    # Log the action
                    logger.info(f"Admin cleared {deleted_count} publications for user {user.id}")
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Failed to delete publications: {str(e)}')
                    )
                    logger.error(f"Error clearing publications for user {user.id}: {str(e)}")

        if self.dry_run:
            self.stdout.write(
                self.style.WARNING(f'Would delete {total_deleted} total publications')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully deleted {total_deleted} total publications')
            )

    def get_users_to_clear(self, options):
        """Get list of users to clear publications for"""
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
                    'Clearing publications for ALL users requires explicit --confirm flag'
                )
            return list(User.objects.filter(is_active=True))
        
        else:
            raise CommandError(
                'Must specify one of: --user-id, --orcid-id, --username, or --all-users'
            )