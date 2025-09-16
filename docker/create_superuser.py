#!/usr/bin/env python
"""
Create Django superuser from environment variables.
This script is used during Docker initialization.
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.insert(0, '/app')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academicdb_web.settings.docker')
django.setup()

from django.contrib.auth import get_user_model

def create_superuser():
    """Create superuser if environment variables are provided and user doesn't exist."""
    User = get_user_model()

    username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
    email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

    if not all([username, email, password]):
        print("Superuser environment variables not provided. Skipping superuser creation.")
        return

    try:
        if User.objects.filter(username=username).exists():
            print(f"Superuser '{username}' already exists. Skipping creation.")
            return

        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        print(f"Superuser '{username}' created successfully.")

    except Exception as e:
        print(f"Error creating superuser: {e}")
        sys.exit(1)

if __name__ == '__main__':
    create_superuser()