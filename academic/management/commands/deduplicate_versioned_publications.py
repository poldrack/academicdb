"""
Django management command to deduplicate versioned publications
"""
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from academic.models import Publication

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Deduplicate versioned publications, keeping only the latest version'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to deduplicate publications for (optional, defaults to all users)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No publications will be deleted"))

        # Get users to process
        if user_id:
            try:
                users = [User.objects.get(id=user_id)]
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User with ID {user_id} not found"))
                return
        else:
            users = User.objects.all()

        total_duplicates_found = 0
        total_publications_removed = 0

        for user in users:
            self.stdout.write(f"\nProcessing user: {user.username}")

            duplicates_found, publications_removed = self.deduplicate_user_publications(
                user, dry_run
            )

            total_duplicates_found += duplicates_found
            total_publications_removed += publications_removed

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDeduplication completed!\n"
                f"Duplicate groups found: {total_duplicates_found}\n"
                f"Publications removed: {total_publications_removed}"
            )
        )

    def deduplicate_user_publications(self, user, dry_run=False):
        """Deduplicate publications for a specific user"""
        duplicates_found = 0
        publications_removed = 0

        # Get all publications with DOIs that contain version patterns
        # Include both preprints and published articles
        versioned_pubs = Publication.objects.filter(
            owner=user,
            doi__iregex=r'.*/v\d+$'
        ).order_by('doi')

        # Group by base DOI
        base_doi_groups = {}

        for pub in versioned_pubs:
            base_doi, version = Publication.normalize_doi_for_deduplication(pub.doi)
            if base_doi not in base_doi_groups:
                base_doi_groups[base_doi] = []
            base_doi_groups[base_doi].append((pub, version))

        # Process each group
        for base_doi, pub_versions in base_doi_groups.items():
            if len(pub_versions) <= 1:
                continue  # No duplicates

            duplicates_found += 1

            # Sort by version number (highest first)
            pub_versions.sort(key=lambda x: x[1] if x[1] is not None else 0, reverse=True)

            latest_pub, latest_version = pub_versions[0]
            older_versions = pub_versions[1:]

            # Determine if these are preprints or published articles
            pub_type = "preprint" if latest_pub.is_preprint else "published article"
            self.stdout.write(f"  Found {len(pub_versions)} versions of {pub_type}: {base_doi}")
            self.stdout.write(f"    Keeping: {latest_pub.doi} (version {latest_version}) - {latest_pub.title[:60]}...")

            for older_pub, older_version in older_versions:
                self.stdout.write(f"    {'Would remove' if dry_run else 'Removing'}: {older_pub.doi} (version {older_version}) - {older_pub.title[:60]}...")

                if not dry_run:
                    with transaction.atomic():
                        # Log the removal
                        logger.info(
                            f"Removing duplicate {pub_type}: {older_pub.doi} "
                            f"(keeping {latest_pub.doi}) for user {user.username}"
                        )
                        older_pub.delete()

                publications_removed += 1

        return duplicates_found, publications_removed