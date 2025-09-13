"""
Diagnostic sync command to track exactly what's happening and where delays occur
"""
import time
import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from academic.models import Publication
import requests

User = get_user_model()

class Command(BaseCommand):
    help = 'Diagnostic sync to identify where the delays are happening'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, default=2)
        parser.add_argument('--limit', type=int, default=5, help='Limit number of DOIs to test')

    def log_with_time(self, message):
        """Print message with timestamp"""
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.stdout.write(f"[{timestamp}] {message}")
        sys.stdout.flush()  # Force immediate output

    def handle(self, *args, **options):
        user_id = options['user_id']
        limit = options['limit']
        
        self.log_with_time(f"Starting diagnostic sync for user {user_id}")
        
        try:
            user = User.objects.get(id=user_id)
            self.log_with_time(f"Found user: {user.display_name}")
        except User.DoesNotExist:
            self.log_with_time(f"ERROR: User {user_id} not found")
            return

        # Check current publication count
        current_count = user.publications.count()
        self.log_with_time(f"Current publication count: {current_count}")

        # Test fetching ORCID data
        self.log_with_time("Fetching ORCID record...")
        start_time = time.time()
        
        try:
            url = f'https://pub.orcid.org/v3.0/{user.orcid_id}/record'
            response = requests.get(url, headers={'Accept': 'application/json'}, timeout=30)
            response.raise_for_status()
            orcid_data = response.json()
            
            elapsed = time.time() - start_time
            self.log_with_time(f"✓ ORCID fetch completed in {elapsed:.2f}s")
            
            # Extract DOIs
            dois = []
            if 'activities-summary' in orcid_data and 'works' in orcid_data['activities-summary']:
                work_groups = orcid_data['activities-summary']['works'].get('group', [])
                for group in work_groups[:limit]:  # Limit for testing
                    work_summary = group.get('work-summary', [{}])[0]
                    external_ids = work_summary.get('external-ids', {}).get('external-id', [])
                    for ext_id in external_ids:
                        if ext_id.get('external-id-type') == 'doi':
                            dois.append(ext_id.get('external-id-value'))
                            break
            
            self.log_with_time(f"Found {len(dois)} DOIs to process (limited to {limit})")
            
        except Exception as e:
            self.log_with_time(f"ERROR fetching ORCID: {e}")
            return

        # Test CrossRef fetching for each DOI
        for i, doi in enumerate(dois, 1):
            self.log_with_time(f"\n--- Processing DOI {i}/{len(dois)}: {doi} ---")
            
            # Check if already exists
            exists = Publication.objects.filter(owner=user, doi=doi).exists()
            if exists:
                self.log_with_time(f"  SKIP: Already exists in database")
                continue
            
            # Fetch from CrossRef
            self.log_with_time(f"  Fetching from CrossRef...")
            start_time = time.time()
            
            try:
                crossref_url = f'https://api.crossref.org/works/{doi}'
                headers = {
                    'User-Agent': 'Academic Database Diagnostic Test',
                    'Accept': 'application/json'
                }
                
                response = requests.get(crossref_url, headers=headers, timeout=10)
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    self.log_with_time(f"  ✓ CrossRef fetch completed in {elapsed:.2f}s")
                    
                    # Parse data
                    work = response.json().get('message', {})
                    title = work.get('title', ['Unknown'])[0]
                    self.log_with_time(f"  Title: {title[:60]}...")
                    
                    # Test database save
                    self.log_with_time(f"  Saving to database...")
                    start_time = time.time()
                    
                    pub = Publication(
                        owner=user,
                        doi=doi,
                        title=title[:100] if len(title) > 100 else title,
                        year=2023,
                        authors=[{'name': 'Test Author'}],
                        source='test'
                    )
                    pub.full_clean()
                    pub.save()
                    
                    elapsed = time.time() - start_time
                    self.log_with_time(f"  ✓ Database save completed in {elapsed:.2f}s")
                    
                else:
                    self.log_with_time(f"  ✗ CrossRef returned {response.status_code}")
                    
            except requests.Timeout:
                self.log_with_time(f"  ✗ CrossRef timeout after 10s")
            except Exception as e:
                self.log_with_time(f"  ✗ Error: {e}")

        # Final check
        final_count = user.publications.count()
        self.log_with_time(f"\n=== SUMMARY ===")
        self.log_with_time(f"Initial publications: {current_count}")
        self.log_with_time(f"Final publications: {final_count}")
        self.log_with_time(f"New publications added: {final_count - current_count}")
        self.log_with_time("Diagnostic sync complete!")