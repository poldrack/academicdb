"""Apply a decided review PR (from a dispatch) and republish both sites."""
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from academic.management.commands.publish_sites import (
    PIPELINE_ERRORS, get_user,
)
from academic.models import ReviewBatch
from academic.publish.publish import PublishConfig, run_process_review


class Command(BaseCommand):
    help = 'Process the review batch for one PR, then publish both sites'

    def add_arguments(self, parser):
        parser.add_argument('--orcid-id', required=True)
        parser.add_argument('--pr', type=int, required=True)

    def handle(self, *args, **options):
        config = PublishConfig.from_env(os.environ)
        user = get_user(options['orcid_id'])
        number = options['pr']
        batch = ReviewBatch.objects.filter(owner=user, pr_number=number).first()
        if batch is None:
            self.stdout.write(f'No review batch for PR {number}')
            return
        try:
            run_process_review(user, batch, config, timezone.now(),
                               log=self.stdout.write)
        except PIPELINE_ERRORS as exc:
            raise CommandError(str(exc)) from None
