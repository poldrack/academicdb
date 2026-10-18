"""
Back up the whole database as a portable, gzipped Django JSON fixture,
with a sidecar file of per-model row counts used to verify restores.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from academic.db_transfer import counts_path_for, dump_fixture, model_counts


class Command(BaseCommand):
    help = 'Back up all data to DIR/academicdb_YYYYMMDD_HHMMSS.json.gz'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default='backups')

    def handle(self, *args, **options):
        fixture = self._write_backup(Path(options['output_dir']))
        self.stdout.write(str(fixture))

    def _write_backup(self, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        fixture = output_dir / f'academicdb_{stamp}.json.gz'
        dump_fixture('default', fixture)
        counts_path_for(fixture).write_text(json.dumps(model_counts('default'), indent=2))
        return fixture
