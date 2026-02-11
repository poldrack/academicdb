from django.db import migrations


def add_fulltext_search(apps, schema_editor):
    """Add full-text search only on PostgreSQL"""
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        # Add search vector field for full-text search
        cursor.execute("""
            ALTER TABLE academic_publication
            ADD COLUMN IF NOT EXISTS search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(publication_name, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(metadata->>'abstract', '')), 'C')
            ) STORED;
        """)
        # Create GIN index on search vector
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS publication_search_vector_idx
            ON academic_publication USING GIN (search_vector);
        """)


def remove_fulltext_search(apps, schema_editor):
    """Remove full-text search only on PostgreSQL"""
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS publication_search_vector_idx;")
        cursor.execute("ALTER TABLE academic_publication DROP COLUMN IF EXISTS search_vector;")


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0013_add_gin_indexes'),
    ]

    operations = [
        migrations.RunPython(add_fulltext_search, remove_fulltext_search),
    ]