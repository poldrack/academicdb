#!/usr/bin/env python
"""
Create a completely fresh database from current models, ignoring all migrations.
This is specifically for Docker deployments where we want a clean start.
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
    from django.core.management.sql import sql_create_index
    from django.db import connection
    from django.apps import apps

    print("🗄️ Creating fresh database schema from models...")

    # Get the current database connection
    cursor = connection.cursor()

    # Create tables for all installed apps
    from django.core.management.commands.migrate import Command as MigrateCommand
    from django.core.management.color import no_style

    # Use Django's internal table creation
    style = no_style()

    # Get all app configs
    app_configs = [apps.get_app_config(label) for label in ['contenttypes', 'auth', 'admin', 'sessions', 'sites', 'account', 'socialaccount', 'academic']]

    # Create tables for each app
    for app_config in app_configs:
        for model in app_config.get_models():
            if not model._meta.managed:
                continue
            print(f"   Creating table for {model._meta.label}")

            # Generate and execute CREATE TABLE SQL
            sql_statements = connection.ops.sql_create_model(model, style)[0]
            for statement in sql_statements:
                try:
                    cursor.execute(statement)
                    print(f"   ✅ {statement[:60]}...")
                except Exception as e:
                    if "already exists" not in str(e):
                        print(f"   ⚠️ Skipped: {e}")

    # Create indexes for models (SQLite-compatible only)
    print("   Creating indexes...")
    for app_config in app_configs:
        for model in app_config.get_models():
            if not model._meta.managed:
                continue
            for field in model._meta.fields:
                if field.db_index and not field.unique:
                    try:
                        index_name = f"{model._meta.db_table}_{field.column}_idx"
                        sql = f"CREATE INDEX {index_name} ON {model._meta.db_table} ({field.column})"
                        cursor.execute(sql)
                        print(f"   ✅ Index: {index_name}")
                    except Exception as e:
                        if "already exists" not in str(e):
                            print(f"   ⚠️ Index skipped: {e}")

    print("✅ Fresh database schema created successfully!")

except Exception as e:
    print(f"❌ Database creation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)