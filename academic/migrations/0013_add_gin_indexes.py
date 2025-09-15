from django.contrib.postgres.indexes import GinIndex
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0012_add_skip_dois_field'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='publication',
            index=GinIndex(fields=['metadata'], name='publication_metadata_gin'),
        ),
        migrations.AddIndex(
            model_name='publication',
            index=GinIndex(fields=['authors'], name='publication_authors_gin'),
        ),
        migrations.AddIndex(
            model_name='publication',
            index=GinIndex(fields=['identifiers'], name='publication_identifiers_gin'),
        ),
        migrations.AddIndex(
            model_name='funding',
            index=GinIndex(fields=['additional_info'], name='funding_info_gin'),
        ),
    ]