"""
Django management command to synchronize publications from ORCID API
"""
import os
import requests
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.exceptions import ValidationError
from academic.models import Publication, Funding

User = get_user_model()

# Import existing ORCID utilities
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../src'))
from academicdb import orcid

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize publications from ORCID API for authenticated users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync specific user by ID (default: all users with ORCID)'
        )
        parser.add_argument(
            '--orcid-id',
            type=str,
            help='Sync specific user by ORCID ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if recently synced'
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.force = options['force']
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Determine which users to sync
        users_to_sync = self.get_users_to_sync(options)
        
        if not users_to_sync:
            self.stdout.write(self.style.WARNING('No users found to sync'))
            return

        total_synced = 0
        for user in users_to_sync:
            try:
                synced_count = self.sync_user_orcid(user)
                total_synced += synced_count
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Synced {synced_count} publications for {user.display_name}'
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Error syncing {user.display_name}: {str(e)}'
                    )
                )
                logger.exception(f'Error syncing user {user.id}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Total publications synced: {total_synced}'
            )
        )

    def get_users_to_sync(self, options):
        """Get list of users to sync based on command options"""
        if options['user_id']:
            try:
                user = User.objects.get(id=options['user_id'])
                if not user.orcid_id:
                    raise CommandError(f'User {user.display_name} has no ORCID ID')
                return [user]
            except User.DoesNotExist:
                raise CommandError(f'User with ID {options["user_id"]} not found')
        
        elif options['orcid_id']:
            try:
                user = User.objects.get(orcid_id=options['orcid_id'])
                return [user]
            except User.DoesNotExist:
                raise CommandError(f'User with ORCID ID {options["orcid_id"]} not found')
        
        else:
            # Sync all users with ORCID connections
            return User.objects.filter(
                orcid_id__isnull=False,
                orcid_token__isnull=False
            ).exclude(orcid_id='')

    def sync_user_orcid(self, user):
        """Sync publications for a single user from ORCID"""
        if not user.is_orcid_connected:
            self.stdout.write(
                self.style.WARNING(
                    f'User {user.display_name} has no valid ORCID connection'
                )
            )
            return 0

        self.stdout.write(f'Syncing ORCID data for {user.display_name} ({user.orcid_id})')
        
        # Fetch ORCID data
        orcid_data = self.fetch_orcid_data(user)
        if not orcid_data:
            return 0

        # Extract DOIs from ORCID record
        dois = orcid.get_dois_from_orcid_record(orcid_data)
        self.stdout.write(f'Found {len(dois)} publications with DOIs in ORCID')

        if not dois:
            return 0

        # Sync publications (process each individually to avoid transaction failures)
        synced_count = 0
        for doi in dois:
            try:
                if self.sync_publication_from_doi(user, doi):
                    synced_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  Failed to sync {doi}: {str(e)}')
                )
                continue

        # Sync funding sources
        funding_count = self.sync_funding_from_orcid(user, orcid_data)
        self.stdout.write(f'Synced {funding_count} funding records')

        # Update user's last sync time
        if not self.dry_run:
            from django.utils import timezone
            user.last_orcid_sync = timezone.now()
            user.save(update_fields=['last_orcid_sync'])

        return synced_count

    def fetch_orcid_data(self, user):
        """Fetch ORCID data using public API (since OAuth app lacks read permissions)"""
        try:
            # Use public ORCID API (no token required for public data)
            headers = {
                'Accept': 'application/json'
            }
            
            # Use production public API
            base_url = 'https://pub.orcid.org/v3.0'
            url = f'{base_url}/{user.orcid_id}/record'
            
            self.stdout.write(f'Fetching public ORCID data from: {url}')
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract works from the activities summary
            if 'activities-summary' in data and 'works' in data['activities-summary']:
                self.stdout.write(f'Found works data in ORCID record')
                return data  # Return full data structure for compatibility with orcid.get_dois_from_orcid_record
            else:
                self.stdout.write(self.style.WARNING('No works found in ORCID record'))
                return None
            
        except requests.exceptions.RequestException as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Error fetching ORCID data for {user.display_name}: {str(e)}'
                )
            )
            return None

    def fetch_crossref_data(self, doi):
        """Fetch publication details from CrossRef API"""
        try:
            # Use CrossRef API to get publication details
            headers = {
                'User-Agent': 'Academic Database (mailto:support@example.com)',
                'Accept': 'application/json'
            }
            
            url = f'https://api.crossref.org/works/{doi}'
            
            self.stdout.write(f'    Fetching CrossRef data for: {doi}')
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 404:
                self.stdout.write(f'    DOI not found in CrossRef: {doi}')
                return None
                
            response.raise_for_status()
            data = response.json()
            
            # Extract publication data from CrossRef response
            work = data.get('message', {})
            
            # Extract title - ensure we always have a title
            title_list = work.get('title', [])
            title = title_list[0] if title_list else f'Publication with DOI: {doi}'
            
            # Extract publication date
            pub_date = None
            date_parts = work.get('published-print', {}).get('date-parts')
            if not date_parts:
                date_parts = work.get('published-online', {}).get('date-parts')
            if date_parts and len(date_parts) > 0 and len(date_parts[0]) >= 3:
                try:
                    from datetime import date
                    year, month, day = date_parts[0][:3]
                    pub_date = date(year, month, day)
                except (ValueError, IndexError):
                    pass
            
            # Extract year - ensure we always have a year value
            year = None
            if date_parts and len(date_parts) > 0:
                year = date_parts[0][0]
            
            # If no year found, try to extract from other fields
            if not year:
                # Try created date
                created_date = work.get('created', {}).get('date-parts')
                if created_date and len(created_date) > 0:
                    year = created_date[0][0]
            
            # If still no year, use current year as fallback
            if not year:
                from datetime import datetime
                year = datetime.now().year
                self.stdout.write(f'    Warning: No year found for {doi}, using current year {year}')
            
            # Extract journal/publisher name
            pub_name = None
            container_title = work.get('container-title', [])
            if container_title:
                pub_name = container_title[0]
            elif work.get('publisher'):
                pub_name = work.get('publisher')
            
            # Map CrossRef type to our types
            crossref_type = work.get('type', '')
            pub_type_mapping = {
                'journal-article': 'journal-article',
                'proceedings-article': 'conference-paper',
                'book-chapter': 'book-chapter',
                'book': 'book',
                'preprint': 'preprint',
                'dataset': 'dataset',
                'report': 'report',
                'thesis': 'thesis',
            }
            pub_type = pub_type_mapping.get(crossref_type, 'journal-article')
            
            # Extract authors
            authors = []
            author_list = work.get('author', [])
            for author in author_list:
                given = author.get('given', '')
                family = author.get('family', '')
                if given and family:
                    authors.append({'name': f"{given} {family}"})
                elif family:
                    authors.append({'name': family})
            
            # If no authors found, try to get from other sources
            if not authors and work.get('editor'):
                editor_list = work.get('editor', [])
                for editor in editor_list[:3]:  # Limit to first 3 editors
                    given = editor.get('given', '')
                    family = editor.get('family', '')
                    if given and family:
                        authors.append({'name': f"{given} {family} (Ed.)"})
            
            # Ensure we always have at least one author (required by model validation)
            if not authors:
                authors = [{'name': 'Unknown Author'}]
            
            return {
                'title': title,
                'year': year,
                'publication_date': pub_date,
                'publication_name': pub_name,
                'publication_type': pub_type,
                'authors': authors,
                'raw_metadata': work
            }
            
        except requests.exceptions.RequestException as e:
            self.stdout.write(f'    Error fetching CrossRef data for {doi}: {str(e)}')
            return None
        except Exception as e:
            self.stdout.write(f'    Error parsing CrossRef data for {doi}: {str(e)}')
            return None

    def sync_publication_from_doi(self, user, doi):
        """Create or update publication from DOI"""
        doi = doi.lower().strip()
        
        # Check if publication already exists
        existing_pub = Publication.objects.filter(
            owner=user,
            doi=doi
        ).first()

        if existing_pub:
            self.stdout.write(
                f'  Publication already exists: {doi}'
            )
            # Could add logic here to update from external APIs
            return False

        if self.dry_run:
            self.stdout.write(f'  Would create publication: {doi}')
            return True

        # Fetch publication details from CrossRef API
        pub_data = self.fetch_crossref_data(doi)
        if not pub_data:
            self.stdout.write(f'  Could not fetch data for DOI: {doi}')
            return False
            
        try:
            # Ensure we always have authors (required by model validation)
            authors = pub_data.get('authors', [])
            if not authors:
                authors = [{'name': 'Unknown Author'}]
                
            publication = Publication(
                owner=user,
                doi=doi,
                title=pub_data.get('title', f'Publication with DOI: {doi}'),
                year=pub_data.get('year', 2023),
                publication_date=pub_data.get('publication_date'),
                publication_name=pub_data.get('publication_name'),
                publication_type=pub_data.get('publication_type', 'journal-article'),
                source='orcid',
                authors=authors,
                metadata={
                    'orcid_sync': True,
                    'crossref_data': pub_data.get('raw_metadata', {}),
                    'enriched': True
                }
            )
            
            # Validate before saving
            publication.full_clean()
            publication.save()
            
            self.stdout.write(f'  Created publication: {pub_data.get("title", doi)}')
            return True
            
        except ValidationError as e:
            self.stdout.write(
                self.style.ERROR(
                    f'  Validation error for {doi}: {e}'
                )
            )
            return False
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'  Error creating publication {doi}: {str(e)}'
                )
            )
            return False

    def sync_funding_from_orcid(self, user, orcid_data):
        """Sync funding records from ORCID data"""
        if not orcid_data or not orcid_data.get('activities-summary'):
            self.stdout.write('  No ORCID activities data available for funding sync')
            return 0

        # Extract funding data using existing utility function
        try:
            funding_df = orcid.get_orcid_funding(orcid_data)
            if funding_df.empty:
                self.stdout.write('  No funding records found in ORCID')
                return 0
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  Error extracting funding data: {str(e)}')
            )
            return 0

        self.stdout.write(f'  Found {len(funding_df)} funding records in ORCID')
        
        synced_count = 0
        for _, funding_row in funding_df.iterrows():
            try:
                if self.sync_funding_record(user, funding_row):
                    synced_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'  Failed to sync funding "{funding_row["title"]}": {str(e)}'
                    )
                )
                continue

        return synced_count

    def sync_funding_record(self, user, funding_data):
        """Create or update a single funding record"""
        # Extract data from the funding row (from pandas DataFrame)
        title = funding_data.get('title', '').strip()
        organization = funding_data.get('organization', '').strip()
        grant_id = funding_data.get('id', '').strip()
        
        if not title or not organization:
            self.stdout.write('  Skipping funding record with missing title or organization')
            return False

        # Check if funding already exists (by title and organization to avoid duplicates)
        existing_funding = Funding.objects.filter(
            owner=user,
            title=title,
            agency=organization
        ).first()

        if existing_funding:
            self.stdout.write(f'  Funding already exists: {title}')
            return False

        if self.dry_run:
            self.stdout.write(f'  Would create funding: {title} ({organization})')
            return True

        # Parse dates
        start_date = None
        end_date = None
        
        try:
            start_year = funding_data.get('start_date')
            if start_year and start_year != 'present' and str(start_year).strip():
                from datetime import date
                start_date = date(int(start_year), 1, 1)
        except (ValueError, TypeError):
            pass
            
        try:
            end_year = funding_data.get('end_date')
            if end_year and end_year != 'present' and str(end_year).strip():
                from datetime import date
                end_date = date(int(end_year), 12, 31)
        except (ValueError, TypeError):
            pass

        # Create funding record
        try:
            funding = Funding(
                owner=user,
                title=title,
                agency=organization,
                grant_number=grant_id,
                start_date=start_date,
                end_date=end_date,
                source='orcid',
                additional_info={
                    'orcid_sync': True,
                    'url': funding_data.get('url', ''),
                    'role': funding_data.get('role', ''),
                    'original_data': funding_data.to_dict() if hasattr(funding_data, 'to_dict') else dict(funding_data)
                }
            )
            
            # Validate before saving
            funding.full_clean()
            funding.save()
            
            self.stdout.write(f'  Created funding: {title}')
            return True
            
        except ValidationError as e:
            self.stdout.write(
                self.style.ERROR(f'  Validation error for funding "{title}": {e}')
            )
            return False
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  Error creating funding "{title}": {str(e)}')
            )
            return False