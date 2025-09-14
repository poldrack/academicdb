from django.core.management.base import BaseCommand
from academic.models import Publication


class Command(BaseCommand):
    help = 'Detect and mark preprints based on DOI patterns'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Find all publications with DOIs
        publications_with_dois = Publication.objects.exclude(doi__isnull=True).exclude(doi__exact='')

        preprint_count = 0
        updated_count = 0

        self.stdout.write(f"Checking {publications_with_dois.count()} publications with DOIs...")

        for publication in publications_with_dois:
            old_status = publication.is_preprint
            old_type = publication.publication_type
            is_preprint = Publication.is_preprint_doi(publication.doi)

            if is_preprint:
                preprint_count += 1

                # Check if we need to update
                needs_update = (old_status != is_preprint) or (old_type != 'preprint')

                if not dry_run and needs_update:
                    # Use the model's detect_preprint_status method to update both fields
                    publication.detect_preprint_status()
                    publication.save()
                    updated_count += 1

                server = 'bioRxiv' if publication.doi.startswith('10.1101') else \
                        'arXiv' if publication.doi.startswith('10.48550') else \
                        'PsyArXiv' if publication.doi.startswith('10.31234') else 'Unknown'

                if dry_run:
                    status = "would be marked"
                elif needs_update:
                    status = "updated"
                else:
                    status = "already correct"

                type_info = f"(type: {old_type} -> preprint)" if old_type != 'preprint' else f"(type: {old_type})"
                self.stdout.write(f"  {publication.title[:60]}... - {status} as {server} preprint {type_info}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"DRY RUN: Found {preprint_count} preprints that would be marked")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Successfully marked {updated_count} publications as preprints")
            )
            self.stdout.write(f"Total preprints found: {preprint_count}")