from django.db import migrations


def add_gin_indexes(apps, schema_editor):
    """Add GIN indexes only on PostgreSQL"""
    if schema_editor.connection.vendor != 'postgresql':
        return

    from django.contrib.postgres.indexes import GinIndex
    Publication = apps.get_model('academic', 'Publication')
    Funding = apps.get_model('academic', 'Funding')

    # Create indexes using raw SQL for PostgreSQL
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('CREATE INDEX IF NOT EXISTS publication_metadata_gin ON academic_publication USING GIN (metadata);')
        cursor.execute('CREATE INDEX IF NOT EXISTS publication_authors_gin ON academic_publication USING GIN (authors);')
        cursor.execute('CREATE INDEX IF NOT EXISTS publication_identifiers_gin ON academic_publication USING GIN (identifiers);')
        cursor.execute('CREATE INDEX IF NOT EXISTS funding_info_gin ON academic_funding USING GIN (additional_info);')


def remove_gin_indexes(apps, schema_editor):
    """Remove GIN indexes only on PostgreSQL"""
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP INDEX IF EXISTS publication_metadata_gin;')
        cursor.execute('DROP INDEX IF EXISTS publication_authors_gin;')
        cursor.execute('DROP INDEX IF EXISTS publication_identifiers_gin;')
        cursor.execute('DROP INDEX IF EXISTS funding_info_gin;')


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0012_add_skip_dois_field'),
    ]

    operations = [
        migrations.RunPython(add_gin_indexes, remove_gin_indexes),
    ]