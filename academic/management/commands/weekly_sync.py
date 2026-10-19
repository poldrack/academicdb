"""Run the weekly discovery/enrichment sync for one owner and write a JSON report."""
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from academic.models import AcademicUser
from academic.sync.http import SourceError
from academic.sync.run import SyncConfig, SyncReport, run_weekly_sync


def _config(orcid) -> SyncConfig:
    try:
        return SyncConfig.from_env(orcid, os.environ)
    except ValueError as exc:
        raise CommandError(str(exc)) from None


def _user(orcid) -> AcademicUser:
    try:
        return AcademicUser.objects.get(orcid_id=orcid)
    except AcademicUser.DoesNotExist:
        raise CommandError(f'No user with ORCID {orcid}') from None


class Command(BaseCommand):
    help = 'Discover new works, enrich existing ones and propose preprint hides.'

    def add_arguments(self, parser):
        parser.add_argument('--orcid-id', required=True)
        parser.add_argument('--report', default='sync_report.json')
        parser.add_argument('--dry-run', action='store_true',
                            help='Run the write phase, then roll it back')

    def handle(self, *args, **options):
        report_path = Path(options['report'])
        report_path.unlink(missing_ok=True)
        config = _config(options['orcid_id'])
        user = _user(options['orcid_id'])
        report = self._run(user, config, report_path, options['dry_run'])
        report_path.write_text(report.to_json())
        self.stdout.write(report.summary())
        if report.errors:
            raise CommandError(
                f'{len(report.errors)} error(s) during sync; see {report_path}')

    def _run(self, user, config, report_path, dry_run) -> SyncReport:
        now = timezone.now()
        try:
            return run_weekly_sync(user, config, now, dry_run=dry_run)
        except SourceError as exc:
            failed = SyncReport(run_at=now.isoformat(), cutoff=config.cutoff.isoformat(),
                                errors=[f'openalex: {exc}'])
            report_path.write_text(failed.to_json())
            raise CommandError(f'OpenAlex fetch failed, nothing written: {exc}') from None
