"""
Django management command to synchronize publications from ORCID API
"""
import os
import re
import requests
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.exceptions import ValidationError
from academic.models import Publication, Funding, ProfessionalActivity, APIRecordCache

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

        # Sync professional activities
        activities_count = self.sync_professional_activities_from_orcid(user, orcid_data)
        self.stdout.write(f'Synced {activities_count} professional activities')

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
        """Fetch publication details from CrossRef API with caching"""
        try:
            # First check if we have this record in cache
            cached_record = APIRecordCache.get_cached_record('crossref', doi=doi)

            if cached_record and cached_record.raw_data:
                self.stdout.write(f'    Found CrossRef data in cache for: {doi}')
                work = cached_record.raw_data
            else:
                # Not in cache, fetch from API
                headers = {
                    'User-Agent': 'Academic Database (mailto:support@example.com)',
                    'Accept': 'application/json'
                }

                url = f'https://api.crossref.org/works/{doi}'

                self.stdout.write(f'    Fetching CrossRef data from API for: {doi}')

                response = requests.get(url, headers=headers, timeout=10)

                if response.status_code == 404:
                    self.stdout.write(f'    DOI not found in CrossRef: {doi}')
                    return None

                response.raise_for_status()
                data = response.json()

                # Extract publication data from CrossRef response
                work = data.get('message', {})

                # Cache the record for future use
                APIRecordCache.cache_record(
                    api_source='crossref',
                    api_id=doi,
                    raw_data=work,
                    doi=doi
                )
                self.stdout.write(f'    Cached CrossRef data for: {doi}')
            
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
        # Replace repeated slashes with single slash
        doi = re.sub(r'/+', '/', doi)

        # Check if DOI should be skipped based on user preferences
        skip_dois = user.get_skip_dois_list()
        if doi in skip_dois:
            self.stdout.write(f'  Skipping DOI (in user skip list): {doi}')
            return False

        # Check if publication already exists
        existing_pub = Publication.objects.filter(
            owner=user,
            doi=doi
        ).first()

        if existing_pub:
            self.stdout.write(
                f'  Publication already exists: {doi}'
            )
            # Check if we have cached CrossRef data that could enrich this publication
            cached_record = APIRecordCache.get_cached_record('crossref', doi=doi)
            if cached_record and cached_record.raw_data:
                self.stdout.write(f'    Found cached CrossRef data for existing publication: {doi}')
                # Could add logic here to update existing publication with cached data
                # For now, just acknowledge that the cache is available
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

        # Get funding groups from activities summary
        funding_groups = orcid_data.get('activities-summary', {}).get('fundings', {}).get('group', [])
        if not funding_groups:
            self.stdout.write('  No funding records found in ORCID')
            return 0

        self.stdout.write(f'  Found {len(funding_groups)} funding records in ORCID')
        
        synced_count = 0
        for funding_group in funding_groups:
            try:
                # Get the first funding summary from the group
                funding_summary = funding_group.get('funding-summary', [])
                if not funding_summary:
                    continue
                    
                summary = funding_summary[0]
                put_code = summary.get('put-code')
                
                if put_code:
                    # Fetch detailed funding record using put-code
                    detailed_funding = self.fetch_detailed_funding_record(user.orcid_id, put_code)
                    if detailed_funding:
                        if self.sync_funding_record(user, detailed_funding):
                            synced_count += 1
                        
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  Failed to sync funding record: {str(e)}')
                )
                continue

        return synced_count

    def fetch_detailed_funding_record(self, orcid_id, put_code):
        """Fetch detailed funding record from ORCID API using put-code"""
        try:
            headers = {'Accept': 'application/json'}
            base_url = 'https://pub.orcid.org/v3.0'
            url = f'{base_url}/{orcid_id}/funding/{put_code}'
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  Failed to fetch detailed funding record {put_code}: {str(e)}')
            )
            return None

    def sync_funding_record(self, user, funding_data):
        """Create or update a single funding record"""
        # Handle both DataFrame (old) and detailed ORCID JSON (new) formats
        if hasattr(funding_data, 'get') and 'title' in funding_data and isinstance(funding_data.get('title'), dict):
            # New format: detailed ORCID JSON
            # Safely extract title with None checks
            title_obj = funding_data.get('title') or {}
            title_inner = title_obj.get('title') or {}
            title = (title_inner.get('value') or '').strip()

            # Safely extract organization with None checks
            org_obj = funding_data.get('organization') or {}
            organization = (org_obj.get('name') or '').strip()
            
            # Extract grant number from external-ids
            grant_id = ''
            external_ids_obj = funding_data.get('external-ids') or {}
            external_ids = external_ids_obj.get('external-id') or []
            if external_ids and len(external_ids) > 0:
                first_id = external_ids[0] or {}
                grant_id = (first_id.get('external-id-value') or '').strip()

            # Extract URL from main url field (not external-ids)
            url_obj = funding_data.get('url') or {}
            url = (url_obj.get('value') or '').strip() if url_obj else ''

            # Extract role from organization-defined-type
            role_obj = funding_data.get('organization-defined-type') or {}
            role = (role_obj.get('value') or '').strip() if role_obj else ''
            
            # Extract dates with full precision
            start_date = None
            end_date = None
            
            start_date_obj = funding_data.get('start-date')
            if start_date_obj:
                try:
                    from datetime import date
                    year_obj = start_date_obj.get('year') or {}
                    month_obj = start_date_obj.get('month') or {}
                    day_obj = start_date_obj.get('day') or {}

                    year_val = year_obj.get('value') if year_obj else None
                    month_val = month_obj.get('value') if month_obj else None
                    day_val = day_obj.get('value') if day_obj else None

                    year = int(year_val) if year_val is not None else 0
                    month = int(month_val) if month_val is not None else 1
                    day = int(day_val) if day_val is not None else 1

                    if year > 0:
                        start_date = date(year, month, day)
                except (ValueError, TypeError) as e:
                    self.stdout.write(f'  Warning: Could not parse start date: {e}')
            
            end_date_obj = funding_data.get('end-date')
            if end_date_obj:
                try:
                    from datetime import date
                    year_obj = end_date_obj.get('year') or {}
                    month_obj = end_date_obj.get('month') or {}
                    day_obj = end_date_obj.get('day') or {}

                    year_val = year_obj.get('value') if year_obj else None
                    month_val = month_obj.get('value') if month_obj else None
                    day_val = day_obj.get('value') if day_obj else None

                    year = int(year_val) if year_val is not None else 0
                    month = int(month_val) if month_val is not None else 12
                    day = int(day_val) if day_val is not None else 31

                    if year > 0:
                        end_date = date(year, month, day)
                except (ValueError, TypeError) as e:
                    self.stdout.write(f'  Warning: Could not parse end date: {e}')
            
            # Extract amount if available
            amount = None
            amount_obj = funding_data.get('amount')
            if amount_obj:
                try:
                    amount_val = amount_obj.get('value') if amount_obj else None
                    if amount_val is not None:
                        amount = float(amount_val)
                except (ValueError, TypeError) as e:
                    self.stdout.write(f'  Warning: Could not parse amount: {e}')
                    
        else:
            # Old format: pandas DataFrame row
            title = funding_data.get('title', '').strip()
            organization = funding_data.get('organization', '').strip()
            grant_id = funding_data.get('id', '').strip()
            url = funding_data.get('url', '')
            role = funding_data.get('role', '')
            amount = None
            
            # Parse dates (old format uses just years)
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

        # Create funding record
        try:
            funding = Funding(
                owner=user,
                title=title,
                agency=organization,
                grant_number=grant_id,
                amount=amount,
                start_date=start_date,
                end_date=end_date,
                source='orcid',
                additional_info={
                    'orcid_sync': True,
                    'url': url,
                    'role': role,
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

    def sync_professional_activities_from_orcid(self, user, orcid_data):
        """Sync professional activities from ORCID record"""
        if not orcid_data:
            return 0

        synced_count = 0

        # Process different activity types
        activities_to_sync = [
            ('employments', 'employment'),
            ('educations', 'education'),
            ('qualifications', 'qualification'),
            ('invited-positions', 'invited_position'),
            ('distinctions', 'distinction'),
            ('memberships', 'membership'),
            ('services', 'service'),
        ]

        for orcid_key, activity_type in activities_to_sync:
            activities = self.extract_activities_from_orcid(orcid_data, orcid_key)

            for activity_data in activities:
                try:
                    if self.create_or_update_professional_activity(user, activity_data, activity_type):
                        synced_count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  Failed to sync professional activity: {str(e)}')
                    )
                    continue

        return synced_count

    def extract_activities_from_orcid(self, orcid_data, activity_type):
        """Extract professional activities of a specific type from ORCID data"""
        activities = []

        try:
            # Navigate to activities-summary in ORCID data
            activities_summary = orcid_data.get('activities-summary', {})

            # Get the specific activity type section
            activity_group = activities_summary.get(activity_type, {})

            # Handle different ORCID response structures
            if 'affiliation-group' in activity_group:
                # For employments, educations, etc.
                for group in activity_group.get('affiliation-group', []):
                    for summary in group.get('summaries', []):
                        activity = summary.get(activity_type.rstrip('s') + '-summary', {})
                        if activity:
                            activities.append(activity)
            elif 'group' in activity_group:
                # For memberships, services, etc.
                for group in activity_group.get('group', []):
                    for summary in group.get('summaries', []):
                        activity = summary.get(activity_type.rstrip('s') + '-summary', {})
                        if activity:
                            activities.append(activity)
            elif activity_type in ['employments', 'educations']:
                # Alternative structure for some records
                employment_summary = activity_group.get('employment-summary', [])
                education_summary = activity_group.get('education-summary', [])
                activities.extend(employment_summary)
                activities.extend(education_summary)

        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'  Could not extract {activity_type}: {str(e)}')
            )

        return activities

    def create_or_update_professional_activity(self, user, activity_data, activity_type):
        """Create or update a professional activity from ORCID data"""
        if self.dry_run:
            self.stdout.write(f'  [DRY RUN] Would create/update {activity_type} activity')
            return True

        from django.utils import timezone

        try:
            # Extract key fields from ORCID data
            put_code = activity_data.get('put-code')

            # Organization details
            organization = activity_data.get('organization', {})
            org_name = organization.get('name', 'Unknown Organization')

            # Address/location
            address = organization.get('address', {})
            city = address.get('city')
            region = address.get('region')
            country = address.get('country')

            # Role/title details
            role_title = activity_data.get('role-title', '')
            department = activity_data.get('department-name', '')

            # Date handling
            start_date = self.parse_orcid_date(activity_data.get('start-date'))
            end_date = self.parse_orcid_date(activity_data.get('end-date'))

            # URL
            url = activity_data.get('url', {}).get('value') if activity_data.get('url') else None

            # Visibility
            visibility = activity_data.get('visibility', 'public')

            # Path for API reference
            path = activity_data.get('path')

            # Check if activity already exists
            activity, created = ProfessionalActivity.objects.update_or_create(
                owner=user,
                orcid_put_code=str(put_code) if put_code else None,
                defaults={
                    'activity_type': activity_type,
                    'title': role_title or activity_type.replace('_', ' ').title(),
                    'organization': org_name,
                    'department': department,
                    'role': role_title,
                    'start_date': start_date,
                    'end_date': end_date,
                    'city': city,
                    'region': region,
                    'country': country,
                    'url': url,
                    'orcid_path': path,
                    'orcid_visibility': visibility,
                    'orcid_data': activity_data,
                    'source': 'orcid',
                    'last_synced': timezone.now(),
                }
            )

            if created:
                self.stdout.write(f'  Created {activity_type}: {role_title} at {org_name}')
            else:
                self.stdout.write(f'  Updated {activity_type}: {role_title} at {org_name}')

            return True

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  Error creating/updating activity: {str(e)}')
            )
            return False

    def parse_orcid_date(self, date_data):
        """Parse ORCID date format to Python date object"""
        if not date_data:
            return None

        try:
            year_obj = date_data.get('year', {})
            month_obj = date_data.get('month', {})
            day_obj = date_data.get('day', {})

            year = year_obj.get('value') if year_obj else None
            month = month_obj.get('value') if month_obj else None
            day = day_obj.get('value') if day_obj else None

            if year:
                # Convert string values to integers
                year = int(year)
                # Use 1 as default for missing month/day
                month = int(month) if month is not None else 1
                day = int(day) if day is not None else 1

                from datetime import date
                return date(year, month, day)
        except (ValueError, TypeError, AttributeError) as e:
            self.stdout.write(f'    Warning: Could not parse date {date_data}: {e}')
            pass

        return None