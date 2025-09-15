# Generated migration to populate volume and page_range fields from metadata

from django.db import migrations, models


def populate_volume_page_range(apps, schema_editor):
    """Populate volume and page_range fields from existing metadata"""
    Publication = apps.get_model('academic', 'Publication')

    updated_count = 0
    for pub in Publication.objects.all():
        updated = False

        # Extract volume from metadata if not already set
        if not pub.volume and pub.metadata:
            volume = None

            # Check different locations in metadata
            if isinstance(pub.metadata, dict):
                # Direct volume field
                volume = pub.metadata.get('volume')

                # Check raw_data if available
                if not volume and pub.metadata.get('raw_data'):
                    raw_data = pub.metadata['raw_data']
                    if isinstance(raw_data, dict):
                        volume = raw_data.get('volume')

            if volume:
                pub.volume = str(volume)
                updated = True

        # Extract page_range from metadata if not already set
        if not pub.page_range and pub.metadata:
            page_range = None

            # Check different locations in metadata
            if isinstance(pub.metadata, dict):
                # Check various page field names
                page_range = (pub.metadata.get('page') or
                             pub.metadata.get('pages') or
                             pub.metadata.get('pageRange'))

                # Check raw_data if available
                if not page_range and pub.metadata.get('raw_data'):
                    raw_data = pub.metadata['raw_data']
                    if isinstance(raw_data, dict):
                        page_range = (raw_data.get('pageRange') or
                                     raw_data.get('page') or
                                     raw_data.get('pages'))

            if page_range:
                pub.page_range = str(page_range)
                updated = True

        if updated:
            pub.save(update_fields=['volume', 'page_range'])
            updated_count += 1

    print(f"Updated {updated_count} publications with volume/page_range data from metadata")


def reverse_populate_volume_page_range(apps, schema_editor):
    """Reverse migration - clear volume and page_range fields"""
    Publication = apps.get_model('academic', 'Publication')
    Publication.objects.all().update(volume=None, page_range=None)


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0017_publication_page_range_publication_volume'),
    ]

    operations = [
        migrations.RunPython(
            populate_volume_page_range,
            reverse_populate_volume_page_range,
            atomic=True
        ),
    ]