"""
Django management command to export publications to various formats (JSON, YAML, CSV)

This command exports publication data for use in external systems such as static websites.
It respects user data isolation and provides flexible filtering and formatting options.
"""
import json
import csv
import sys
from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from academic.models import Publication, Link

User = get_user_model()


class Command(BaseCommand):
    help = 'Export publications to JSON, YAML, or CSV format for external use (e.g., static website generation)'

    def add_arguments(self, parser):
        # Output format
        parser.add_argument(
            '--format',
            choices=['json', 'yaml', 'csv'],
            default='json',
            help='Output format (default: json)'
        )

        # Output destination
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path. If not specified, prints to stdout.'
        )

        # User filtering options
        parser.add_argument(
            '--user-id',
            type=int,
            help='Export publications for specific user ID'
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Export publications for specific username'
        )
        parser.add_argument(
            '--orcid-id',
            type=str,
            help='Export publications for specific ORCID ID'
        )
        parser.add_argument(
            '--all-users',
            action='store_true',
            help='Export publications for ALL users (default: requires one of --user-id, --username, or --orcid-id)'
        )

        # Data filtering options
        parser.add_argument(
            '--year-from',
            type=int,
            help='Filter publications from this year onwards'
        )
        parser.add_argument(
            '--year-to',
            type=int,
            help='Filter publications up to this year'
        )
        parser.add_argument(
            '--publication-type',
            type=str,
            help='Filter by publication type (e.g., journal-article, conference-paper)'
        )
        parser.add_argument(
            '--exclude-ignored',
            action='store_true',
            help='Exclude publications marked as ignored'
        )
        parser.add_argument(
            '--preprints-only',
            action='store_true',
            help='Export only preprints'
        )
        parser.add_argument(
            '--exclude-preprints',
            action='store_true',
            help='Exclude preprints from export'
        )

        # Field selection
        parser.add_argument(
            '--fields',
            type=str,
            help='Comma-separated list of fields to include (default: all fields). '
                 'Example: title,year,doi,authors,publication_name'
        )
        parser.add_argument(
            '--exclude-metadata',
            action='store_true',
            help='Exclude the metadata JSONB field from export (reduces size)'
        )
        parser.add_argument(
            '--exclude-edit-history',
            action='store_true',
            help='Exclude edit tracking fields (manual_edits, edit_history)'
        )

        # Formatting options
        parser.add_argument(
            '--pretty',
            action='store_true',
            help='Pretty-print JSON output with indentation'
        )
        parser.add_argument(
            '--include-user-info',
            action='store_true',
            help='Include user information with each publication'
        )

    def handle(self, *args, **options):
        # Determine which user(s) to export
        user_filter = self._get_user_filter(options)

        # Get publications queryset
        publications = Publication.objects.select_related('owner').filter(**user_filter)

        # Apply additional filters
        publications = self._apply_filters(publications, options)

        # Order by year (descending), then by publication date
        publications = publications.order_by('-year', '-publication_date', 'title')

        if not publications.exists():
            self.stdout.write(self.style.WARNING('No publications found matching the criteria'))
            return

        self.stdout.write(f'Found {publications.count()} publications to export')

        # Export based on format
        if options['format'] == 'json':
            output = self._export_json(publications, options)
        elif options['format'] == 'yaml':
            output = self._export_yaml(publications, options)
        elif options['format'] == 'csv':
            output = self._export_csv(publications, options)

        # Write to file or stdout
        if options['output']:
            output_path = Path(options['output'])
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if options['format'] == 'csv':
                # CSV is already written to file
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully exported {publications.count()} publications to {output_path}')
                )
            else:
                output_path.write_text(output, encoding='utf-8')
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully exported {publications.count()} publications to {output_path}')
                )
        else:
            # Print to stdout
            self.stdout.write(output)

    def _get_user_filter(self, options):
        """Determine which user(s) to filter by"""
        if options['all_users']:
            return {}  # No filter, all users

        if options['user_id']:
            try:
                user = User.objects.get(id=options['user_id'])
                self.stdout.write(f"Exporting publications for user: {user.get_full_name()} (ID: {user.id})")
                return {'owner': user}
            except User.DoesNotExist:
                raise CommandError(f"User with ID {options['user_id']} does not exist")

        if options['username']:
            try:
                user = User.objects.get(username=options['username'])
                self.stdout.write(f"Exporting publications for user: {user.get_full_name()} (username: {user.username})")
                return {'owner': user}
            except User.DoesNotExist:
                raise CommandError(f"User with username '{options['username']}' does not exist")

        if options['orcid_id']:
            try:
                user = User.objects.get(orcid_id=options['orcid_id'])
                self.stdout.write(f"Exporting publications for user: {user.get_full_name()} (ORCID: {user.orcid_id})")
                return {'owner': user}
            except User.DoesNotExist:
                raise CommandError(f"User with ORCID ID '{options['orcid_id']}' does not exist")

        raise CommandError(
            'You must specify either --user-id, --username, --orcid-id, or --all-users'
        )

    def _apply_filters(self, queryset, options):
        """Apply additional filters to the queryset"""
        if options['year_from']:
            queryset = queryset.filter(year__gte=options['year_from'])

        if options['year_to']:
            queryset = queryset.filter(year__lte=options['year_to'])

        if options['publication_type']:
            queryset = queryset.filter(publication_type=options['publication_type'])

        if options['exclude_ignored']:
            queryset = queryset.filter(is_ignored=False)

        if options['preprints_only']:
            queryset = queryset.filter(is_preprint=True)

        if options['exclude_preprints']:
            queryset = queryset.filter(is_preprint=False)

        return queryset

    def _serialize_publication(self, pub, options):
        """Convert a publication to a dictionary for export"""
        # Determine which fields to include
        if options['fields']:
            fields = [f.strip() for f in options['fields'].split(',')]
        else:
            # Default: all fields
            fields = None

        data = {}

        # Always include ID
        data['id'] = pub.id

        # Helper to check if field should be included
        def should_include(field_name):
            if fields is None:
                return True
            return field_name in fields

        # Basic fields
        if should_include('doi'):
            data['doi'] = pub.doi
        if should_include('title'):
            data['title'] = pub.title
        if should_include('year'):
            data['year'] = pub.year
        if should_include('publication_date'):
            data['publication_date'] = pub.publication_date.isoformat() if pub.publication_date else None
        if should_include('publication_name'):
            data['publication_name'] = pub.publication_name
        if should_include('publication_type'):
            data['publication_type'] = pub.publication_type
        if should_include('is_preprint'):
            data['is_preprint'] = pub.is_preprint
        if should_include('is_ignored'):
            data['is_ignored'] = pub.is_ignored
        if should_include('ignore_reason'):
            data['ignore_reason'] = pub.ignore_reason
        if should_include('volume'):
            data['volume'] = pub.volume
        if should_include('page_range'):
            data['page_range'] = pub.page_range
        if should_include('source'):
            data['source'] = pub.source

        # JSONB fields
        if should_include('authors'):
            data['authors'] = pub.authors
        if should_include('identifiers'):
            data['identifiers'] = pub.identifiers
        if should_include('links'):
            data['links'] = dict(pub.links) if pub.links else {}

            # Include Link model records (Code, Data, OSF, etc.)
            link_records = Link.get_links_for_publication(pub)
            if link_records.exists():
                data['links']['resources'] = [
                    {
                        'type': link.type,
                        'url': link.url,
                        'title': link.title,
                    }
                    for link in link_records
                ]

        # Optionally exclude metadata
        if should_include('metadata') and not options['exclude_metadata']:
            data['metadata'] = pub.metadata

        # Optionally exclude edit tracking
        if not options['exclude_edit_history']:
            if should_include('manual_edits'):
                data['manual_edits'] = pub.manual_edits
            if should_include('edit_history'):
                data['edit_history'] = pub.edit_history
            if should_include('manually_edited_at'):
                data['manually_edited_at'] = pub.manually_edited_at.isoformat() if pub.manually_edited_at else None

        # Timestamps
        if should_include('created_at'):
            data['created_at'] = pub.created_at.isoformat()
        if should_include('updated_at'):
            data['updated_at'] = pub.updated_at.isoformat()
        if should_include('last_api_sync'):
            data['last_api_sync'] = pub.last_api_sync.isoformat() if pub.last_api_sync else None

        # Optionally include user information
        if options['include_user_info']:
            data['user'] = {
                'id': pub.owner.id,
                'username': pub.owner.username,
                'full_name': pub.owner.get_full_name(),
                'orcid_id': pub.owner.orcid_id,
                'institution': pub.owner.institution,
            }

        return data

    def _export_json(self, publications, options):
        """Export publications to JSON format"""
        data = {
            'export_info': {
                'export_date': datetime.now().isoformat(),
                'total_publications': publications.count(),
                'format': 'json',
            },
            'publications': [
                self._serialize_publication(pub, options)
                for pub in publications
            ]
        }

        if options['pretty']:
            return json.dumps(data, indent=2, ensure_ascii=False)
        else:
            return json.dumps(data, ensure_ascii=False)

    def _export_yaml(self, publications, options):
        """Export publications to YAML format"""
        try:
            import yaml
        except ImportError:
            raise CommandError(
                'PyYAML is required for YAML export. Install it with: pip install PyYAML'
            )

        data = {
            'export_info': {
                'export_date': datetime.now().isoformat(),
                'total_publications': publications.count(),
                'format': 'yaml',
            },
            'publications': [
                self._serialize_publication(pub, options)
                for pub in publications
            ]
        }

        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def _export_csv(self, publications, options):
        """Export publications to CSV format"""
        if not options['output']:
            raise CommandError('CSV export requires --output parameter (cannot write to stdout)')

        output_path = Path(options['output'])

        # Determine fields for CSV
        if options['fields']:
            csv_fields = ['id'] + [f.strip() for f in options['fields'].split(',')]
        else:
            # Default CSV fields (excluding complex JSONB fields)
            csv_fields = [
                'id', 'doi', 'title', 'year', 'publication_date', 'publication_name',
                'publication_type', 'is_preprint', 'is_ignored', 'volume', 'page_range',
                'source', 'created_at', 'updated_at'
            ]

            if options['include_user_info']:
                csv_fields.extend(['user_id', 'username', 'user_full_name', 'user_orcid'])

        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_fields, extrasaction='ignore')
            writer.writeheader()

            for pub in publications:
                data = self._serialize_publication(pub, options)

                # Flatten user info for CSV
                if options['include_user_info'] and 'user' in data:
                    data['user_id'] = data['user']['id']
                    data['username'] = data['user']['username']
                    data['user_full_name'] = data['user']['full_name']
                    data['user_orcid'] = data['user']['orcid_id']
                    del data['user']

                # Remove complex fields that don't fit in CSV
                for key in list(data.keys()):
                    if isinstance(data[key], (dict, list)):
                        if key == 'authors':
                            # Convert authors list to comma-separated string
                            data['authors'] = '; '.join([
                                author.get('name', '') or
                                f"{author.get('given', '')} {author.get('family', '')}".strip()
                                for author in data[key]
                            ])
                        else:
                            del data[key]

                writer.writerow(data)

        return ''  # CSV is written directly to file
