"""
Django management command to set up ORCID authentication properly
"""
import os
from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp


class Command(BaseCommand):
    help = 'Set up ORCID authentication configuration'

    def handle(self, *args, **options):
        # Check environment variables
        client_id = os.getenv('ORCID_CLIENT_ID')
        client_secret = os.getenv('ORCID_CLIENT_SECRET')
        
        if not client_id:
            self.stdout.write(self.style.ERROR('ORCID_CLIENT_ID not set'))
            return
            
        if not client_secret:
            self.stdout.write(self.style.ERROR('ORCID_CLIENT_SECRET not set'))
            return
            
        # Clean up any existing ORCID apps
        existing_count = SocialApp.objects.filter(provider='orcid').count()
        if existing_count > 0:
            SocialApp.objects.filter(provider='orcid').delete()
            self.stdout.write(f'Removed {existing_count} existing ORCID SocialApp(s)')
        
        # Get or create the site
        site, created = Site.objects.get_or_create(
            pk=1,
            defaults={
                'domain': '127.0.0.1:8000',
                'name': 'Academic Database (Local)'
            }
        )

        if not created:
            site.domain = '127.0.0.1:8000'
            site.name = 'Academic Database (Local)'
            site.save()
            
        self.stdout.write(f'Site configured: {site.domain}')
        
        # Create ORCID SocialApp
        app = SocialApp.objects.create(
            provider='orcid',
            name='ORCID',
            client_id=client_id,
            secret=client_secret,
        )
        
        # Associate with site
        app.sites.add(site)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ ORCID SocialApp created successfully!\n'
                f'   Provider: {app.provider}\n'
                f'   Client ID: {app.client_id}\n'
                f'   Sites: {", ".join([s.domain for s in app.sites.all()])}'
            )
        )
        
        # Verify no duplicates
        total_orcid = SocialApp.objects.filter(provider='orcid').count()
        if total_orcid != 1:
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  Expected 1 ORCID app, found {total_orcid}'
                )
            )
        else:
            self.stdout.write('✅ Verification passed: exactly 1 ORCID app exists')
            
        self.stdout.write(
            '\n🚀 Next steps:\n'
            '   1. Restart your Django server\n'
            '   2. Go to http://127.0.0.1:8000/accounts/login/\n'
            '   3. Click "ORCID" to test authentication\n'
            '   4. Make sure your ORCID app has redirect URI:\n'
            '      http://127.0.0.1:8000/accounts/orcid/login/callback/'
        )