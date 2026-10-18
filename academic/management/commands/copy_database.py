"""
Copy all data from a source database into the (empty) default database,
then compare row counts for every model.
"""
import copy
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from academic.db_transfer import TargetNotEmptyError, copy_all_data, model_counts


SOURCE_ALIAS = 'source'


class Command(BaseCommand):
    help = 'Copy all data from a source database into the empty default database'

    def add_arguments(self, parser):
        parser.add_argument('--source-sqlite', help='Path to the source SQLite file')
        parser.add_argument('--source-alias', help='Existing database alias to copy from')

    def handle(self, *args, **options):
        source = self._resolve_source(options['source_sqlite'], options['source_alias'])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mismatches = copy_all_data(source, 'default', Path(tmp))
        except TargetNotEmptyError as e:
            raise CommandError(str(e))
        self._print_counts(source)
        if mismatches:
            raise CommandError(f'Count mismatch: {mismatches}')
        self.stdout.write('All counts match.')

    def _resolve_source(self, sqlite_path, alias):
        if bool(sqlite_path) == bool(alias):
            raise CommandError('Provide exactly one of --source-sqlite or --source-alias')
        if alias:
            return alias
        return self._register_sqlite(Path(sqlite_path).resolve())

    def _register_sqlite(self, path):
        if not path.exists():
            raise CommandError(f'Source file {path} does not exist')
        default_name = str(connections.databases['default'].get('NAME', ''))
        if default_name and Path(default_name).resolve() == path:
            raise CommandError('Source and target are the same database')
        settings = copy.deepcopy(connections.databases['default'])
        settings.update({'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(path),
                         'OPTIONS': {}, 'HOST': '', 'PORT': '', 'USER': '', 'PASSWORD': ''})
        connections.databases[SOURCE_ALIAS] = settings
        return SOURCE_ALIAS

    def _print_counts(self, source):
        source_counts = model_counts(source)
        target_counts = model_counts('default')
        self.stdout.write(f"{'model':<40}{'source':>10}{'target':>10}")
        for label in sorted(source_counts):
            self.stdout.write(
                f'{label:<40}{source_counts[label]:>10}{target_counts.get(label, 0):>10}'
            )
