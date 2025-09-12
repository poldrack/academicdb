from django.dispatch import receiver
from allauth.socialaccount.signals import pre_social_login, social_account_added
from allauth.socialaccount.models import SocialAccount, SocialToken
import logging

logger = logging.getLogger(__name__)


@receiver(pre_social_login)
def populate_user_from_orcid(sender, request, sociallogin, **kwargs):
    """
    Pre-process social login to extract ORCID data
    """
    if sociallogin.account.provider == 'orcid':
        user = sociallogin.user
        
        # Extract ORCID ID from the socialaccount UID
        orcid_id = sociallogin.account.uid
        if orcid_id:
            user.orcid_id = orcid_id
            print(f"[SIGNAL] Set ORCID ID {orcid_id} for user {user.email}")


@receiver(social_account_added)
def social_account_added_handler(sender, request, sociallogin, **kwargs):
    """
    Handle when a social account is successfully added
    """
    if sociallogin.account.provider == 'orcid':
        user = sociallogin.user
        social_account = sociallogin.account
        
        print(f"[SIGNAL] Processing ORCID connection for {user.email}")
        
        # Ensure ORCID ID is set
        if not user.orcid_id:
            user.orcid_id = social_account.uid
            print(f"[SIGNAL] Set ORCID ID from social account: {social_account.uid}")
        
        # Store ORCID token for API access - need to wait for token to be created
        # This happens after the social_account_added signal, so we'll handle it differently
        
        # Save the user with ORCID ID
        user.save()
        print(f"[SIGNAL] Saved user {user.email} with ORCID ID: {user.orcid_id}")


# Additional signal to handle token storage
from django.db.models.signals import post_save

@receiver(post_save, sender=SocialToken)
def handle_social_token_created(sender, instance, created, **kwargs):
    """
    Handle when a SocialToken is created - store it in the user model
    """
    if created and instance.account.provider == 'orcid':
        user = instance.account.user
        if hasattr(user, 'orcid_token'):  # Check if it's our custom user model
            user.orcid_token = instance.token
            user.save()
            print(f"[SIGNAL] Stored ORCID token for user {user.email}")