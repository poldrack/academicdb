"""
Import resource links from the links spreadsheet and/or a site's publications.json.
"""
from django.core.management.base import BaseCommand, CommandError

from academic.link_import import (
    import_link_records,
    read_links_csv,
    read_links_from_publications_json,
)
from academic.models import AcademicUser


class Command(BaseCommand):
    help = 'Import Code/Data/OSF links from a CSV (type,DOI,url) and/or publications.json'

    def add_arguments(self, parser):
        parser.add_argument('--orcid-id', required=True)
        parser.add_argument('--csv', help='Links CSV with columns type,DOI,url')
        parser.add_argument('--publications-json', help='Site publications.json with links.resources')

    def handle(self, *args, **options):
        if not (options['csv'] or options['publications_json']):
            raise CommandError('Provide --csv and/or --publications-json')
        user = self._get_user(options['orcid_id'])
        records = self._read_records(options)
        result = import_link_records(user, records)
        self.stdout.write(
            f'Created: {result.created}  Existing: {result.existing}  '
            f'Unmatched: {len(result.unmatched_dois)}'
        )
        for doi in result.unmatched_dois:
            self.stdout.write(f'  unmatched DOI: {doi}')

    def _get_user(self, orcid_id):
        try:
            return AcademicUser.objects.get(orcid_id=orcid_id)
        except AcademicUser.DoesNotExist:
            raise CommandError(f'No user with ORCID {orcid_id}')

    def _read_records(self, options):
        records = []
        if options['csv']:
            records += read_links_csv(options['csv'])
        if options['publications_json']:
            records += read_links_from_publications_json(options['publications_json'])
        return records
