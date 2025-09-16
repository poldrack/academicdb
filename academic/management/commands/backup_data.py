"""
Django management command to backup user data to JSON files
"""
import json
import os
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers import serialize
from django.contrib.auth import get_user_model
from academic.models import Publication, Funding, Teaching, Talk, Conference, ProfessionalActivity, AuthorCache

User = get_user_model()


class Command(BaseCommand):
    help = 'Backup user data to JSON files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='backups',
            help='Directory to store backup files (default: backups/)'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Backup specific user (by ID). If not provided, backs up all users.'
        )
        parser.add_argument(
            '--format',
            choices=['separate', 'combined'],
            default='separate',
            help='Output format: separate files per model or combined file (default: separate)'
        )
        parser.add_argument(
            '--exclude-cache',
            action='store_true',
            help='Exclude AuthorCache data from backup'
        )

    def handle(self, *args, **options):
        # Create backup directory with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = Path(options['output_dir']) / f'backup_{timestamp}'
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Determine which users to backup
        if options['user_id']:
            try:
                users = [User.objects.get(id=options['user_id'])]
                self.stdout.write(f"Backing up data for user ID: {options['user_id']}")
            except User.DoesNotExist:
                raise CommandError(f"User with ID {options['user_id']} does not exist")
        else:
            users = User.objects.all()
            self.stdout.write(f"Backing up data for {users.count()} users")

        # Models to backup with their related fields
        models_to_backup = [
            ('publications', Publication, 'owner'),
            ('funding', Funding, 'owner'),
            ('teaching', Teaching, 'owner'),
            ('talks', Talk, 'owner'),
            ('conferences', Conference, 'owner'),
            ('professional_activities', ProfessionalActivity, 'owner'),
        ]

        # Add AuthorCache if not excluded (this is global, not user-specific)
        if not options['exclude_cache']:
            models_to_backup.append(('author_cache', AuthorCache, None))

        backup_info = {
            'backup_date': datetime.now().isoformat(),
            'backup_format': options['format'],
            'total_users': len(users),
            'user_ids': [user.id for user in users] if options['user_id'] else 'all',
            'files': [],
            'stats': {}
        }

        if options['format'] == 'combined':
            # Single combined file
            combined_data = {
                'backup_info': backup_info,
                'users': [],
                'data': {}
            }

            # Backup user profiles
            for user in users:
                user_data = {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'middle_name': user.middle_name,
                    'orcid_id': user.orcid_id,
                    'institution': user.institution,
                    'department': user.department,
                    'research_areas': user.research_areas,
                    'preferred_citation_style': user.preferred_citation_style,
                    'email_notifications': user.email_notifications,
                    'scopus_id': user.scopus_id,
                    'pubmed_query': user.pubmed_query,
                    'skip_dois': user.skip_dois,
                    # Address fields
                    'address1': user.address1,
                    'address2': user.address2,
                    'city': user.city,
                    'state': user.state,
                    'zip_code': user.zip_code,
                    'country': user.country,
                    'phone': user.phone,
                    # Website information
                    'websites': user.websites,
                    'last_orcid_sync': user.last_orcid_sync.isoformat() if user.last_orcid_sync else None,
                    'date_joined': user.date_joined.isoformat(),
                }
                combined_data['users'].append(user_data)

            # Backup model data
            for model_name, model_class, owner_field in models_to_backup:
                if owner_field:
                    # User-specific data
                    if options['user_id']:
                        queryset = model_class.objects.filter(**{owner_field + '__id': options['user_id']})
                    else:
                        queryset = model_class.objects.filter(**{owner_field + '__in': users})
                else:
                    # Global data (like AuthorCache)
                    queryset = model_class.objects.all()

                serialized_data = serialize('json', queryset, use_natural_foreign_keys=True, indent=2)
                combined_data['data'][model_name] = json.loads(serialized_data)
                backup_info['stats'][model_name] = queryset.count()
                self.stdout.write(f"  - {model_name}: {queryset.count()} records")

            # Write combined file
            combined_file = backup_dir / 'complete_backup.json'
            with open(combined_file, 'w', encoding='utf-8') as f:
                json.dump(combined_data, f, indent=2, ensure_ascii=False)

            backup_info['files'].append(str(combined_file.name))

        else:
            # Separate files

            # Backup user profiles
            users_data = []
            for user in users:
                user_data = {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'middle_name': user.middle_name,
                    'orcid_id': user.orcid_id,
                    'institution': user.institution,
                    'department': user.department,
                    'research_areas': user.research_areas,
                    'preferred_citation_style': user.preferred_citation_style,
                    'email_notifications': user.email_notifications,
                    'scopus_id': user.scopus_id,
                    'pubmed_query': user.pubmed_query,
                    'skip_dois': user.skip_dois,
                    # Address fields
                    'address1': user.address1,
                    'address2': user.address2,
                    'city': user.city,
                    'state': user.state,
                    'zip_code': user.zip_code,
                    'country': user.country,
                    'phone': user.phone,
                    # Website information
                    'websites': user.websites,
                    'last_orcid_sync': user.last_orcid_sync.isoformat() if user.last_orcid_sync else None,
                    'date_joined': user.date_joined.isoformat(),
                }
                users_data.append(user_data)

            users_file = backup_dir / 'users.json'
            with open(users_file, 'w', encoding='utf-8') as f:
                json.dump(users_data, f, indent=2, ensure_ascii=False)
            backup_info['files'].append('users.json')

            # Backup each model separately
            for model_name, model_class, owner_field in models_to_backup:
                if owner_field:
                    # User-specific data
                    if options['user_id']:
                        queryset = model_class.objects.filter(**{owner_field + '__id': options['user_id']})
                    else:
                        queryset = model_class.objects.filter(**{owner_field + '__in': users})
                else:
                    # Global data (like AuthorCache)
                    queryset = model_class.objects.all()

                if queryset.exists():
                    serialized_data = serialize('json', queryset, use_natural_foreign_keys=True, indent=2)
                    model_file = backup_dir / f'{model_name}.json'

                    with open(model_file, 'w', encoding='utf-8') as f:
                        f.write(serialized_data)

                    backup_info['files'].append(f'{model_name}.json')
                    backup_info['stats'][model_name] = queryset.count()
                    self.stdout.write(f"  - {model_name}: {queryset.count()} records")
                else:
                    backup_info['stats'][model_name] = 0
                    self.stdout.write(f"  - {model_name}: 0 records (skipped)")

        # Write backup metadata
        info_file = backup_dir / 'backup_info.json'
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(backup_info, f, indent=2, ensure_ascii=False)

        # Calculate total backup size
        total_size = sum(f.stat().st_size for f in backup_dir.rglob('*.json'))
        total_size_mb = total_size / (1024 * 1024)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Backup completed successfully!\n"
                f"  Directory: {backup_dir}\n"
                f"  Files: {len(backup_info['files']) + 1} files\n"  # +1 for backup_info.json
                f"  Total size: {total_size_mb:.2f} MB\n"
                f"  Format: {options['format']}"
            )
        )

        # Show restore command
        self.stdout.write(f"\nTo restore this backup, use:")
        self.stdout.write(f"  python manage.py restore_data --backup-dir {backup_dir}")
        if options['user_id']:
            self.stdout.write(f"  (Note: This was a single-user backup for user ID {options['user_id']})")