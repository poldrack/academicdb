"""
Back up the whole database as a portable, gzipped Django JSON fixture,
with a sidecar file of per-model row counts used to verify restores.
With --upload, also copy it to Neon object storage and prune old backups.
"""
import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from academic.db_transfer import counts_path_for, dump_fixture, model_counts
from academic.remote_backup import prune_backups, s3_client_from_env, upload_backup


class Command(BaseCommand):
    help = 'Back up all data to DIR/academicdb_YYYYMMDD_HHMMSS.json.gz'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default='backups')
        parser.add_argument('--upload', action='store_true',
                            help='Also upload to Neon object storage (BACKUP_BUCKET)')

    def handle(self, *args, **options):
        bucket = self._bucket() if options['upload'] else None
        fixture = self._write_backup(Path(options['output_dir']))
        if bucket:
            self._upload(bucket, fixture)
        self.stdout.write(str(fixture))

    def _bucket(self):
        bucket = os.environ.get('BACKUP_BUCKET')
        if not bucket:
            raise CommandError('BACKUP_BUCKET must be set to upload backups')
        return bucket

    def _write_backup(self, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        fixture = output_dir / f'academicdb_{stamp}.json.gz'
        dump_fixture('default', fixture)
        counts_path_for(fixture).write_text(json.dumps(model_counts('default'), indent=2))
        return fixture

    def _upload(self, bucket, fixture):
        try:
            client = s3_client_from_env(os.environ)
        except ValueError as e:
            raise CommandError(str(e))
        for key in upload_backup(client, bucket, fixture):
            self.stdout.write(f'uploaded {key}')
        for key in prune_backups(client, bucket):
            self.stdout.write(f'pruned {key}')
