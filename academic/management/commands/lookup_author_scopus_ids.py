"""
Django management command to lookup Scopus IDs for all authors in existing publications
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from pybliometrics.scopus import ScopusSearch, AuthorRetrieval
import pybliometrics
import time
from collections import defaultdict

from academic.models import Publication
from academic.utils import init_pybliometrics

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Lookup Scopus IDs for all authors in existing publications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to process publications for (optional - if not provided, processes all users)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )
        parser.add_argument(
            '--rate-limit',
            type=float,
            default=2.0,
            help='Seconds to wait between Scopus API calls (default: 2.0)'
        )

    def handle(self, *args, **options):
        # Initialize Scopus
        try:
            init_pybliometrics()
        except Exception as e:
            raise CommandError(f"Failed to initialize Scopus: {str(e)}")

        user_id = options.get('user_id')
        dry_run = options.get('dry_run')
        rate_limit = options.get('rate_limit')

        # Get publications to process
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                publications = Publication.objects.filter(owner=user)
                self.stdout.write(f"Processing publications for user: {user.username}")
            except User.DoesNotExist:
                raise CommandError(f"User with ID {user_id} not found")
        else:
            publications = Publication.objects.all()
            self.stdout.write("Processing publications for all users")

        if not publications.exists():
            self.stdout.write(self.style.WARNING("No publications found"))
            return

        self.stdout.write(f"Found {publications.count()} publications to process")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Collect all unique authors
        authors_to_lookup = {}  # author_name -> list of (publication_id, author_index)
        updated_count = 0
        already_has_scopus_count = 0

        self.stdout.write("\nScanning publications for authors...")
        
        for pub in publications:
            if not pub.authors:
                continue
                
            for i, author in enumerate(pub.authors):
                if not isinstance(author, dict):
                    continue
                
                author_name = author.get('name', '').strip()
                if not author_name or author_name.lower() in ['unknown', 'unknown author']:
                    continue
                    
                # Skip if already has Scopus ID
                if author.get('scopus_id'):
                    already_has_scopus_count += 1
                    continue
                
                # Add to lookup list
                if author_name not in authors_to_lookup:
                    authors_to_lookup[author_name] = []
                authors_to_lookup[author_name].append((pub.id, i))

        self.stdout.write(f"Found {len(authors_to_lookup)} unique authors to lookup")
        self.stdout.write(f"Authors already with Scopus IDs: {already_has_scopus_count}")

        if not authors_to_lookup:
            self.stdout.write(self.style.SUCCESS("All authors already have Scopus IDs!"))
            return

        # Lookup Scopus IDs for each unique author
        successful_lookups = 0
        failed_lookups = 0
        
        for author_name, publication_locations in authors_to_lookup.items():
            self.stdout.write(f"\nLooking up Scopus ID for: {author_name}")
            
            try:
                scopus_id = self.lookup_author_scopus_id(author_name)
                
                if scopus_id:
                    self.stdout.write(f"  Found Scopus ID: {scopus_id}")
                    successful_lookups += 1
                    
                    # Update all publications with this author
                    for pub_id, author_index in publication_locations:
                        if not dry_run:
                            self.update_author_scopus_id(pub_id, author_index, scopus_id)
                        updated_count += 1
                        
                else:
                    self.stdout.write(f"  No Scopus ID found")
                    failed_lookups += 1
                
                # Rate limiting
                time.sleep(rate_limit)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error: {str(e)}"))
                failed_lookups += 1
                time.sleep(rate_limit)  # Still wait on errors

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== SUMMARY ===\n"
                f"Successful lookups: {successful_lookups}\n"
                f"Failed lookups: {failed_lookups}\n"
                f"Author records updated: {updated_count}\n"
                f"Already had Scopus IDs: {already_has_scopus_count}"
            )
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No actual changes were made"))

    def lookup_author_scopus_id(self, author_name):
        """
        Lookup Scopus ID for an author by name
        Uses author name search in Scopus
        """
        try:
            # Try searching for the author by name
            # Format: "AUTHOR-NAME(lastname, firstname)"
            name_parts = author_name.split(',')
            if len(name_parts) >= 2:
                lastname = name_parts[0].strip()
                firstname = name_parts[1].strip()
                search_query = f'AUTHOR-NAME("{lastname}, {firstname}")'
            else:
                # Try with full name
                search_query = f'AUTHOR-NAME("{author_name}")'
            
            self.stdout.write(f"    Searching: {search_query}")
            
            # Search for publications by this author
            search = ScopusSearch(search_query, subscriber=False)
            
            if search.results is None or len(search.results) == 0:
                return None
                
            # Get the first result and extract author information
            first_result = search.results[0]
            
            # Try to find the matching author in the author list
            if hasattr(first_result, 'author_ids') and first_result.author_ids:
                author_ids = first_result.author_ids.split(';')
                
                if hasattr(first_result, 'author_names') and first_result.author_names:
                    author_names = first_result.author_names.split(';')
                    
                    # Find the best matching author
                    for i, result_author_name in enumerate(author_names):
                        if self.names_match(author_name, result_author_name.strip()):
                            if i < len(author_ids):
                                return author_ids[i].strip()
                
                # Fallback: return first author ID if name matching fails
                return author_ids[0].strip()
                
            return None
            
        except Exception as e:
            logger.warning(f"Error looking up Scopus ID for {author_name}: {str(e)}")
            return None

    def names_match(self, name1, name2):
        """
        Check if two author names likely refer to the same person
        """
        # Simple matching logic - can be enhanced
        name1_clean = self.clean_name(name1)
        name2_clean = self.clean_name(name2)
        
        # Exact match
        if name1_clean == name2_clean:
            return True
            
        # Try matching last name + first initial
        parts1 = name1_clean.split(',')
        parts2 = name2_clean.split(',')
        
        if len(parts1) >= 2 and len(parts2) >= 2:
            lastname1 = parts1[0].strip()
            lastname2 = parts2[0].strip()
            
            if lastname1.lower() == lastname2.lower():
                # Check first initial
                firstname1 = parts1[1].strip()
                firstname2 = parts2[1].strip()
                
                if (len(firstname1) > 0 and len(firstname2) > 0 and 
                    firstname1[0].lower() == firstname2[0].lower()):
                    return True
        
        return False

    def clean_name(self, name):
        """Clean author name for comparison"""
        # Remove extra spaces, normalize punctuation
        return ' '.join(name.replace('.', '').split())

    def update_author_scopus_id(self, publication_id, author_index, scopus_id):
        """Update the Scopus ID for a specific author in a publication"""
        try:
            publication = Publication.objects.get(id=publication_id)
            
            if author_index < len(publication.authors):
                publication.authors[author_index]['scopus_id'] = scopus_id
                
                # Mark as manually edited to preserve this information
                if not publication.manual_edits:
                    publication.manual_edits = {}
                publication.manual_edits['authors'] = True
                
                publication.save()
                
        except Publication.DoesNotExist:
            logger.error(f"Publication {publication_id} not found")
        except Exception as e:
            logger.error(f"Error updating publication {publication_id}: {str(e)}")