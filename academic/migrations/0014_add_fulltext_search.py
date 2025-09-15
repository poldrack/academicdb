from django.contrib.postgres.search import SearchVector
from django.contrib.postgres.indexes import GinIndex
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0013_add_gin_indexes'),
    ]

    operations = [
        # Add search vector field for full-text search
        migrations.RunSQL(
            sql="""
            ALTER TABLE academic_publication
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(publication_name, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(metadata->>'abstract', '')), 'C')
            ) STORED;
            """,
            reverse_sql="ALTER TABLE academic_publication DROP COLUMN search_vector;"
        ),

        # Create GIN index on search vector
        migrations.RunSQL(
            sql="CREATE INDEX publication_search_vector_idx ON academic_publication USING GIN (search_vector);",
            reverse_sql="DROP INDEX IF EXISTS publication_search_vector_idx;"
        ),
    ]