"""
Restore a backup fixture into the (empty) default database and verify
row counts against the backup's sidecar counts file when present.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from academic.db_transfer import (
    TargetNotEmptyError,
    count_mismatches,
    counts_path_for,
    load_fixture,
    model_counts,
)


class Command(BaseCommand):
    help = 'Restore a backup fixture into the empty default database'

    def add_arguments(self, parser):
        parser.add_argument('fixture', help='Path to academicdb_*.json.gz')

    def handle(self, *args, **options):
        fixture = Path(options['fixture'])
        if not fixture.exists():
            raise CommandError(f'Backup {fixture} does not exist')
        try:
            load_fixture(fixture, 'default')
        except TargetNotEmptyError as e:
            raise CommandError(str(e))
        self._verify_counts(fixture)
        self.stdout.write(f'Restored {fixture}')

    def _verify_counts(self, fixture):
        counts_path = counts_path_for(fixture)
        if not counts_path.exists():
            self.stdout.write('No counts file found; skipping count check.')
            return
        expected = json.loads(counts_path.read_text())
        mismatches = count_mismatches(expected, model_counts('default'))
        if mismatches:
            raise CommandError(f'Count mismatch: {mismatches}')
        self.stdout.write('All counts match.')
