from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from academic.models import Teaching, Talk, Conference
import csv
import os
from datetime import datetime

User = get_user_model()


class Command(BaseCommand):
    help = 'Import teaching, talks, and conferences from CSV files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to import data for',
            required=True
        )
        parser.add_argument(
            '--teaching-file',
            type=str,
            help='Path to teaching CSV file',
        )
        parser.add_argument(
            '--talks-file',
            type=str,
            help='Path to talks CSV file',
        )
        parser.add_argument(
            '--conferences-file',
            type=str,
            help='Path to conferences CSV file',
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing data before importing',
        )

    def handle(self, *args, **options):
        try:
            user = User.objects.get(id=options['user_id'])
        except User.DoesNotExist:
            raise CommandError(f'User with ID {options["user_id"]} does not exist')

        self.stdout.write(
            self.style.SUCCESS(f'Starting import for user: {user.display_name}')
        )

        # Clear existing data if requested
        if options['clear_existing']:
            self.stdout.write('Clearing existing data...')
            Teaching.objects.filter(owner=user).delete()
            Talk.objects.filter(owner=user).delete()
            Conference.objects.filter(owner=user).delete()

        # Import teaching
        if options['teaching_file']:
            self.import_teaching(user, options['teaching_file'])

        # Import talks
        if options['talks_file']:
            self.import_talks(user, options['talks_file'])

        # Import conferences
        if options['conferences_file']:
            self.import_conferences(user, options['conferences_file'])

        self.stdout.write(
            self.style.SUCCESS('Import completed successfully!')
        )

    def import_teaching(self, user, file_path):
        """Import teaching data from CSV file"""
        if not os.path.exists(file_path):
            raise CommandError(f'Teaching file not found: {file_path}')

        self.stdout.write(f'Importing teaching data from {file_path}...')
        
        created_count = 0
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                # Map CSV level to model choices
                level_mapping = {
                    'undergraduate': 'undergraduate',
                    'graduate': 'graduate',
                    'postdoc': 'postdoc',
                    'professional': 'professional',
                }
                
                level = level_mapping.get(
                    row['type'].lower().strip(), 
                    'undergraduate'
                )
                
                teaching = Teaching.objects.create(
                    owner=user,
                    name=row['name'].strip(),
                    level=level,
                    source='import'
                )
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Created {created_count} teaching records')
        )

    def import_talks(self, user, file_path):
        """Import talks data from CSV file"""
        if not os.path.exists(file_path):
            raise CommandError(f'Talks file not found: {file_path}')

        self.stdout.write(f'Importing talks data from {file_path}...')
        
        created_count = 0
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                # Parse year
                try:
                    year = int(row['year'].strip())
                except (ValueError, KeyError):
                    self.stdout.write(
                        self.style.WARNING(f'Skipping row with invalid year: {row}')
                    )
                    continue

                place = row['place'].strip()
                # Check for virtual indicator (asterisk at end)
                virtual = place.endswith('*')
                if virtual:
                    place = place.rstrip('*').strip()

                talk = Talk.objects.create(
                    owner=user,
                    year=year,
                    place=place,
                    virtual=virtual,
                    invited=True,  # Assume talks in list are invited
                    source='import'
                )
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Created {created_count} talk records')
        )

    def import_conferences(self, user, file_path):
        """Import conference data from CSV file"""
        if not os.path.exists(file_path):
            raise CommandError(f'Conferences file not found: {file_path}')

        self.stdout.write(f'Importing conferences data from {file_path}...')
        
        created_count = 0
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                # Parse year
                try:
                    year = int(row['year'].strip())
                except (ValueError, KeyError):
                    self.stdout.write(
                        self.style.WARNING(f'Skipping row with invalid year: {row}')
                    )
                    continue

                # Extract required fields
                title = row['title'].strip()
                authors = row['authors'].strip()
                location = row['location'].strip()
                
                # Optional fields
                month = row.get('month', '').strip()
                link = row.get('link', '').strip()

                conference = Conference.objects.create(
                    owner=user,
                    title=title,
                    authors=authors,
                    year=year,
                    location=location,
                    month=month,
                    link=link,
                    presentation_type='talk',  # Default to talk
                    source='import'
                )
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Created {created_count} conference records')
        )