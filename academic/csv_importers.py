"""
Unified CSV import architecture

This module provides a single source of truth for all CSV import logic,
eliminating duplication between API ViewSets and data_ingestion.py.

Required CSV Formats for Each Table:

1. Publications:
   - Required columns: title
   - Optional columns: type, year, authors, journal, volume, page, DOI, publisher, ISBN, editors
   - Example: title,year,authors,journal,DOI
             "My Paper",2023,"John Doe, Jane Smith","Nature","10.1234/nature.123"

2. Teaching:
   - Required columns: name
   - Optional columns: level
   - Example: level,name
             "Undergraduate","Introduction to Psychology"

3. Talks:
   - Required columns: year, place
   - Optional columns: invited
   - Example: year,place,invited
             "2023","Stanford University","true"

4. Conferences:
   - Required columns: authors, year, title
   - Optional columns: location, month, link
   - Example: authors,year,title,location,month,link
             "John Doe","2023","My Presentation","New York","June","https://example.com"

5. Editorial:
   - Required columns: role, journal
   - Optional columns: dates
   - Example: role,journal,dates
             "editor","Nature Reviews","2023-2024"

All CSV files support UTF-8 encoding with BOM and will validate column names before processing.
"""
import csv
import io
from django.db import transaction
from .models import Publication, Teaching, Talk, Conference, Editorial


class CSVImporter:
    """
    Base class for CSV importers with common functionality
    """

    def __init__(self):
        self.model = self.get_model()

    def get_model(self):
        """Override in subclasses to return the model class"""
        raise NotImplementedError("Subclasses must implement get_model()")

    def map_csv_row(self, row):
        """Override in subclasses to map CSV row to model fields"""
        raise NotImplementedError("Subclasses must implement map_csv_row()")

    def get_required_columns(self):
        """Override in subclasses to return required column names"""
        return []

    def get_optional_columns(self):
        """Override in subclasses to return optional column names"""
        return []

    def validate_csv_columns(self, columns):
        """
        Validate that CSV has required columns

        Args:
            columns: List of column names from CSV header

        Returns:
            dict: Validation result with 'valid' boolean and 'error' message
        """
        required_cols = self.get_required_columns()
        optional_cols = self.get_optional_columns()
        all_valid_cols = set(required_cols + optional_cols)

        # Check for required columns
        missing_required = set(required_cols) - set(columns)
        if missing_required:
            return {
                'valid': False,
                'error': f'Missing required columns: {", ".join(sorted(missing_required))}'
            }

        # Check for invalid columns
        invalid_cols = set(columns) - all_valid_cols
        if invalid_cols:
            return {
                'valid': False,
                'error': f'Invalid columns: {", ".join(sorted(invalid_cols))}. Valid columns are: {", ".join(sorted(all_valid_cols))}'
            }

        return {'valid': True}

    def import_csv(self, user, csv_file):
        """
        Import data from CSV file using unified logic

        Args:
            user: The user who owns the imported data
            csv_file: Django UploadedFile object or file-like object

        Returns:
            dict: Import results with created, updated, errors counts
        """
        if not csv_file:
            return {'error': 'No file provided'}

        if not csv_file.name.endswith('.csv'):
            return {'error': 'File must be a CSV'}

        try:
            # Handle both uploaded files and string content
            if hasattr(csv_file, 'read'):
                decoded_file = csv_file.read().decode('utf-8-sig')  # Handle BOM
            else:
                decoded_file = csv_file

            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            # Validate CSV columns
            if reader.fieldnames:
                validation = self.validate_csv_columns(reader.fieldnames)
                if not validation['valid']:
                    return {'error': validation['error']}

            created_items = []
            updated_items = []
            errors = []

            with transaction.atomic():
                for i, row in enumerate(reader):
                    try:
                        # Map CSV fields to model fields
                        item_data = self.map_csv_row(row)

                        # Skip empty rows
                        if not self._is_valid_row(item_data):
                            continue

                        # Check for existing item
                        existing = self._find_existing_item(user, item_data)

                        if existing:
                            # Update existing item
                            for field, value in item_data.items():
                                setattr(existing, field, value)
                            existing.source = 'csv_import'
                            existing.save()
                            updated_items.append(existing.id)
                        else:
                            # Create new item
                            item_data['owner'] = user
                            item_data['source'] = 'csv_import'
                            instance = self.model.objects.create(**item_data)
                            created_items.append(instance.id)

                    except Exception as e:
                        errors.append({
                            'row': i + 2,  # +2 because of header and 0-indexing
                            'error': str(e)
                        })

            return {
                'created': len(created_items),
                'updated': len(updated_items),
                'errors': errors,
                'created_ids': created_items,
                'updated_ids': updated_items
            }

        except Exception as e:
            return {'error': f'Failed to process CSV: {str(e)}'}

    def _is_valid_row(self, item_data):
        """Check if row contains valid data"""
        # Override in subclasses for specific validation logic
        return any(value for value in item_data.values() if value)

    def _find_existing_item(self, user, item_data):
        """Find existing item for potential update"""
        # Default implementation - override in subclasses for specific logic
        return None


class PublicationCSVImporter(CSVImporter):
    """CSV importer for publications"""

    def get_model(self):
        return Publication

    def get_required_columns(self):
        return ['title']

    def get_optional_columns(self):
        return ['type', 'year', 'authors', 'journal', 'volume', 'page', 'DOI', 'publisher', 'ISBN', 'editors']

    def map_csv_row(self, row):
        """
        Map CSV row to Publication model fields
        Expected CSV format: type,year,authors,title,journal,volume,page,DOI,publisher,ISBN,editors
        """
        # Parse authors string into list format expected by the model
        authors_str = row.get('authors', '').strip()
        authors_list = []
        if authors_str:
            # Split by comma and create author objects
            author_names = [name.strip() for name in authors_str.split(',')]
            authors_list = [{'name': name} for name in author_names if name]

        # Map publication type to valid model choices
        pub_type = row.get('type', '').strip()
        if pub_type == 'proceedings-article':
            pub_type = 'conference-paper'
        elif pub_type not in ['journal-article', 'conference-paper', 'book', 'book-chapter', 'preprint', 'thesis', 'patent', 'report', 'dataset', 'software']:
            pub_type = 'other'

        # Determine publication name based on type
        publication_name = ''
        if pub_type in ['journal-article', 'conference-paper']:
            publication_name = row.get('journal', '').strip()
        elif pub_type == 'book':
            publication_name = row.get('publisher', '').strip()
        elif pub_type == 'book-chapter':
            publication_name = row.get('title', '').strip()

        # Parse year
        year = None
        try:
            year_str = row.get('year', '').strip()
            if year_str:
                year = int(year_str)
        except (ValueError, TypeError):
            pass

        # Clean DOI
        doi = row.get('DOI', '').strip()
        if doi and not doi.startswith('10.'):
            doi = ''  # Invalid DOI format

        return {
            'title': row.get('title', '').strip(),
            'year': year,
            'publication_type': pub_type or 'other',
            'publication_name': publication_name,
            'doi': doi or None,
            'authors': authors_list,
        }

    def _is_valid_row(self, item_data):
        """Publication is valid if it has title or DOI"""
        return item_data.get('title') or item_data.get('doi')

    def _find_existing_item(self, user, item_data):
        """Find existing publication by DOI"""
        doi = item_data.get('doi')
        if doi:
            return Publication.objects.filter(owner=user, doi=doi).first()
        return None


class TeachingCSVImporter(CSVImporter):
    """CSV importer for teaching records"""

    def get_model(self):
        return Teaching

    def get_required_columns(self):
        return []  # No truly required columns since either 'name' or 'course_name' can work

    def get_optional_columns(self):
        return ['level', 'course_name', 'name']  # Accept both 'name' and 'course_name'

    def map_csv_row(self, row):
        """
        Map CSV row to Teaching model fields
        Expected CSV format: level,name
        """
        level = row.get('level', '').strip()
        if level not in ['Undergraduate', 'Graduate']:
            level = 'Undergraduate'  # Default value

        return {
            'level': level,
            'name': row.get('name', '').strip() or row.get('course_name', '').strip(),  # Support both 'name' and 'course_name'
        }

    def _is_valid_row(self, item_data):
        """Teaching is valid if it has a name"""
        return bool(item_data.get('name'))

    def _find_existing_item(self, user, item_data):
        """Find existing teaching by name and level"""
        return Teaching.objects.filter(
            owner=user,
            name=item_data.get('name'),
            level=item_data.get('level')
        ).first()


class TalkCSVImporter(CSVImporter):
    """CSV importer for talks"""

    def get_model(self):
        return Talk

    def get_required_columns(self):
        return ['year', 'place']

    def get_optional_columns(self):
        return ['invited']

    def map_csv_row(self, row):
        """
        Map CSV row to Talk model fields
        Expected CSV format: year,place (with optional invited)
        """
        # Parse year
        year = None
        try:
            year_str = row.get('year', '').strip()
            if year_str:
                year = int(year_str)
        except (ValueError, TypeError):
            pass

        # Parse invited field
        invited = True  # Default to invited
        invited_str = row.get('invited', '').strip().lower()
        if invited_str in ['false', 'no', '0', 'f']:
            invited = False

        return {
            'place': row.get('place', '').strip(),
            'year': year,
            'invited': invited,
        }

    def _is_valid_row(self, item_data):
        """Talk is valid if it has year and place"""
        return bool(item_data.get('year')) and bool(item_data.get('place'))

    def _find_existing_item(self, user, item_data):
        """Find existing talk by year and place"""
        return Talk.objects.filter(
            owner=user,
            year=item_data.get('year'),
            place=item_data.get('place')
        ).first()


class ConferenceCSVImporter(CSVImporter):
    """CSV importer for conferences"""

    def get_model(self):
        return Conference

    def get_required_columns(self):
        return ['authors', 'year', 'title']

    def get_optional_columns(self):
        return ['location', 'month', 'link']

    def map_csv_row(self, row):
        """
        Map CSV row to Conference model fields
        Expected CSV format: authors,year,title,location,month,link
        """
        # Parse year
        year = None
        try:
            year_str = row.get('year', '').strip()
            if year_str:
                year = int(year_str)
        except (ValueError, TypeError):
            pass

        return {
            'authors': row.get('authors', '').strip(),
            'year': year,
            'title': row.get('title', '').strip(),
            'location': row.get('location', '').strip(),
            'month': row.get('month', '').strip(),
            'link': row.get('link', '').strip(),
        }

    def _is_valid_row(self, item_data):
        """Conference is valid if it has required fields"""
        return bool(item_data.get('authors')) and bool(item_data.get('year')) and bool(item_data.get('title'))

    def _find_existing_item(self, user, item_data):
        """Find existing conference by title and year"""
        return Conference.objects.filter(
            owner=user,
            title=item_data.get('title'),
            year=item_data.get('year')
        ).first()


class EditorialCSVImporter(CSVImporter):
    """CSV importer for editorial activities"""

    def get_model(self):
        return Editorial

    def get_required_columns(self):
        return ['role', 'journal']

    def get_optional_columns(self):
        return ['dates']

    def map_csv_row(self, row):
        """
        Map CSV row to Editorial model fields
        Expected CSV format: role,journal,dates
        """
        return {
            'role': row.get('role', '').strip(),
            'journal': row.get('journal', '').strip(),
            'dates': row.get('dates', '').strip(),
        }

    def _is_valid_row(self, item_data):
        """Editorial is valid if it has role and journal"""
        return bool(item_data.get('role')) and bool(item_data.get('journal'))

    def _find_existing_item(self, user, item_data):
        """Find existing editorial by role and journal"""
        return Editorial.objects.filter(
            owner=user,
            role=item_data.get('role'),
            journal=item_data.get('journal')
        ).first()


# Factory function to get the appropriate importer
def get_csv_importer(model_name):
    """
    Factory function to get the appropriate CSV importer for a model

    Args:
        model_name (str): Name of the model ('publication', 'teaching', etc.)

    Returns:
        CSVImporter: Appropriate importer instance
    """
    importers = {
        'publication': PublicationCSVImporter,
        'teaching': TeachingCSVImporter,
        'talk': TalkCSVImporter,
        'conference': ConferenceCSVImporter,
        'editorial': EditorialCSVImporter,
    }

    importer_class = importers.get(model_name.lower())
    if not importer_class:
        raise ValueError(f"No importer found for model: {model_name}")

    return importer_class()