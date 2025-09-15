"""
Django management command to sync preprint relations from Crossref
and mark preprints that have been published
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from academic.models import Publication
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync preprint relations from Crossref metadata and mark published preprints'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making changes to the database',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Process only publications for a specific user (by username)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        username = options.get('user')

        self.stdout.write('Starting preprint relation synchronization...')

        # Get publications to process
        publications = Publication.objects.filter(is_ignored=False)
        if username:
            publications = publications.filter(owner__username=username)
            self.stdout.write(f'Processing publications for user: {username}')

        # Exclude preprints themselves from the search
        published_papers = publications.exclude(publication_type='preprint')

        # Collect all preprint DOIs that have been published
        published_preprint_dois = set()
        papers_with_preprints = []

        for paper in published_papers:
            # Check if this paper has preprint relations in its metadata
            if paper.metadata and isinstance(paper.metadata, dict):
                # Check for Crossref relation data
                relations = paper.metadata.get('relation', {})
                if relations:
                    found_preprints = []
                    # Look for various relation types that indicate preprints
                    for relation_type in ['is-version-of', 'has-preprint', 'is-preprint-of']:
                        if relation_type in relations:
                            relation_list = relations[relation_type]
                            if isinstance(relation_list, list):
                                for rel in relation_list:
                                    if isinstance(rel, dict) and 'id' in rel:
                                        # Extract DOI from the relation
                                        preprint_doi = rel['id']
                                        # Clean the DOI (remove URL prefix if present)
                                        if preprint_doi.startswith('https://doi.org/'):
                                            preprint_doi = preprint_doi.replace('https://doi.org/', '')
                                        elif preprint_doi.startswith('http://doi.org/'):
                                            preprint_doi = preprint_doi.replace('http://doi.org/', '')

                                        published_preprint_dois.add(preprint_doi)
                                        found_preprints.append(preprint_doi)

                    if found_preprints:
                        papers_with_preprints.append({
                            'paper': paper,
                            'preprint_dois': found_preprints
                        })
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Found preprint relations for "{paper.title[:50]}...": {", ".join(found_preprints)}'
                            )
                        )

        # Now find and mark preprints that have been published
        if published_preprint_dois:
            self.stdout.write(f'\nFound {len(published_preprint_dois)} preprint DOIs that have been published')

            # Get preprints to check
            preprints = Publication.objects.filter(
                publication_type='preprint',
                doi__in=published_preprint_dois
            )

            if username:
                preprints = preprints.filter(owner__username=username)

            preprints_to_mark = []
            for preprint in preprints:
                if preprint.doi in published_preprint_dois:
                    preprints_to_mark.append(preprint)
                    self.stdout.write(
                        self.style.WARNING(
                            f'Preprint "{preprint.title[:50]}..." (DOI: {preprint.doi}) has been published'
                        )
                    )

            if preprints_to_mark and not dry_run:
                with transaction.atomic():
                    for preprint in preprints_to_mark:
                        # Add a note to metadata about publication status
                        if not preprint.metadata:
                            preprint.metadata = {}
                        preprint.metadata['published_version_exists'] = True

                        # Find which paper published this preprint
                        for paper_info in papers_with_preprints:
                            if preprint.doi in paper_info['preprint_dois']:
                                preprint.metadata['published_as_doi'] = paper_info['paper'].doi
                                preprint.metadata['published_as_title'] = paper_info['paper'].title
                                break

                        preprint.save()

                self.stdout.write(
                    self.style.SUCCESS(
                        f'Marked {len(preprints_to_mark)} preprints as having published versions'
                    )
                )
            elif dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f'DRY RUN: Would mark {len(preprints_to_mark)} preprints as having published versions'
                    )
                )
        else:
            self.stdout.write('No published preprint DOIs found in the metadata')

        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write('Summary:')
        self.stdout.write(f'  Papers with preprint relations: {len(papers_with_preprints)}')
        self.stdout.write(f'  Unique preprint DOIs found: {len(published_preprint_dois)}')
        if not dry_run:
            self.stdout.write(f'  Preprints marked as published: {len(preprints_to_mark) if published_preprint_dois else 0}')

        self.stdout.write(self.style.SUCCESS('\nPreprint relation synchronization complete!'))