from django.db import migrations


def update_search_vector(apps, schema_editor):
    """Update search vector to include authors - PostgreSQL only"""
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE academic_publication DROP COLUMN IF EXISTS search_vector;")
        cursor.execute("""
            ALTER TABLE academic_publication
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(publication_name, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(metadata->>'abstract', '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(authors::text, '')), 'D')
            ) STORED;
        """)
        cursor.execute("DROP INDEX IF EXISTS publication_search_vector_idx;")
        cursor.execute("CREATE INDEX publication_search_vector_idx ON academic_publication USING GIN (search_vector);")


def revert_search_vector(apps, schema_editor):
    """Revert search vector to exclude authors - PostgreSQL only"""
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE academic_publication DROP COLUMN IF EXISTS search_vector;")
        cursor.execute("""
            ALTER TABLE academic_publication
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(publication_name, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(metadata->>'abstract', '')), 'C')
            ) STORED;
        """)
        cursor.execute("DROP INDEX IF EXISTS publication_search_vector_idx;")
        cursor.execute("CREATE INDEX publication_search_vector_idx ON academic_publication USING GIN (search_vector);")


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0020_apirecordcache'),
    ]

    operations = [
        migrations.RunPython(update_search_vector, revert_search_vector),
    ]