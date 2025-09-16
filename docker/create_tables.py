#!/usr/bin/env python
"""
Docker initialization script that creates the database schema
without problematic PostgreSQL-specific migrations.
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
    from django.core.management import call_command
    from django.db import connection

    print("🗄️ Initializing fresh database...")

    # For SQLite deployment, create tables directly from models
    # This bypasses the problematic PostgreSQL migrations
    call_command('migrate', 'contenttypes', verbosity=0)
    call_command('migrate', 'auth', verbosity=0)
    call_command('migrate', 'admin', verbosity=0)
    call_command('migrate', 'sessions', verbosity=0)
    call_command('migrate', 'sites', verbosity=0)
    call_command('migrate', 'account', verbosity=0)
    call_command('migrate', 'socialaccount', verbosity=0)

    # Create academic app tables without problematic migrations
    call_command('migrate', 'academic', '0012', verbosity=0)

    # Mark the problematic migrations as applied without running them
    call_command('migrate', 'academic', '--fake', verbosity=0)

    print("✅ Database initialization completed")

except Exception as e:
    print(f"❌ Database initialization failed: {e}")
    sys.exit(1)