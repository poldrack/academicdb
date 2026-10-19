"""Open, update or close pipeline failure and stalled-run issues."""
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from academic.publish.alerts import (
    check_heartbeat, report_failure, resolve_failure)
from academic.publish.github import GitHub, GitHubError


def require_env(name):
    value = os.environ.get(name)
    if not value:
        raise CommandError(f'{name} is not set')
    return value


def dispatch(options, gh, repo, log):
    action, workflow = options['action'], options['workflow']
    if action == 'heartbeat':
        healthy = check_heartbeat(gh, repo, workflow, timezone.now(),
                                  options['max_age_days'])
        log('healthy' if healthy else 'stalled: issue opened or updated')
        return
    run_url = options['run_url']
    if not run_url:
        raise CommandError(f'--run-url is required for {action}')
    if action == 'failure':
        log(f'issue #{report_failure(gh, repo, workflow, run_url)}')
    else:
        log('closed' if resolve_failure(gh, repo, workflow, run_url)
            else 'no open issue')


class Command(BaseCommand):
    help = 'Report pipeline failures, recoveries and stalls as GitHub issues'

    def add_arguments(self, parser):
        parser.add_argument('action',
                            choices=['failure', 'recovered', 'heartbeat'])
        parser.add_argument('--workflow', required=True)
        parser.add_argument('--run-url')
        parser.add_argument('--max-age-days', type=int, default=14)

    def handle(self, *args, **options):
        token = require_env('GITHUB_TOKEN')
        repo = require_env('GITHUB_REPOSITORY')
        try:
            dispatch(options, GitHub(token), repo, self.stdout.write)
        except GitHubError as exc:
            raise CommandError(str(exc)) from None
