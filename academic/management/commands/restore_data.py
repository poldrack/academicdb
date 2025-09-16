"""
Django management command to restore user data from JSON backup files
"""
import json
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers import deserialize
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.dateparse import parse_datetime
from academic.models import Publication, Funding, Teaching, Talk, Conference, ProfessionalActivity, AuthorCache

User = get_user_model()


class Command(BaseCommand):
    help = 'Restore user data from JSON backup files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--backup-dir',
            type=str,
            required=True,
            help='Directory containing backup files'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Restore data for specific user only (by ID). Must exist in backup and current DB.'
        )
        parser.add_argument(
            '--merge',
            action='store_true',
            help='Merge with existing data instead of clearing first (use with caution)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be restored without actually doing it'
        )
        parser.add_argument(
            '--exclude-users',
            action='store_true',
            help='Skip user profile restoration (restore only model data)'
        )
        parser.add_argument(
            '--exclude-cache',
            action='store_true',
            help='Skip AuthorCache restoration'
        )

    def handle(self, *args, **options):
        backup_dir = Path(options['backup_dir'])

        if not backup_dir.exists():
            raise CommandError(f"Backup directory does not exist: {backup_dir}")

        # Check for backup info
        info_file = backup_dir / 'backup_info.json'
        if not info_file.exists():
            raise CommandError(f"Backup info file not found: {info_file}")

        # Load backup info
        with open(info_file, 'r', encoding='utf-8') as f:
            backup_info = json.load(f)

        self.stdout.write(f"Loading backup from: {backup_dir}")
        self.stdout.write(f"Backup date: {backup_info.get('backup_date', 'Unknown')}")
        self.stdout.write(f"Backup format: {backup_info.get('backup_format', 'Unknown')}")
        self.stdout.write(f"Original user count: {backup_info.get('total_users', 'Unknown')}")

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Load backup data
        if backup_info.get('backup_format') == 'combined':
            combined_file = backup_dir / 'complete_backup.json'
            if not combined_file.exists():
                raise CommandError(f"Combined backup file not found: {combined_file}")

            with open(combined_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)

            users_data = backup_data.get('users', [])
            model_data = backup_data.get('data', {})
        else:
            # Separate files format
            users_file = backup_dir / 'users.json'
            if users_file.exists() and not options['exclude_users']:
                with open(users_file, 'r', encoding='utf-8') as f:
                    users_data = json.load(f)
            else:
                users_data = []

            # Load model data from separate files
            model_data = {}
            for file_name in backup_info.get('files', []):
                if file_name != 'users.json':
                    model_name = file_name.replace('.json', '')
                    model_file = backup_dir / file_name
                    if model_file.exists():
                        with open(model_file, 'r', encoding='utf-8') as f:
                            model_data[model_name] = json.loads(f.read())

        # Filter by user if specified
        if options['user_id']:
            self.stdout.write(f"Filtering for user ID: {options['user_id']}")
            # Filter users
            users_data = [u for u in users_data if u['id'] == options['user_id']]
            if not users_data:
                raise CommandError(f"User ID {options['user_id']} not found in backup")

        if options['dry_run']:
            self.stdout.write("\n--- DRY RUN SUMMARY ---")
            if not options['exclude_users']:
                self.stdout.write(f"Would restore {len(users_data)} user profiles")
            for model_name, data in model_data.items():
                if options['exclude_cache'] and model_name == 'author_cache':
                    continue
                count = len(data) if isinstance(data, list) else 0
                self.stdout.write(f"Would restore {count} {model_name} records")
            self.stdout.write("--- END DRY RUN ---")
            return

        # Start restoration
        stats = {'users': 0, 'errors': []}

        with transaction.atomic():
            try:
                # Clear existing data if not merging
                if not options['merge']:
                    self.stdout.write("Clearing existing data...")
                    if options['user_id']:
                        # Clear only specific user's data
                        user_to_clear = User.objects.filter(id=options['user_id']).first()
                        if user_to_clear:
                            Publication.objects.filter(owner=user_to_clear).delete()
                            Funding.objects.filter(owner=user_to_clear).delete()
                            Teaching.objects.filter(owner=user_to_clear).delete()
                            Talk.objects.filter(owner=user_to_clear).delete()
                            Conference.objects.filter(owner=user_to_clear).delete()
                            ProfessionalActivity.objects.filter(owner=user_to_clear).delete()
                    else:
                        # Clear all user data
                        Publication.objects.all().delete()
                        Funding.objects.all().delete()
                        Teaching.objects.all().delete()
                        Talk.objects.all().delete()
                        Conference.objects.all().delete()
                        ProfessionalActivity.objects.all().delete()
                        if not options['exclude_cache']:
                            AuthorCache.objects.all().delete()

                # Restore users
                if not options['exclude_users'] and users_data:
                    self.stdout.write(f"Restoring {len(users_data)} users...")
                    for user_data in users_data:
                        try:
                            user, created = User.objects.get_or_create(
                                id=user_data['id'],
                                defaults={
                                    'username': user_data['username'],
                                    'email': user_data['email'],
                                    'first_name': user_data['first_name'],
                                    'last_name': user_data['last_name'],
                                    'date_joined': parse_datetime(user_data['date_joined']) or datetime.now()
                                }
                            )

                            # Update academic fields
                            user.middle_name = user_data.get('middle_name', '')
                            user.orcid_id = user_data.get('orcid_id')
                            user.institution = user_data.get('institution', '')
                            user.department = user_data.get('department', '')
                            user.research_areas = user_data.get('research_areas', [])
                            user.preferred_citation_style = user_data.get('preferred_citation_style', 'apa')
                            user.email_notifications = user_data.get('email_notifications', True)
                            user.scopus_id = user_data.get('scopus_id')
                            user.pubmed_query = user_data.get('pubmed_query')
                            user.skip_dois = user_data.get('skip_dois')

                            # Update address fields
                            user.address1 = user_data.get('address1', '')
                            user.address2 = user_data.get('address2', '')
                            user.city = user_data.get('city', '')
                            user.state = user_data.get('state', '')
                            user.zip_code = user_data.get('zip_code', '')
                            user.country = user_data.get('country', '')
                            user.phone = user_data.get('phone', '')

                            # Update website information
                            user.websites = user_data.get('websites', [])

                            if user_data.get('last_orcid_sync'):
                                user.last_orcid_sync = parse_datetime(user_data['last_orcid_sync'])

                            user.save()
                            stats['users'] += 1

                            if created:
                                self.stdout.write(f"  Created user: {user.username}")
                            else:
                                self.stdout.write(f"  Updated user: {user.username}")

                        except Exception as e:
                            error_msg = f"Failed to restore user {user_data.get('username', 'Unknown')}: {str(e)}"
                            stats['errors'].append(error_msg)
                            self.stdout.write(self.style.ERROR(f"  ERROR: {error_msg}"))

                # Restore model data
                model_mapping = {
                    'publications': Publication,
                    'funding': Funding,
                    'teaching': Teaching,
                    'talks': Talk,
                    'conferences': Conference,
                    'professional_activities': ProfessionalActivity,
                    'author_cache': AuthorCache,
                }

                for model_name, model_class in model_mapping.items():
                    if options['exclude_cache'] and model_name == 'author_cache':
                        continue

                    if model_name in model_data:
                        data = model_data[model_name]
                        if not data:
                            continue

                        self.stdout.write(f"Restoring {len(data)} {model_name} records...")

                        try:
                            # Use Django's deserializer
                            json_data = json.dumps(data) if not isinstance(data, str) else data
                            objects = list(deserialize('json', json_data))

                            restored_count = 0
                            for obj in objects:
                                try:
                                    # Filter by user if specified
                                    if options['user_id'] and hasattr(obj.object, 'owner'):
                                        if obj.object.owner_id != options['user_id']:
                                            continue

                                    obj.save()
                                    restored_count += 1
                                except Exception as e:
                                    error_msg = f"Failed to restore {model_name} object: {str(e)}"
                                    stats['errors'].append(error_msg)
                                    self.stdout.write(self.style.WARNING(f"    Warning: {error_msg}"))

                            stats[model_name] = restored_count
                            self.stdout.write(f"  Successfully restored {restored_count} {model_name} records")

                        except Exception as e:
                            error_msg = f"Failed to restore {model_name}: {str(e)}"
                            stats['errors'].append(error_msg)
                            self.stdout.write(self.style.ERROR(f"  ERROR: {error_msg}"))

                # Success summary
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n✓ Restore completed!\n"
                        f"  Users restored: {stats['users']}\n"
                        f"  Publications: {stats.get('publications', 0)}\n"
                        f"  Funding: {stats.get('funding', 0)}\n"
                        f"  Teaching: {stats.get('teaching', 0)}\n"
                        f"  Talks: {stats.get('talks', 0)}\n"
                        f"  Conferences: {stats.get('conferences', 0)}\n"
                        f"  Professional Activities: {stats.get('professional_activities', 0)}\n"
                        + (f"  Author Cache: {stats.get('author_cache', 0)}\n" if not options['exclude_cache'] else "")
                        + (f"  Errors: {len(stats['errors'])}\n" if stats['errors'] else "")
                    )
                )

                if stats['errors']:
                    self.stdout.write(self.style.WARNING("\nErrors encountered during restore:"))
                    for error in stats['errors']:
                        self.stdout.write(f"  - {error}")

            except Exception as e:
                raise CommandError(f"Restore failed: {str(e)}")