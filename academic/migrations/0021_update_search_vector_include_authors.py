from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0020_apirecordcache'),
    ]

    operations = [
        # Update search vector to include authors
        migrations.RunSQL(
            sql="""
            ALTER TABLE academic_publication
            DROP COLUMN IF EXISTS search_vector;

            ALTER TABLE academic_publication
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(publication_name, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(metadata->>'abstract', '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(authors::text, '')), 'D')
            ) STORED;
            """,
            reverse_sql="""
            ALTER TABLE academic_publication
            DROP COLUMN IF EXISTS search_vector;

            ALTER TABLE academic_publication
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(publication_name, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(metadata->>'abstract', '')), 'C')
            ) STORED;
            """
        ),

        # Recreate GIN index on search vector
        migrations.RunSQL(
            sql="""
            DROP INDEX IF EXISTS publication_search_vector_idx;
            CREATE INDEX publication_search_vector_idx ON academic_publication USING GIN (search_vector);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS publication_search_vector_idx;
            CREATE INDEX publication_search_vector_idx ON academic_publication USING GIN (search_vector);
            """
        ),
    ]