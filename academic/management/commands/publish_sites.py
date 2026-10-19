"""Publish the public YAML to both sites and drive the weekly review PR."""
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from academic.models import AcademicUser
from academic.publish.decisions import ReviewFileError
from academic.publish.github import GitHubError
from academic.publish.publish import PublishConfig, run_publish_sites
from academic.publish.review_pr import ReviewPRError

PIPELINE_ERRORS = (GitHubError, ReviewFileError, ReviewPRError)


def get_user(orcid_id):
    try:
        return AcademicUser.objects.get(orcid_id=orcid_id)
    except AcademicUser.DoesNotExist:
        raise CommandError(f'No user with ORCID ID {orcid_id}') from None


class Command(BaseCommand):
    help = ('Process a decided review PR, publish both sites, then open '
            'or remind about the review PR')

    def add_arguments(self, parser):
        parser.add_argument('--orcid-id', required=True)
        parser.add_argument('--dry-run', action='store_true',
                            help='Roll back database writes and only log '
                                 'GitHub writes')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        config = PublishConfig.from_env(os.environ, dry_run=dry_run)
        user = get_user(options['orcid_id'])
        try:
            run_publish_sites(user, config, timezone.now(), dry_run=dry_run,
                              log=self.stdout.write)
        except PIPELINE_ERRORS as exc:
            raise CommandError(str(exc)) from None
