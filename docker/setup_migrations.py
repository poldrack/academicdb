#!/usr/bin/env python
"""
Setup script to prepare SQLite-compatible migrations for Docker builds.
This modifies problematic migrations to remove PostgreSQL-specific operations
while preserving table and field creation operations.
"""

import os
import shutil
from pathlib import Path

# Migration directory
migrations_dir = Path('/app/academic/migrations')
backup_dir = Path('/app/docker/migrations_backup')

# Create backup directory
backup_dir.mkdir(exist_ok=True)

print("🔧 Setting up SQLite-compatible migrations...")

def create_sqlite_migration_13():
    """Migration 0013 - Remove GIN indexes, keep everything else"""
    return """# SQLite-compatible migration (Docker build)
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [('academic', '0012_add_skip_dois_field')]

    # Remove GIN index operations for SQLite compatibility
    operations = []
"""

def create_sqlite_migration_14():
    """Migration 0014 - Remove PostgreSQL search, keep everything else"""
    return """# SQLite-compatible migration (Docker build)
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [('academic', '0013_add_gin_indexes')]

    # Remove PostgreSQL full-text search operations for SQLite compatibility
    operations = []
"""

def create_sqlite_migration_15():
    """Migration 0015 - Keep ProfessionalActivity creation, remove GIN indexes"""
    return """# SQLite-compatible migration (Docker build)
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('academic', '0014_add_fulltext_search')]

    operations = [
        # Keep the ProfessionalActivity model creation
        migrations.CreateModel(
            name="ProfessionalActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("activity_type", models.CharField(choices=[("employment", "Employment"), ("education", "Education"), ("qualification", "Qualification"), ("invited_position", "Invited Position"), ("distinction", "Distinction"), ("membership", "Membership"), ("service", "Service")], help_text="Type of professional activity", max_length=50)),
                ("title", models.CharField(help_text="Position title or activity name", max_length=500)),
                ("organization", models.CharField(help_text="Organization or institution name", max_length=500)),
                ("department", models.CharField(blank=True, help_text="Department within organization", max_length=500, null=True)),
                ("role", models.CharField(blank=True, help_text="Role or position type", max_length=200, null=True)),
                ("start_date", models.DateField(blank=True, help_text="Start date of activity", null=True)),
                ("end_date", models.DateField(blank=True, help_text="End date of activity (null for current positions)", null=True)),
                ("is_current", models.BooleanField(default=False, help_text="Is this a current/ongoing activity?")),
                ("city", models.CharField(blank=True, max_length=200, null=True)),
                ("region", models.CharField(blank=True, max_length=200, null=True)),
                ("country", models.CharField(blank=True, max_length=200, null=True)),
                ("description", models.TextField(blank=True, help_text="Description of the activity or role", null=True)),
                ("url", models.URLField(blank=True, help_text="URL for more information", max_length=500, null=True)),
                ("orcid_put_code", models.CharField(blank=True, help_text="ORCID put-code for this activity", max_length=50, null=True, unique=True)),
                ("orcid_path", models.CharField(blank=True, help_text="ORCID API path for this activity", max_length=200, null=True)),
                ("orcid_visibility", models.CharField(blank=True, help_text="ORCID visibility setting", max_length=20, null=True)),
                ("orcid_data", models.JSONField(blank=True, default=dict, help_text="Raw data from ORCID API")),
                ("source", models.CharField(choices=[("orcid", "ORCID"), ("manual", "Manual Entry")], default="orcid", help_text="Original data source", max_length=50)),
                ("manual_edits", models.JSONField(blank=True, default=dict, help_text="Tracks which fields have been manually edited")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_synced", models.DateTimeField(blank=True, help_text="Last time synced from ORCID", null=True)),
            ],
            options={
                "verbose_name": "Professional Activity",
                "verbose_name_plural": "Professional Activities",
                "ordering": ["-is_current", "-start_date", "title"],
            },
        ),

        # Add the owner field
        migrations.AddField(
            model_name="professionalactivity",
            name="owner",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="professional_activities", to=settings.AUTH_USER_MODEL),
        ),

        # Add regular indexes (not GIN indexes for SQLite compatibility)
        migrations.AddIndex(
            model_name="professionalactivity",
            index=models.Index(fields=["owner", "activity_type"], name="academic_pr_owner_i_28b0ee_idx"),
        ),
        migrations.AddIndex(
            model_name="professionalactivity",
            index=models.Index(fields=["owner", "is_current"], name="academic_pr_owner_i_92be70_idx"),
        ),
        migrations.AddIndex(
            model_name="professionalactivity",
            index=models.Index(fields=["activity_type", "start_date"], name="academic_pr_activit_4ac0db_idx"),
        ),
        migrations.AddIndex(
            model_name="professionalactivity",
            index=models.Index(fields=["orcid_put_code"], name="academic_pr_orcid_p_4665e9_idx"),
        ),

        # Add unique constraint
        migrations.AlterUniqueTogether(
            name="professionalactivity",
            unique_together={("owner", "orcid_put_code")},
        ),

        # Skip the RemoveIndex operations for GIN indexes since they don't exist in SQLite
    ]
"""

def create_sqlite_migration_21():
    """Migration 0021 - Skip PostgreSQL search vector update for SQLite"""
    return """# SQLite-compatible migration (Docker build)
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [('academic', '0020_apirecordcache')]

    # Skip PostgreSQL search vector operations for SQLite compatibility
    operations = []
"""

# Migration replacements
migration_replacements = {
    '0013_add_gin_indexes.py': create_sqlite_migration_13(),
    '0014_add_fulltext_search.py': create_sqlite_migration_14(),
    '0015_professionalactivity_remove_funding_funding_info_gin_and_more.py': create_sqlite_migration_15(),
    '0021_update_search_vector_include_authors.py': create_sqlite_migration_21()
}

for migration_file, replacement_content in migration_replacements.items():
    migration_path = migrations_dir / migration_file
    backup_path = backup_dir / migration_file

    if migration_path.exists():
        # Backup original
        shutil.copy2(migration_path, backup_path)
        print(f"   Backed up: {migration_file}")

        # Write SQLite-compatible version
        with open(migration_path, 'w') as f:
            f.write(replacement_content)
        print(f"   ✅ Created SQLite-compatible: {migration_file}")

print("✅ Migration setup complete for SQLite compatibility")