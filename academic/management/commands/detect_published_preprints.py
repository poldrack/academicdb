"""
Django management command to detect preprints that have been published as journal articles
"""
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from academic.models import Publication

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Detect preprints that have published journal article versions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to check preprints for (optional, defaults to all users)'
        )
        parser.add_argument(
            '--mark-ignored',
            action='store_true',
            help='Mark detected published preprints as ignored (excluded from CV)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be detected/marked without making changes'
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        mark_ignored = options.get('mark_ignored', False)
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Get users to process
        if user_id:
            try:
                users = [User.objects.get(id=user_id)]
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User with ID {user_id} not found"))
                return
        else:
            users = User.objects.all()

        total_preprints_checked = 0
        total_published_preprints_found = 0
        total_marked_ignored = 0

        for user in users:
            self.stdout.write(f"\nProcessing user: {user.username}")

            preprints_checked, published_found, marked_ignored = self.check_user_preprints(
                user, mark_ignored, dry_run
            )

            total_preprints_checked += preprints_checked
            total_published_preprints_found += published_found
            total_marked_ignored += marked_ignored

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDetection completed!\n"
                f"Preprints checked: {total_preprints_checked}\n"
                f"Published preprints found: {total_published_preprints_found}\n"
                f"Preprints marked as ignored: {total_marked_ignored}"
            )
        )

    def check_user_preprints(self, user, mark_ignored=False, dry_run=False):
        """Check preprints for a specific user"""
        preprints_checked = 0
        published_found = 0
        marked_ignored = 0

        # Get all preprints for this user
        preprints = Publication.objects.filter(
            owner=user,
            is_preprint=True,
            is_ignored=False
        ).order_by('year', 'title')

        for preprint in preprints:
            preprints_checked += 1

            # Check if this preprint has a published version
            published_version = Publication.find_published_version_of_preprint(preprint, user)

            if published_version:
                published_found += 1

                self.stdout.write(
                    f"  Found published version of preprint:"
                )
                self.stdout.write(f"    Preprint: {preprint.doi} - {preprint.title[:80]}...")
                self.stdout.write(f"    Published: {published_version.doi} - {published_version.title[:80]}...")

                if mark_ignored:
                    action_text = "Would mark" if dry_run else "Marking"
                    self.stdout.write(f"    {action_text} preprint as ignored (excluded from CV)")

                    if not dry_run:
                        with transaction.atomic():
                            preprint.is_ignored = True
                            preprint.ignore_reason = f"Published as journal article: {published_version.doi}"
                            preprint.save()

                            # Log the action
                            logger.info(
                                f"Marked preprint {preprint.doi} as ignored - "
                                f"published as {published_version.doi} for user {user.username}"
                            )

                    marked_ignored += 1

        if preprints_checked == 0:
            self.stdout.write("  No preprints found for this user")
        elif published_found == 0:
            self.stdout.write(f"  No published versions found for {preprints_checked} preprints")

        return preprints_checked, published_found, marked_ignored