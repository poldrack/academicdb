"""
Django management command to sync publications from PubMed
"""
import logging
import re
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth import get_user_model
from Bio import Entrez
import requests

from academic.models import Publication

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = 'Sync publications from PubMed for a specific user'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to sync PubMed data for'
        )
        parser.add_argument(
            '--query',
            type=str,
            help='PubMed query to use (overrides user profile)'
        )
        parser.add_argument(
            '--max-results',
            type=int,
            default=1000,
            help='Maximum number of publications to fetch'
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        query = options.get('query')
        max_results = options.get('max_results')

        if not user_id:
            raise CommandError("User ID is required (--user-id)")

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise CommandError(f"User with ID {user_id} not found")

        # Use provided query or get from user profile
        if not query:
            query = user.pubmed_query

        if not query or not query.strip():
            raise CommandError(f"No PubMed query found for user {user.username}. Please provide --query or set in profile.")

        self.stdout.write(f"Starting PubMed sync for user: {user.username}")
        self.stdout.write(f"Using query: {query}")

        # Set email for Entrez
        Entrez.email = user.email or 'noreply@example.com'

        try:
            # Get publications from PubMed
            publications_data = self.fetch_pubmed_publications(query, max_results)
            
            if not publications_data:
                self.stdout.write(self.style.WARNING("No publications found in PubMed"))
                return

            # Import publications
            created_count, updated_count, error_count = self.import_publications(
                user, publications_data
            )

            # Update user's last sync time
            user.last_orcid_sync = timezone.now()  # Using same field for simplicity
            user.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"PubMed sync completed successfully!\n"
                    f"Created: {created_count} publications\n"
                    f"Updated: {updated_count} publications\n"
                    f"Errors: {error_count} publications"
                )
            )

        except Exception as e:
            logger.error(f"PubMed sync failed for user {user_id}: {str(e)}")
            raise CommandError(f"Sync failed: {str(e)}")

    def fetch_pubmed_publications(self, query, max_results):
        """Fetch publications from PubMed using the query"""
        try:
            self.stdout.write(f"Searching PubMed with query: {query}")
            
            # Search for PMIDs
            search_handle = Entrez.esearch(
                db='pubmed', 
                term=query, 
                retmax=max_results
            )
            search_result = Entrez.read(search_handle)
            search_handle.close()
            
            pmids = search_result['IdList']
            self.stdout.write(f"Found {len(pmids)} publications in PubMed")
            
            if not pmids:
                return []

            # Fetch full records
            fetch_handle = Entrez.efetch(
                db='pubmed',
                id=','.join(pmids),
                retmax=max_results,
                retmode='xml'
            )
            
            publications = Entrez.read(fetch_handle)
            fetch_handle.close()
            
            return publications.get('PubmedArticle', [])
            
        except Exception as e:
            logger.error(f"Error fetching PubMed data: {str(e)}")
            raise

    def import_publications(self, user, publications_data):
        """Import publications into the database"""
        created_count = 0
        updated_count = 0
        error_count = 0

        for pub_data in publications_data:
            try:
                # Parse PubMed record
                parsed_data = self.parse_pubmed_record(pub_data)
                
                if not parsed_data:
                    error_count += 1
                    continue
                    
                doi = parsed_data.get('DOI')
                if doi:
                    doi = doi.lower().strip()  # Normalize DOI to lowercase
                    # Replace repeated slashes with single slash
                    doi = re.sub(r'/+', '/', doi)

                    # Check if DOI should be skipped based on user preferences
                    skip_dois = user.get_skip_dois_list()
                    if doi in skip_dois:
                        self.stdout.write(f"Skipping DOI (in user skip list): {doi}")
                        continue

                pmid = parsed_data.get('PMID')
                
                if not doi and not pmid:
                    self.stdout.write(
                        self.style.WARNING(f"Skipping publication without DOI or PMID: {parsed_data.get('title', 'Unknown')}")
                    )
                    error_count += 1
                    continue

                # Use DOI as primary identifier, fall back to PMID-based identifier
                identifier = doi if doi else f"pmid_{pmid}"

                # Build authors list
                authors = self.parse_authors(parsed_data.get('authors', ''))

                # Build identifiers
                identifiers = {}
                if pmid:
                    identifiers['pmid'] = str(pmid)
                if parsed_data.get('PMC'):
                    identifiers['pmcid'] = parsed_data['PMC']

                # Build metadata
                metadata = {
                    'source': 'pubmed',
                    'raw_data': {
                        'abstract': parsed_data.get('abstract'),
                        'volume': parsed_data.get('volume'),
                        'pages': parsed_data.get('page'),
                        'publication_date': parsed_data.get('publication-date'),
                    }
                }

                # Check if publication exists
                existing_pub = None
                if doi:
                    existing_pub = Publication.objects.filter(owner=user, doi=doi).first()
                
                if not existing_pub and pmid:
                    existing_pub = Publication.objects.filter(
                        owner=user, 
                        identifiers__pmid=str(pmid)
                    ).first()

                if existing_pub:
                    # Update existing publication with PubMed data
                    self.update_existing_publication(existing_pub, parsed_data, identifiers, metadata)
                    updated_count += 1
                    self.stdout.write(f"Updated: {parsed_data.get('title', 'Unknown')}")
                else:
                    # Create new publication
                    new_pub = Publication(
                        owner=user,
                        doi=doi,
                        title=parsed_data.get('title', 'Unknown Title'),
                        year=parsed_data.get('year', datetime.now().year),
                        publication_name=parsed_data.get('journal', ''),
                        publication_type='journal-article',  # PubMed is primarily journal articles
                        volume=parsed_data.get('volume'),
                        page_range=parsed_data.get('page'),
                        source='pubmed',
                        metadata=metadata,
                        authors=authors,
                        identifiers=identifiers,
                        last_api_sync=timezone.now()
                    )
                    
                    # Set publication date if available
                    if parsed_data.get('publication-date'):
                        try:
                            pub_date = datetime.strptime(parsed_data['publication-date'], '%Y-%m-%d').date()
                            new_pub.publication_date = pub_date
                        except (ValueError, TypeError):
                            pass
                    
                    new_pub.save()
                    created_count += 1
                    self.stdout.write(f"Created: {parsed_data.get('title', 'Unknown')}")

            except Exception as e:
                logger.error(f"Error processing publication: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f"Error processing publication: {str(e)}")
                )
                error_count += 1
                continue

        return created_count, updated_count, error_count

    def parse_pubmed_record(self, record):
        """Parse a single PubMed record"""
        try:
            return {
                'DOI': self.get_pubmed_doi(record),
                'abstract': self.get_pubmed_abstract(record),
                'PMC': self.get_pubmed_pmcid(record),
                'PMID': self.get_pubmed_pmid(record),
                'journal': self.get_pubmed_journal_name(record),
                'year': self.get_pubmed_year(record),
                'publication-date': self.get_pubmed_date(record),
                'volume': self.get_pubmed_volume(record),
                'title': self.get_pubmed_title(record),
                'page': self.get_pubmed_pages(record),
                'authors': self.get_pubmed_authors(record),
            }
        except Exception as e:
            logger.error(f"Error parsing PubMed record: {str(e)}")
            return None

    def parse_authors(self, authors_string):
        """Parse authors string into list of dictionaries"""
        if not authors_string:
            return [{'name': 'Unknown Author'}]
        
        authors = []
        for author in authors_string.split(', '):
            authors.append({'name': author.strip()})
        
        return authors

    def update_existing_publication(self, publication, parsed_data, identifiers, metadata):
        """Update existing publication with PubMed data"""
        # Update identifiers (preserve existing, add new)
        if not publication.identifiers:
            publication.identifiers = {}
        publication.identifiers.update(identifiers)
        
        # Update metadata (preserve existing, add new)
        if not publication.metadata:
            publication.metadata = {}
        publication.metadata.update(metadata)
        
        # Add PMC ID if available and not already set
        if parsed_data.get('PMC') and not publication.identifiers.get('pmcid'):
            publication.identifiers['pmcid'] = parsed_data['PMC']
        
        # Update abstract if not present
        if parsed_data.get('abstract') and not publication.metadata.get('abstract'):
            publication.metadata['abstract'] = parsed_data['abstract']

        # Update volume and page_range if available and not manually edited
        if parsed_data.get('volume') and not publication.manual_edits.get('volume', False):
            publication.volume = parsed_data['volume']
        if parsed_data.get('page') and not publication.manual_edits.get('page_range', False):
            publication.page_range = parsed_data['page']

        publication.last_api_sync = timezone.now()
        publication.save()

    # PubMed parsing functions (from original codebase)
    def get_pubmed_doi(self, record):
        doi = None
        if 'PubmedData' in record and 'ArticleIdList' in record['PubmedData']:
            for article_id in record['PubmedData']['ArticleIdList']:
                if hasattr(article_id, 'attributes') and article_id.attributes.get('IdType') == 'doi':
                    doi = str(article_id).lower().replace('http://dx.doi.org/', '')
                    # Replace repeated slashes with single slash
                    doi = re.sub(r'/+', '/', doi)
                    break
        return doi

    def get_pubmed_pmcid(self, record):
        pmc = None
        if 'PubmedData' in record and 'ArticleIdList' in record['PubmedData']:
            for article_id in record['PubmedData']['ArticleIdList']:
                if hasattr(article_id, 'attributes') and article_id.attributes.get('IdType') == 'pmc':
                    pmc = str(article_id)
                    break
        return pmc

    def get_pubmed_pmid(self, record):
        if 'MedlineCitation' in record and 'PMID' in record['MedlineCitation']:
            return int(record['MedlineCitation']['PMID'])
        return None

    def get_pubmed_title(self, record):
        if ('MedlineCitation' in record and 'Article' in record['MedlineCitation'] 
            and 'ArticleTitle' in record['MedlineCitation']['Article']):
            return record['MedlineCitation']['Article']['ArticleTitle']
        return None

    def get_pubmed_journal_name(self, record):
        if ('MedlineCitation' in record and 'Article' in record['MedlineCitation'] 
            and 'Journal' in record['MedlineCitation']['Article']
            and 'ISOAbbreviation' in record['MedlineCitation']['Article']['Journal']):
            return record['MedlineCitation']['Article']['Journal']['ISOAbbreviation']
        return None

    def get_pubmed_year(self, record):
        year = None
        if ('MedlineCitation' in record and 'Article' in record['MedlineCitation'] 
            and 'Journal' in record['MedlineCitation']['Article']
            and 'JournalIssue' in record['MedlineCitation']['Article']['Journal']
            and 'PubDate' in record['MedlineCitation']['Article']['Journal']['JournalIssue']):
            
            pub_date = record['MedlineCitation']['Article']['Journal']['JournalIssue']['PubDate']
            
            if 'Year' in pub_date:
                year = int(pub_date['Year'])
            elif 'MedlineDate' in pub_date:
                year = int(pub_date['MedlineDate'].split(' ')[0])
        
        return year or datetime.now().year

    def get_pubmed_volume(self, record):
        if ('MedlineCitation' in record and 'Article' in record['MedlineCitation'] 
            and 'Journal' in record['MedlineCitation']['Article']
            and 'JournalIssue' in record['MedlineCitation']['Article']['Journal']
            and 'Volume' in record['MedlineCitation']['Article']['Journal']['JournalIssue']):
            return record['MedlineCitation']['Article']['Journal']['JournalIssue']['Volume']
        return None

    def get_pubmed_pages(self, record):
        if ('MedlineCitation' in record and 'Article' in record['MedlineCitation'] 
            and 'Pagination' in record['MedlineCitation']['Article']
            and 'MedlinePgn' in record['MedlineCitation']['Article']['Pagination']):
            return record['MedlineCitation']['Article']['Pagination']['MedlinePgn']
        return None

    def get_pubmed_authors(self, record):
        authors = None
        if ('MedlineCitation' in record and 'Article' in record['MedlineCitation'] 
            and 'AuthorList' in record['MedlineCitation']['Article']):
            
            author_list = []
            for author in record['MedlineCitation']['Article']['AuthorList']:
                if 'LastName' in author and 'Initials' in author:
                    author_list.append(f"{author['LastName']} {author['Initials']}")
                elif 'LastName' in author:
                    author_list.append(author['LastName'])
            
            authors = ', '.join(author_list)
        
        return authors

    def get_pubmed_abstract(self, record):
        abstract = None
        if ('MedlineCitation' in record and 'Article' in record['MedlineCitation'] 
            and 'Abstract' in record['MedlineCitation']['Article']
            and 'AbstractText' in record['MedlineCitation']['Article']['Abstract']):
            
            abstract_text = record['MedlineCitation']['Article']['Abstract']['AbstractText']
            if isinstance(abstract_text, list):
                abstract = ' '.join(str(text) for text in abstract_text)
            else:
                abstract = str(abstract_text)
        
        return abstract

    def get_pubmed_date(self, record):
        """Get publication date as YYYY-MM-DD string"""
        date_str = None
        
        # Try ArticleDate first
        if ('MedlineCitation' in record and 'Article' in record['MedlineCitation'] 
            and 'ArticleDate' in record['MedlineCitation']['Article']
            and len(record['MedlineCitation']['Article']['ArticleDate']) > 0):
            
            date_info = record['MedlineCitation']['Article']['ArticleDate'][0]
            date_str = self.convert_to_datestring(date_info)
            
        # Fall back to Journal PubDate
        elif ('MedlineCitation' in record and 'Article' in record['MedlineCitation'] 
              and 'Journal' in record['MedlineCitation']['Article']
              and 'JournalIssue' in record['MedlineCitation']['Article']['Journal']
              and 'PubDate' in record['MedlineCitation']['Article']['Journal']['JournalIssue']
              and 'Year' in record['MedlineCitation']['Article']['Journal']['JournalIssue']['PubDate']):
            
            date_info = record['MedlineCitation']['Article']['Journal']['JournalIssue']['PubDate']
            date_str = self.convert_to_datestring(date_info)
        
        return date_str

    def convert_to_datestring(self, date_struct):
        """Convert PubMed date structure to YYYY-MM-DD string"""
        year = date_struct.get('Year', str(datetime.now().year))
        month = date_struct.get('Month', '12')
        day = date_struct.get('Day', '31')
        
        # Convert month name to number if needed
        if month and not month.isdigit():
            try:
                month = str(datetime.strptime(month, '%b').month)
            except ValueError:
                month = '12'
        
        # Ensure we have valid values
        year = int(year)
        month = max(1, min(12, int(month))) if month else 12
        day = max(1, min(31, int(day))) if day else 31
        
        return f"{year:04d}-{month:02d}-{day:02d}"