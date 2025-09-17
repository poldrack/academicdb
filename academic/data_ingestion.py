"""
Data ingestion utilities for CSV file processing
"""
import os
import csv
import logging
from datetime import datetime
from django.utils import timezone
from .models import Publication, Conference, Editorial, Teaching, Talk, Link

logger = logging.getLogger(__name__)


def ingest_additional_publications(user, data_directory):
    """
    Ingest additional publications from additional_pubs.csv
    Expected CSV columns: title, authors, year, doi, journal
    """
    csv_path = os.path.join(data_directory, 'additional_pubs.csv')
    if not os.path.exists(csv_path):
        logger.info(f"No additional_pubs.csv found in {data_directory}")
        return 0

    count = 0
    try:
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Check if publication already exists
                if row.get('doi') and Publication.objects.filter(
                    owner=user, doi=row['doi']
                ).exists():
                    logger.info(f"Publication with DOI {row['doi']} already exists, skipping")
                    continue

                # Create publication
                pub_data = {
                    'owner': user,
                    'title': row.get('title', ''),
                    'year': int(row.get('year', 0)) if row.get('year') and row['year'].isdigit() else None,
                    'doi': row.get('doi', ''),
                    'source': 'manual_csv',
                    'metadata': {
                        'journal': row.get('journal', ''),
                        'authors_raw': row.get('authors', ''),
                        'imported_from': 'additional_pubs.csv'
                    }
                }

                # Parse authors
                if row.get('authors'):
                    authors = []
                    for author in row['authors'].split(';'):
                        author = author.strip()
                        if author:
                            authors.append({
                                'name': author,
                                'affiliation': ''
                            })
                    pub_data['authors'] = authors
                else:
                    pub_data['authors'] = []

                Publication.objects.create(**pub_data)
                count += 1
                logger.info(f"Created publication: {row.get('title', 'Unknown title')}")

    except Exception as e:
        logger.error(f"Error processing additional_pubs.csv: {e}")
        raise

    return count


def ingest_conferences(user, data_directory):
    """
    Ingest conference presentations from conferences.csv
    Expected CSV columns: title, authors, year, venue, location
    """
    csv_path = os.path.join(data_directory, 'conferences.csv')
    if not os.path.exists(csv_path):
        logger.info(f"No conferences.csv found in {data_directory}")
        return 0

    count = 0
    try:
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Check if conference already exists
                if Conference.objects.filter(
                    owner=user,
                    title=row.get('title', ''),
                    year=int(row.get('year', 0)) if row.get('year') and row['year'].isdigit() else None
                ).exists():
                    logger.info(f"Conference '{row.get('title')}' already exists, skipping")
                    continue

                conf_data = {
                    'owner': user,
                    'title': row.get('title', ''),
                    'authors': row.get('authors', ''),
                    'year': int(row.get('year', 0)) if row.get('year') and row['year'].isdigit() else None,
                    'conference_name': row.get('venue', ''),
                    'location': row.get('location', ''),
                    'source': 'manual_csv'
                }

                Conference.objects.create(**conf_data)
                count += 1
                logger.info(f"Created conference: {row.get('title', 'Unknown title')}")

    except Exception as e:
        logger.error(f"Error processing conferences.csv: {e}")
        raise

    return count


def ingest_editorial(user, data_directory):
    """
    Ingest editorial activities from editorial.csv
    Expected CSV columns: role, journal, dates
    """
    csv_path = os.path.join(data_directory, 'editorial.csv')
    if not os.path.exists(csv_path):
        logger.info(f"No editorial.csv found in {data_directory}")
        return 0

    count = 0
    try:
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Check if editorial already exists
                if Editorial.objects.filter(
                    owner=user,
                    role=row.get('role', ''),
                    journal=row.get('journal', '')
                ).exists():
                    logger.info(f"Editorial role '{row.get('role')}' at '{row.get('journal')}' already exists, skipping")
                    continue

                editorial_data = {
                    'owner': user,
                    'role': row.get('role', ''),
                    'journal': row.get('journal', ''),
                    'dates': row.get('dates', ''),
                    'source': 'manual_csv'
                }

                Editorial.objects.create(**editorial_data)
                count += 1
                logger.info(f"Created editorial: {row.get('role')} at {row.get('journal')}")

    except Exception as e:
        logger.error(f"Error processing editorial.csv: {e}")
        raise

    return count


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
    Ingest talks from talks.csv
    Expected CSV columns: title, venue, date, type
    """
    csv_path = os.path.join(data_directory, 'talks.csv')
    if not os.path.exists(csv_path):
        logger.info(f"No talks.csv found in {data_directory}")
        return 0

    count = 0
    try:
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Parse date and year
                date = None
                year = None
                if row.get('date'):
                    try:
                        date = datetime.strptime(row['date'], '%Y-%m-%d').date()
                        year = date.year
                    except ValueError:
                        logger.warning(f"Invalid date format '{row['date']}', expected YYYY-MM-DD")
                        # Try to extract year
                        if row['date'].isdigit() and len(row['date']) == 4:
                            year = int(row['date'])

                # Check if talk already exists
                if Talk.objects.filter(
                    owner=user,
                    title=row.get('title', ''),
                    place=row.get('venue', ''),
                    year=year
                ).exists():
                    logger.info(f"Talk '{row.get('title')}' already exists, skipping")
                    continue

                talk_data = {
                    'owner': user,
                    'title': row.get('title', ''),
                    'place': row.get('venue', ''),
                    'date': date,
                    'year': year or datetime.now().year,
                    'source': 'manual_csv'
                }

                Talk.objects.create(**talk_data)
                count += 1
                logger.info(f"Created talk: {row.get('title', 'Unknown title')}")

    except Exception as e:
        logger.error(f"Error processing talks.csv: {e}")
        raise

    return count


def ingest_teaching(user, data_directory):
    """
    Ingest teaching activities from teaching.csv
    Expected CSV columns: course_name, institution, year, role
    """
    csv_path = os.path.join(data_directory, 'teaching.csv')
    if not os.path.exists(csv_path):
        logger.info(f"No teaching.csv found in {data_directory}")
        return 0

    count = 0
    try:
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Check if teaching record already exists
                if Teaching.objects.filter(
                    owner=user,
                    name=row.get('course_name', ''),
                    institution=row.get('institution', ''),
                    year=int(row.get('year', 0)) if row.get('year') and row['year'].isdigit() else None
                ).exists():
                    logger.info(f"Teaching record '{row.get('course_name')}' already exists, skipping")
                    continue

                teaching_data = {
                    'owner': user,
                    'name': row.get('course_name', ''),
                    'institution': row.get('institution', ''),
                    'year': int(row.get('year', 0)) if row.get('year') and row['year'].isdigit() else None,
                    'source': 'manual_csv'
                }

                Teaching.objects.create(**teaching_data)
                count += 1
                logger.info(f"Created teaching: {row.get('course_name', 'Unknown course')}")

    except Exception as e:
        logger.error(f"Error processing teaching.csv: {e}")
        raise

    return count


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