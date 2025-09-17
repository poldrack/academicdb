"""
Collaborator utilities for extracting and managing collaborators from publications
"""
import logging
from datetime import datetime
from collections import defaultdict
from django.utils import timezone
from .models import Publication, Collaborator

logger = logging.getLogger(__name__)


def extract_collaborators_from_publications(user):
    """
    Extract unique Scopus IDs from all publications belonging to a user.
    Excludes the user's own Scopus ID if it exists.

    Returns:
        set: Set of unique Scopus IDs found in user's publications
    """
    # Get user's own Scopus ID to exclude
    user_scopus_id = getattr(user, 'scopus_id', None)
    if user_scopus_id:
        user_scopus_id = str(user_scopus_id).strip()

    collaborator_ids = set()

    # Get all publications for this user
    publications = Publication.objects.filter(owner=user)

    for pub in publications:
        # Check metadata for Scopus coauthor IDs
        metadata = pub.metadata or {}

        # Look for scopus_coauthor_ids in metadata
        scopus_ids = metadata.get('scopus_coauthor_ids', [])
        if isinstance(scopus_ids, list):
            for scopus_id in scopus_ids:
                scopus_id = str(scopus_id).strip()
                # Exclude user's own ID
                if scopus_id and scopus_id != user_scopus_id:
                    collaborator_ids.add(scopus_id)

        # Also check for authors with scopus_id in the authors field
        authors = pub.authors or []
        if isinstance(authors, list):
            for author in authors:
                if isinstance(author, dict) and 'scopus_id' in author:
                    scopus_id = str(author['scopus_id']).strip()
                    if scopus_id and scopus_id != user_scopus_id:
                        collaborator_ids.add(scopus_id)

    logger.info(f"Found {len(collaborator_ids)} unique collaborators for user {user.id}")
    return collaborator_ids


def get_most_recent_collaboration_date(user, scopus_id):
    """
    Get the most recent publication date for a specific collaborator.

    Args:
        user: AcademicUser instance
        scopus_id: Scopus ID of the collaborator

    Returns:
        date or None: Most recent collaboration date
    """
    publications = Publication.objects.filter(owner=user)

    most_recent_date = None

    for pub in publications:
        # Check if this publication includes the collaborator
        metadata = pub.metadata or {}
        scopus_ids = metadata.get('scopus_coauthor_ids', [])

        # Also check authors field
        authors = pub.authors or []
        author_scopus_ids = [
            str(author.get('scopus_id', ''))
            for author in authors
            if isinstance(author, dict) and author.get('scopus_id')
        ]

        all_ids = [str(sid) for sid in scopus_ids] + author_scopus_ids

        if str(scopus_id) in all_ids:
            pub_date = pub.publication_date
            if pub_date and (most_recent_date is None or pub_date > most_recent_date):
                most_recent_date = pub_date

    return most_recent_date


def count_collaborations(user, scopus_id):
    """
    Count the number of publications shared with a specific collaborator.

    Args:
        user: AcademicUser instance
        scopus_id: Scopus ID of the collaborator

    Returns:
        int: Number of shared publications
    """
    publications = Publication.objects.filter(owner=user)

    count = 0

    for pub in publications:
        # Check if this publication includes the collaborator
        metadata = pub.metadata or {}
        scopus_ids = metadata.get('scopus_coauthor_ids', [])

        # Also check authors field
        authors = pub.authors or []
        author_scopus_ids = [
            str(author.get('scopus_id', ''))
            for author in authors
            if isinstance(author, dict) and author.get('scopus_id')
        ]

        all_ids = [str(sid) for sid in scopus_ids] + author_scopus_ids

        if str(scopus_id) in all_ids:
            count += 1

    return count


def get_scopus_author_info(scopus_id):
    """
    Retrieve author information from Scopus API.

    Args:
        scopus_id: Scopus Author ID

    Returns:
        dict: Author information including name and affiliation
    """
    try:
        from pybliometrics.scopus import AuthorRetrieval

        author_info = AuthorRetrieval(scopus_id)

        # Extract basic information
        result = {
            'scopus_id': scopus_id,
            'surname': getattr(author_info, 'surname', ''),
            'given_name': getattr(author_info, 'given_name', ''),
            'indexed_name': getattr(author_info, 'indexed_name', ''),
            'affiliation_current': []
        }

        # Format full name
        if result['surname'] and result['given_name']:
            result['name'] = f"{result['surname']}, {result['given_name']}"
        elif result['indexed_name']:
            result['name'] = result['indexed_name']
        else:
            result['name'] = f"Author {scopus_id}"

        # Extract current affiliation
        if hasattr(author_info, 'affiliation_current') and author_info.affiliation_current:
            for affil in author_info.affiliation_current:
                affil_info = {
                    'id': getattr(affil, 'id', ''),
                    'name': getattr(affil, 'name', ''),
                    'city': getattr(affil, 'city', ''),
                    'country': getattr(affil, 'country', '')
                }
                result['affiliation_current'].append(affil_info)

        return result

    except Exception as e:
        logger.error(f"Error retrieving Scopus author info for {scopus_id}: {e}")
        return {
            'scopus_id': scopus_id,
            'name': f"Author {scopus_id}",
            'affiliation_current': [],
            'error': str(e)
        }


def build_collaborators_table(user):
    """
    Build the collaborators table for a user by:
    1. Extracting unique Scopus IDs from publications
    2. Retrieving current affiliation information from Scopus API
    3. Creating/updating Collaborator records

    Args:
        user: AcademicUser instance

    Returns:
        dict: Results summary with counts of processed, created, updated, and errors
    """
    logger.info(f"Building collaborators table for user {user.id}")

    # Extract collaborator IDs from publications
    collaborator_ids = extract_collaborators_from_publications(user)

    results = {
        'processed': 0,
        'created': 0,
        'updated': 0,
        'errors': 0,
        'error_details': []
    }

    for scopus_id in collaborator_ids:
        try:
            # Get author info from Scopus API
            author_info = get_scopus_author_info(scopus_id)

            # Get collaboration statistics
            last_collab_date = get_most_recent_collaboration_date(user, scopus_id)
            pub_count = count_collaborations(user, scopus_id)

            # Extract primary affiliation
            affiliation = ""
            affiliation_id = ""
            if author_info.get('affiliation_current'):
                primary_affil = author_info['affiliation_current'][0]
                affiliation = primary_affil.get('name', '')
                affiliation_id = primary_affil.get('id', '')

            # Create or update collaborator record
            collaborator, created = Collaborator.objects.get_or_create(
                owner=user,
                scopus_id=scopus_id,
                defaults={
                    'name': author_info.get('name', f'Author {scopus_id}'),
                    'affiliation': affiliation,
                    'affiliation_id': affiliation_id,
                    'last_publication_date': last_collab_date,
                    'publication_count': pub_count,
                    'additional_info': author_info,
                    'source': 'scopus_api'
                }
            )

            if not created:
                # Update existing record with latest information
                collaborator.name = author_info.get('name', collaborator.name)
                collaborator.affiliation = affiliation
                collaborator.affiliation_id = affiliation_id
                collaborator.last_publication_date = last_collab_date
                collaborator.publication_count = pub_count
                collaborator.additional_info = author_info
                collaborator.save()
                results['updated'] += 1
            else:
                results['created'] += 1

            results['processed'] += 1
            logger.info(f"Processed collaborator {scopus_id}: {author_info.get('name')}")

        except Exception as e:
            error_msg = f"Error processing collaborator {scopus_id}: {str(e)}"
            logger.error(error_msg)
            results['errors'] += 1
            results['error_details'].append(error_msg)

    logger.info(f"Collaborators table build complete: {results}")
    return results


def deduplicate_collaborators(user):
    """
    Remove duplicate collaborator entries (same Scopus ID) keeping the most recent.

    Args:
        user: AcademicUser instance

    Returns:
        int: Number of duplicates removed
    """
    duplicate_ids = Collaborator.find_duplicate_scopus_ids(user)
    removed_count = 0

    for scopus_id in duplicate_ids:
        # Get all collaborators with this Scopus ID
        collaborators = Collaborator.objects.filter(
            owner=user,
            scopus_id=scopus_id
        ).order_by('-updated_at')

        # Keep the most recently updated one, delete the rest
        to_keep = collaborators.first()
        to_delete = collaborators[1:]

        for collaborator in to_delete:
            collaborator.delete()
            removed_count += 1

    logger.info(f"Removed {removed_count} duplicate collaborators for user {user.id}")
    return removed_count