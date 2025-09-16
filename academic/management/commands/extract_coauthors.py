"""
Django management command to extract coauthor information from publications
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import models
from pybliometrics.scopus import AuthorRetrieval
import pybliometrics

from academic.models import Publication
from academic.utils import init_pybliometrics

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Extract coauthor Scopus IDs and information from existing publications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to extract coauthors for'
        )
        parser.add_argument(
            '--output-format',
            choices=['json', 'csv'],
            default='json',
            help='Output format for coauthor data'
        )
        parser.add_argument(
            '--output-file',
            type=str,
            help='File to save coauthor data to'
        )
        parser.add_argument(
            '--min-collaborations',
            type=int,
            default=1,
            help='Minimum number of collaborations to include coauthor'
        )

    def handle(self, *args, **options):
        # Initialize Scopus
        try:
            init_pybliometrics()
        except Exception as e:
            raise CommandError(f"Failed to initialize Scopus: {str(e)}")

        user_id = options.get('user_id')
        output_format = options.get('output_format')
        output_file = options.get('output_file')
        min_collaborations = options.get('min_collaborations')

        if not user_id:
            raise CommandError("User ID is required (--user-id)")

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise CommandError(f"User with ID {user_id} not found")

        self.stdout.write(f"Extracting coauthors for user: {user.username}")

        # Get all publications for the user
        publications = Publication.objects.filter(owner=user)
        
        if not publications.exists():
            self.stdout.write(self.style.WARNING("No publications found for user"))
            return

        self.stdout.write(f"Processing {publications.count()} publications")

        # Extract coauthors
        coauthors = self.extract_coauthors_from_publications(publications, user)

        # Filter by minimum collaborations
        filtered_coauthors = {
            scopus_id: info for scopus_id, info in coauthors.items()
            if info['num_publications'] >= min_collaborations
        }

        self.stdout.write(
            self.style.SUCCESS(
                f"Found {len(coauthors)} unique coauthors\n"
                f"After filtering (min {min_collaborations} collaborations): {len(filtered_coauthors)}"
            )
        )

        # Output results
        if output_file:
            self.save_coauthors_to_file(filtered_coauthors, output_file, output_format)
        else:
            self.display_coauthors(filtered_coauthors)

    def extract_coauthors_from_publications(self, publications, user):
        """Extract coauthor information from publications"""
        coauthors = {}
        
        for publication in publications:
            if not publication.authors:
                continue
                
            # Process each author in the publication
            for author in publication.authors:
                if not isinstance(author, dict):
                    continue
                
                scopus_id = author.get('scopus_id')
                if not scopus_id:
                    continue
                
                # Skip if this is the user themselves
                if user.scopus_id and scopus_id == user.scopus_id:
                    continue
                
                if scopus_id not in coauthors:
                    # First time seeing this coauthor, get their info
                    try:
                        author_info = self.get_author_info(scopus_id)
                        if author_info:
                            coauthors[scopus_id] = {
                                'scopus_id': scopus_id,
                                'name': author_info.get('name', author.get('name', 'Unknown')),
                                'indexed_name': author_info.get('indexed_name'),
                                'affiliation': author_info.get('affiliation'),
                                'affiliation_id': author_info.get('affiliation_id'),
                                'first_collaboration': publication.year,
                                'last_collaboration': publication.year,
                                'num_publications': 1,
                                'collaborations': [publication.year],
                                'publication_titles': [publication.title[:100]]
                            }
                        else:
                            # Fallback if we can't get Scopus info
                            coauthors[scopus_id] = {
                                'scopus_id': scopus_id,
                                'name': author.get('name', 'Unknown'),
                                'indexed_name': None,
                                'affiliation': None,
                                'affiliation_id': None,
                                'first_collaboration': publication.year,
                                'last_collaboration': publication.year,
                                'num_publications': 1,
                                'collaborations': [publication.year],
                                'publication_titles': [publication.title[:100]]
                            }
                    except Exception as e:
                        logger.warning(f"Error getting info for author {scopus_id}: {str(e)}")
                        continue
                else:
                    # Update existing coauthor record
                    coauthor = coauthors[scopus_id]
                    coauthor['num_publications'] += 1
                    coauthor['collaborations'].append(publication.year)
                    coauthor['publication_titles'].append(publication.title[:100])
                    
                    if publication.year < coauthor['first_collaboration']:
                        coauthor['first_collaboration'] = publication.year
                    if publication.year > coauthor['last_collaboration']:
                        coauthor['last_collaboration'] = publication.year

        return coauthors

    def get_author_info(self, scopus_id):
        """Get author information from Scopus"""
        try:
            author = AuthorRetrieval(scopus_id)
            
            if not author.indexed_name:
                return None
            
            # Get affiliation info
            affiliation = None
            affiliation_id = None
            
            if author.affiliation_current:
                affiliations = []
                affiliation_ids = []
                
                for aff in author.affiliation_current:
                    if aff.parent_preferred_name:
                        aff_str = f'{aff.preferred_name}, {aff.parent_preferred_name}, {aff.city}, {aff.country}'
                    else:
                        aff_str = f'{aff.preferred_name}, {aff.city}, {aff.country}'
                    affiliations.append(aff_str)
                    affiliation_ids.append(aff.id)
                
                affiliation = affiliations
                affiliation_id = affiliation_ids
            
            return {
                'name': author.indexed_name,
                'indexed_name': author.indexed_name,
                'affiliation': affiliation,
                'affiliation_id': affiliation_id
            }
            
        except Exception as e:
            logger.warning(f"Error retrieving author {scopus_id}: {str(e)}")
            return None

    def save_coauthors_to_file(self, coauthors, output_file, output_format):
        """Save coauthor data to file"""
        if output_format == 'json':
            import json
            with open(output_file, 'w') as f:
                json.dump(coauthors, f, indent=2, default=str)
            self.stdout.write(f"Coauthor data saved to {output_file} (JSON format)")
            
        elif output_format == 'csv':
            import csv
            with open(output_file, 'w', newline='') as f:
                if coauthors:
                    # Get all possible field names
                    fieldnames = set()
                    for coauthor in coauthors.values():
                        fieldnames.update(coauthor.keys())
                    fieldnames = sorted(list(fieldnames))
                    
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for coauthor in coauthors.values():
                        # Convert lists to strings for CSV
                        row = {}
                        for field, value in coauthor.items():
                            if isinstance(value, list):
                                row[field] = '; '.join(map(str, value))
                            else:
                                row[field] = value
                        writer.writerow(row)
                        
            self.stdout.write(f"Coauthor data saved to {output_file} (CSV format)")

    def display_coauthors(self, coauthors):
        """Display coauthor data in the console"""
        self.stdout.write("\n" + "="*80)
        self.stdout.write("COAUTHOR SUMMARY")
        self.stdout.write("="*80)
        
        # Sort by number of publications (descending)
        sorted_coauthors = sorted(
            coauthors.items(),
            key=lambda x: x[1]['num_publications'],
            reverse=True
        )
        
        for scopus_id, info in sorted_coauthors:
            self.stdout.write(f"\nScopus ID: {scopus_id}")
            self.stdout.write(f"Name: {info['name']}")
            self.stdout.write(f"Publications: {info['num_publications']}")
            self.stdout.write(f"Collaboration period: {info['first_collaboration']}-{info['last_collaboration']}")
            
            if info['affiliation']:
                if isinstance(info['affiliation'], list):
                    self.stdout.write(f"Affiliations: {'; '.join(info['affiliation'])}")
                else:
                    self.stdout.write(f"Affiliation: {info['affiliation']}")
            
            # Show first few publication titles
            if info['publication_titles']:
                titles = info['publication_titles'][:3]  # Show first 3
                self.stdout.write(f"Sample publications: {'; '.join(titles)}")
                if len(info['publication_titles']) > 3:
                    self.stdout.write(f"... and {len(info['publication_titles']) - 3} more")
            
            self.stdout.write("-" * 40)