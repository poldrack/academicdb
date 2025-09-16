#!/usr/bin/env python
"""
Docker-specific migration script that handles database differences.
This script runs appropriate migrations based on the database backend.
"""

import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
sys.path.insert(0, '/app')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academicdb_web.settings.docker')

try:
    django.setup()
    from django.core.management import execute_from_command_line
    from django.conf import settings
    from django.db import connection

    print("🗄️ Setting up database...")

    # Check database engine
    engine = settings.DATABASES['default']['ENGINE']
    print(f"   Database engine: {engine}")

    if 'sqlite' in engine:
        print("   Using SQLite - running compatible migrations only")

        # For SQLite, we need to fake the PostgreSQL-specific migrations
        print("   Faking PostgreSQL-specific migrations...")

        # Run initial migrations first
        execute_from_command_line(['manage.py', 'migrate', '--fake-initial'])

        # Then run up to before PostgreSQL features
        execute_from_command_line(['manage.py', 'migrate', 'academic', '0012'])

        # Fake the problematic migrations
        execute_from_command_line(['manage.py', 'migrate', 'academic', '0013', '--fake'])
        execute_from_command_line(['manage.py', 'migrate', 'academic', '0014', '--fake'])

        # Run any remaining migrations
        execute_from_command_line(['manage.py', 'migrate'])

        print("   ✅ SQLite migrations completed")

    else:
        print("   Using PostgreSQL - running all migrations")
        execute_from_command_line(['manage.py', 'migrate', '--fake-initial'])
        print("   ✅ PostgreSQL migrations completed")

except Exception as e:
    print(f"❌ Migration failed: {e}")
    sys.exit(1)

print("🎉 Database setup completed successfully!")