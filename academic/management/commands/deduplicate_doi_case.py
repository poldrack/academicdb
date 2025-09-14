"""
Django management command to deduplicate publications with DOIs that differ only in case.
This command will find DOI pairs like '10.3758/BF03214547' and '10.3758/bf03214547' and merge them.
"""
import logging
import re
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from academic.models import Publication

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Find and deduplicate publications with DOIs that differ only in case'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Process specific user only (default: all users)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deduplicated without making changes'
        )
        parser.add_argument(
            '--auto-merge',
            action='store_true',
            help='Automatically merge duplicates (keeps the first created, deletes others)'
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        dry_run = options.get('dry_run')
        auto_merge = options.get('auto_merge')

        if user_id:
            try:
                user = User.objects.get(id=user_id)
                users = [user]
                self.stdout.write(f"Processing user: {user.username}")
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"User with ID {user_id} not found")
                )
                return
        else:
            users = User.objects.all()
            self.stdout.write(f"Processing all {users.count()} users")

        total_duplicates_found = 0
        total_duplicates_processed = 0

        for user in users:
            self.stdout.write(f"\n--- Processing user: {user.username} ({user.id}) ---")

            # Find DOI duplicates for this user
            duplicates = self.find_doi_duplicates(user)

            if not duplicates:
                self.stdout.write("  No DOI case duplicates found")
                continue

            total_duplicates_found += len(duplicates)
            self.stdout.write(f"  Found {len(duplicates)} sets of DOI case duplicates")

            for lowercase_doi, publications in duplicates.items():
                self.stdout.write(f"\n  DOI: {lowercase_doi}")
                self.stdout.write(f"    {len(publications)} publications found:")

                for i, pub in enumerate(publications):
                    self.stdout.write(
                        f"      {i+1}. ID: {pub.id}, DOI: '{pub.doi}', Title: {pub.title[:50]}..."
                    )
                    self.stdout.write(f"         Created: {pub.created_at}, Source: {pub.source}")

                if auto_merge and not dry_run:
                    merged_count = self.merge_duplicates(publications)
                    total_duplicates_processed += merged_count
                    self.stdout.write(
                        self.style.SUCCESS(f"    Merged {merged_count} duplicates")
                    )
                elif dry_run:
                    self.stdout.write(
                        self.style.WARNING(f"    [DRY RUN] Would merge {len(publications)-1} duplicates")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "    Use --auto-merge to automatically merge these duplicates"
                        )
                    )

        # Summary
        self.stdout.write(f"\n--- SUMMARY ---")
        self.stdout.write(f"Total duplicate sets found: {total_duplicates_found}")

        if auto_merge and not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"Total duplicates processed: {total_duplicates_processed}")
            )
        elif dry_run:
            potential_merges = sum(len(pubs)-1 for _, pubs in duplicates.items() for duplicates in [{}])
            # Recalculate for accurate count
            potential_merges = 0
            for user in users:
                duplicates = self.find_doi_duplicates(user)
                for _, pubs in duplicates.items():
                    potential_merges += len(pubs) - 1
            self.stdout.write(
                self.style.WARNING(f"[DRY RUN] Would process: {potential_merges} duplicates")
            )
        else:
            self.stdout.write("Use --auto-merge to process duplicates automatically")

    def find_doi_duplicates(self, user):
        """Find publications with DOIs that differ only in case for a specific user"""
        # Get all publications with DOIs for this user
        publications = Publication.objects.filter(
            owner=user,
            doi__isnull=False
        ).exclude(doi='').order_by('created_at')

        # Group by lowercase DOI
        doi_groups = defaultdict(list)
        for pub in publications:
            lowercase_doi = pub.doi.lower().strip()
            # Replace repeated slashes with single slash
            lowercase_doi = re.sub(r'/+', '/', lowercase_doi)
            doi_groups[lowercase_doi].append(pub)

        # Return only groups with multiple publications
        duplicates = {}
        for lowercase_doi, pubs in doi_groups.items():
            if len(pubs) > 1:
                # Check if they actually differ in case (not just exact duplicates)
                unique_dois = set(pub.doi for pub in pubs)
                if len(unique_dois) > 1:
                    duplicates[lowercase_doi] = pubs

        return duplicates

    def merge_duplicates(self, publications):
        """Merge duplicate publications, keeping the earliest created one"""
        if len(publications) <= 1:
            return 0

        # Sort by creation date to keep the oldest
        publications = sorted(publications, key=lambda p: p.created_at)
        keeper = publications[0]
        to_delete = publications[1:]

        merged_count = 0

        with transaction.atomic():
            for duplicate in to_delete:
                try:
                    # Before deleting, we might want to merge any unique data
                    # For now, we'll just normalize the keeper's DOI and delete duplicates

                    # Log the merge
                    logger.info(
                        f"Merging duplicate DOI: keeping {keeper.id} "
                        f"(DOI: '{keeper.doi}'), deleting {duplicate.id} "
                        f"(DOI: '{duplicate.doi}')"
                    )

                    # Delete the duplicate
                    duplicate.delete()
                    merged_count += 1

                except Exception as e:
                    logger.error(
                        f"Error merging publication {duplicate.id}: {str(e)}"
                    )
                    self.stdout.write(
                        self.style.ERROR(
                            f"      Error merging publication {duplicate.id}: {str(e)}"
                        )
                    )

            # Ensure keeper has normalized DOI
            keeper.save()  # This will trigger the DOI normalization in the model

        return merged_count