"""
Data ingestion utilities for CSV file processing
Uses the unified CSV importers to ensure consistency with API endpoints
"""
import os
import csv
import io
import logging
from datetime import datetime
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import Publication, Conference, Editorial, Teaching, Talk, Link
from .csv_importers import (
    PublicationCSVImporter,
    TeachingCSVImporter,
    TalkCSVImporter,
    ConferenceCSVImporter,
    EditorialCSVImporter
)

logger = logging.getLogger(__name__)


def _import_csv_unified(user, csv_path, importer_class):
    """
    Helper function to import CSV using unified CSV importers
    """
    if not os.path.exists(csv_path):
        logger.info(f"No CSV file found at {csv_path}")
        return 0

    try:
        # Read the CSV file
        with open(csv_path, 'rb') as f:
            file_content = f.read()

        # Create a mock uploaded file
        filename = os.path.basename(csv_path)
        uploaded_file = SimpleUploadedFile(
            name=filename,
            content=file_content,
            content_type='text/csv'
        )

        # Use the unified CSV importer directly
        importer = importer_class()
        result = importer.import_csv(user, uploaded_file)

        if 'error' in result:
            logger.error(f"Error importing {filename}: {result['error']}")
            return 0

        created = result.get('created', 0)
        logger.info(f"Imported {created} items from {filename} via unified CSV importer")
        return created

    except Exception as e:
        logger.error(f"Error importing {csv_path} via unified CSV importer: {e}")
        raise




def ingest_additional_publications(user, data_directory):
    """
    Ingest additional publications from additional_pubs.csv using unified CSV importer
    Expected CSV columns: title, authors, year, doi, journal (same format as publications table)
    """
    csv_path = os.path.join(data_directory, 'additional_pubs.csv')
    return _import_csv_unified(user, csv_path, PublicationCSVImporter)


def ingest_conferences(user, data_directory):
    """
    Ingest conference presentations from conferences.csv using unified CSV importer
    """
    csv_path = os.path.join(data_directory, 'conferences.csv')
    return _import_csv_unified(user, csv_path, ConferenceCSVImporter)


def ingest_editorial(user, data_directory):
    """
    Ingest editorial activities from editorial.csv using unified CSV importer
    """
    csv_path = os.path.join(data_directory, 'editorial.csv')
    return _import_csv_unified(user, csv_path, EditorialCSVImporter)


def ingest_links(user, data_directory):
    """
    Ingest publication links from links.csv
    Expected CSV columns: publication_title, link_type, url, description
    """
    csv_path = os.path.join(data_directory, 'links.csv')
    if not os.path.exists(csv_path):
        logger.info(f"No links.csv found in {data_directory}")
        return 0

    count = 0
    try:
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Find the publication by title
                try:
                    publication = Publication.objects.get(
                        owner=user,
                        title=row.get('publication_title', '')
                    )
                except Publication.DoesNotExist:
                    logger.warning(f"Publication '{row.get('publication_title')}' not found, skipping link")
                    continue
                except Publication.MultipleObjectsReturned:
                    # If multiple publications with same title, use the first one
                    publication = Publication.objects.filter(
                        owner=user,
                        title=row.get('publication_title', '')
                    ).first()

                # Check if link already exists
                if Link.objects.filter(
                    owner=user,
                    doi=publication.doi or '',
                    url=row.get('url', '')
                ).exists():
                    logger.info(f"Link '{row.get('url')}' already exists, skipping")
                    continue

                link_data = {
                    'owner': user,
                    'type': row.get('link_type', 'Other'),
                    'doi': publication.doi or '',
                    'url': row.get('url', ''),
                    'title': row.get('description', ''),
                    'source': 'csv_import'
                }

                Link.objects.create(**link_data)
                count += 1
                logger.info(f"Created link: {row.get('url')} for {publication.title}")

    except Exception as e:
        logger.error(f"Error processing links.csv: {e}")
        raise

    return count


def ingest_talks(user, data_directory):
    """
    Ingest talks from talks.csv using unified CSV importer
    """
    csv_path = os.path.join(data_directory, 'talks.csv')
    return _import_csv_unified(user, csv_path, TalkCSVImporter)


def ingest_teaching(user, data_directory):
    """
    Ingest teaching activities from teaching.csv using unified CSV importer
    """
    csv_path = os.path.join(data_directory, 'teaching.csv')
    return _import_csv_unified(user, csv_path, TeachingCSVImporter)


def ingest_all_data_files(user, data_directory):
    """
    Ingest all supported data files from the specified directory
    Returns a dictionary with counts for each type
    """
    if not os.path.exists(data_directory):
        logger.warning(f"Data directory does not exist: {data_directory}")
        return {}

    results = {}

    try:
        results['additional_publications'] = ingest_additional_publications(user, data_directory)
        results['conferences'] = ingest_conferences(user, data_directory)
        results['editorial'] = ingest_editorial(user, data_directory)
        results['links'] = ingest_links(user, data_directory)
        results['talks'] = ingest_talks(user, data_directory)
        results['teaching'] = ingest_teaching(user, data_directory)

        total_imported = sum(results.values())
        logger.info(f"Data ingestion completed. Total items imported: {total_imported}")

    except Exception as e:
        logger.error(f"Error during data ingestion: {e}")
        raise

    return results