"""
Django management command to fix existing ORCID connections
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialAccount, SocialToken

User = get_user_model()


class Command(BaseCommand):
    help = 'Fix existing ORCID connections by populating user ORCID fields'

    def handle(self, *args, **options):
        """Fix ORCID connections for users who have SocialAccounts but missing user fields"""
        
        fixed_count = 0
        
        # Find all ORCID social accounts
        orcid_accounts = SocialAccount.objects.filter(provider='orcid')
        
        self.stdout.write(f'Found {orcid_accounts.count()} ORCID social accounts')
        
        for account in orcid_accounts:
            user = account.user
            updated = False
            
            # Set ORCID ID if missing
            if not user.orcid_id:
                user.orcid_id = account.uid
                updated = True
                self.stdout.write(f'Set ORCID ID for {user.username}: {account.uid}')
            
            # Set ORCID token if missing
            if not user.orcid_token:
                token = SocialToken.objects.filter(account=account).first()
                if token:
                    user.orcid_token = token.token
                    updated = True
                    self.stdout.write(f'Set ORCID token for {user.username}')
            
            if updated:
                user.save()
                fixed_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Fixed ORCID connection for {user.username} '
                        f'(is_connected: {user.is_orcid_connected})'
                    )
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Fixed {fixed_count} ORCID connections')
        )