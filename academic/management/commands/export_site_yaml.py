"""Export a user's publications as the YAML file used by the static sites."""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from academic.models import AcademicUser
from academic.publish.site_yaml import render_site_yaml, site_records


class Command(BaseCommand):
    help = 'Write the site publications YAML for one user'

    def add_arguments(self, parser):
        parser.add_argument('--orcid-id', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--include-pending', action='store_true')

    def handle(self, *args, **options):
        user = self._get_user(options['orcid_id'])
        records = site_records(user, include_pending=options['include_pending'])
        output = Path(options['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_site_yaml(records), encoding='utf-8')
        self.stdout.write(f'Wrote {len(records)} publications to {output}')

    def _get_user(self, orcid_id):
        try:
            return AcademicUser.objects.get(orcid_id=orcid_id)
        except AcademicUser.DoesNotExist:
            raise CommandError(f'No user with ORCID ID {orcid_id}')
