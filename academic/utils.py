"""
Utility functions for the academic Django app
"""

import os
import pybliometrics
from django.core.management.utils import get_random_secret_key
from pathlib import Path


def init_pybliometrics():
    """
    Initialize pybliometrics with API key from environment variable if available,
    otherwise use interactive configuration.
    """
    scopus_api_key = os.environ.get('SCOPUS_API_KEY')
    if scopus_api_key:
        pybliometrics.scopus.init(keys=[scopus_api_key])
    else:
        pybliometrics.scopus.init()


def get_or_generate_secret_key():
    """
    Get SECRET_KEY from environment variable, or generate a new one and save to .env file.

    Returns:
        str: The secret key to use
    """
    secret_key = os.getenv('SECRET_KEY')

    if secret_key:
        return secret_key

    # Generate a new secret key
    new_secret_key = get_random_secret_key()

    # Find the project root (where manage.py is located)
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent  # Go up to academicdb2 directory

    # Look for manage.py to confirm we're in the right place
    while project_root != project_root.parent and not (project_root / 'manage.py').exists():
        project_root = project_root.parent

    env_file = project_root / '.env'

    # Create or append to .env file
    env_content = ''
    if env_file.exists():
        with open(env_file, 'r') as f:
            env_content = f.read()

    # Check if SECRET_KEY is already in .env but not set
    if 'SECRET_KEY=' not in env_content:
        # Append the new secret key
        with open(env_file, 'a') as f:
            if env_content and not env_content.endswith('\n'):
                f.write('\n')
            f.write(f'SECRET_KEY={new_secret_key}\n')

        print(f"Generated new SECRET_KEY and saved to {env_file}")

    return new_secret_key