"""
Django management command to deduplicate PMC links in publications.
Removes 'pmc' entries from links dictionary when there's already a pmcid identifier.
"""
import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from academic.models import Publication

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Deduplicate PMC links by removing redundant pmc entries from links dictionary'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to process publications for (optional - if not provided, processes all users)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without making changes'
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        dry_run = options.get('dry_run')

        # Get publications to process
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                publications = Publication.objects.filter(owner=user)
                self.stdout.write(f"Processing publications for user: {user.username}")
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User with ID {user_id} not found"))
                return
        else:
            publications = Publication.objects.all()
            self.stdout.write("Processing publications for all users")

        if not publications.exists():
            self.stdout.write(self.style.WARNING("No publications found"))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Find publications with potential PMC link duplicates
        duplicates_found = 0
        cleaned_publications = 0

        for pub in publications:
            has_pmcid = bool(pub.identifiers and pub.identifiers.get('pmcid'))
            has_pmc_link = bool(pub.links and pub.links.get('pmc'))

            if has_pmcid and has_pmc_link:
                # Check if the PMC link points to the same PMC ID
                pmcid = pub.identifiers.get('pmcid')
                pmc_link = pub.links.get('pmc')

                # Normalize PMC ID format (ensure it starts with PMC)
                if pmcid and not pmcid.startswith('PMC'):
                    pmcid = 'PMC' + pmcid

                # Check if the link contains the same PMC ID
                if pmcid and pmc_link and pmcid in pmc_link:
                    duplicates_found += 1
                    self.stdout.write(
                        f"Found duplicate PMC links for: {pub.title[:60]}..."
                    )
                    self.stdout.write(f"  PMCID identifier: {pmcid}")
                    self.stdout.write(f"  PMC link: {pmc_link}")

                    if not dry_run:
                        # Remove the redundant pmc link
                        del pub.links['pmc']

                        # Clean up empty links dict
                        if not pub.links:
                            pub.links = {}

                        pub.save()
                        cleaned_publications += 1
                        self.stdout.write("  ✓ Removed duplicate PMC link")

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== SUMMARY ===\n"
                f"Publications with duplicate PMC links: {duplicates_found}\n"
                f"Publications cleaned: {cleaned_publications}"
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No actual changes were made"))
        elif duplicates_found == 0:
            self.stdout.write(self.style.SUCCESS("No duplicate PMC links found!"))