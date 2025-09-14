"""
API views for academic models
"""
from rest_framework import viewsets, permissions, authentication, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import exception_handler
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.db import transaction
import csv
import io
import openpyxl
from .models import Publication, Teaching, Talk, Conference
from .serializers import PublicationSerializer, TeachingSerializer, TalkSerializer, ConferenceSerializer

User = get_user_model()


def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns 401 for authentication failures
    """
    response = exception_handler(exc, context)
    
    if response is not None:
        # Convert 403 (PermissionDenied) to 401 (Unauthorized) for authentication failures
        if response.status_code == 403:
            # Check if this is an authentication failure vs authorization failure
            request = context.get('request')
            user = getattr(request, 'user', None) if request else None
            
            if not user or not getattr(user, 'is_authenticated', False):
                response.status_code = status.HTTP_401_UNAUTHORIZED
                response.data = {'detail': 'Authentication credentials were not provided.'}
    
    return response


class IsAuthenticatedWith401(permissions.IsAuthenticated):
    """
    Custom permission that returns 401 instead of 403 for unauthenticated users
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            from rest_framework.exceptions import NotAuthenticated
            raise NotAuthenticated()
        return True


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination for API results"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 2000  # Increased to support large datasets in spreadsheets


class PublicationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user publications

    Provides CRUD operations for publications with user isolation
    """
    serializer_class = PublicationSerializer
    permission_classes = [IsAuthenticatedWith401]
    authentication_classes = [authentication.SessionAuthentication, authentication.TokenAuthentication]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """Return publications owned by the current user only"""
        return Publication.objects.filter(
            owner=self.request.user
        ).order_by('-created_at')

    def perform_create(self, serializer):
        """Set the owner to the current user when creating"""
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=['post'])
    def import_csv(self, request):
        """
        Import publications from CSV file
        Expected CSV format: type,year,authors,title,journal,volume,page,DOI,publisher,ISBN,editors
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        csv_file = request.FILES['file']

        if not csv_file.name.endswith('.csv'):
            return Response(
                {'error': 'File must be a CSV'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            decoded_file = csv_file.read().decode('utf-8')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            created_items = []
            updated_items = []
            errors = []

            with transaction.atomic():
                for i, row in enumerate(reader):
                    try:
                        # Map CSV fields to Publication model fields
                        pub_data = self._map_csv_row_to_publication(row)

                        # Skip empty rows
                        if not pub_data.get('title') and not pub_data.get('doi'):
                            continue

                        # Check for existing publication by DOI
                        doi = pub_data.get('doi')
                        if doi:
                            existing = self.get_queryset().filter(doi=doi).first()
                            if existing:
                                # Update existing publication
                                serializer = self.get_serializer(existing, data=pub_data, partial=True)
                                if serializer.is_valid():
                                    serializer.save()
                                    updated_items.append(existing.id)
                                else:
                                    errors.append({
                                        'row': i + 2,  # +2 because of header and 0-indexing
                                        'errors': serializer.errors
                                    })
                                continue

                        # Create new publication
                        serializer = self.get_serializer(data=pub_data)
                        if serializer.is_valid():
                            instance = serializer.save(owner=request.user)
                            created_items.append(instance.id)
                        else:
                            errors.append({
                                'row': i + 2,  # +2 because of header and 0-indexing
                                'errors': serializer.errors
                            })

                    except Exception as e:
                        errors.append({
                            'row': i + 2,
                            'error': str(e)
                        })

            return Response({
                'created': len(created_items),
                'updated': len(updated_items),
                'errors': errors,
                'created_ids': created_items,
                'updated_ids': updated_items
            })

        except Exception as e:
            return Response(
                {'error': f'Failed to process CSV: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _map_csv_row_to_publication(self, row):
        """
        Map CSV row to Publication model fields
        CSV format: type,year,authors,title,journal,volume,page,DOI,publisher,ISBN,editors
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
        # Valid types like 'journal-article', 'book-chapter', and 'book' stay the same

        # Determine publication name based on type
        publication_name = ''
        if pub_type in ['journal-article', 'conference-paper']:
            publication_name = row.get('journal', '').strip()
        elif pub_type == 'book':
            publication_name = row.get('publisher', '').strip()
        elif pub_type == 'book-chapter':
            publication_name = row.get('title', '').strip()  # For chapters, use the book title

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


class BaseBulkViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet with bulk operations for spreadsheet functionality
    """
    permission_classes = [IsAuthenticatedWith401]
    authentication_classes = [authentication.SessionAuthentication, authentication.TokenAuthentication]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """Return items owned by the current user only"""
        return self.get_model().objects.filter(
            owner=self.request.user
        ).order_by('-created_at')

    def perform_create(self, serializer):
        """Set the owner to the current user when creating"""
        serializer.save(owner=self.request.user)

    def get_model(self):
        """Override in subclasses to return the model class"""
        raise NotImplementedError("Subclasses must implement get_model()")

    @action(detail=False, methods=['patch'])
    def bulk_update(self, request):
        """
        Bulk update/create items from spreadsheet data
        """
        data = request.data
        if not isinstance(data, list):
            return Response(
                {'error': 'Expected a list of items'},
                status=status.HTTP_400_BAD_REQUEST
            )

        created_items = []
        updated_items = []
        errors = []

        with transaction.atomic():
            for i, item_data in enumerate(data):
                try:
                    # Check if this is an update (has ID) or create (no ID)
                    item_id = item_data.get('id')

                    if item_id:
                        # Update existing item
                        try:
                            instance = self.get_queryset().get(id=item_id)
                            serializer = self.get_serializer(instance, data=item_data, partial=True)
                        except self.get_model().DoesNotExist:
                            # ID provided but item doesn't exist, create new
                            item_data.pop('id', None)  # Remove invalid ID
                            serializer = self.get_serializer(data=item_data)
                    else:
                        # Create new item
                        serializer = self.get_serializer(data=item_data)

                    if serializer.is_valid():
                        instance = serializer.save(owner=request.user)
                        if item_id:
                            updated_items.append(instance.id)
                        else:
                            created_items.append(instance.id)
                    else:
                        errors.append({
                            'row': i + 1,
                            'errors': serializer.errors
                        })

                except Exception as e:
                    errors.append({
                        'row': i + 1,
                        'error': str(e)
                    })

        return Response({
            'created': len(created_items),
            'updated': len(updated_items),
            'errors': errors,
            'created_ids': created_items,
            'updated_ids': updated_items
        })

    @action(detail=False, methods=['post'])
    def import_csv(self, request):
        """
        Import data from CSV file
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        csv_file = request.FILES['file']

        if not csv_file.name.endswith('.csv'):
            return Response(
                {'error': 'File must be a CSV'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            decoded_file = csv_file.read().decode('utf-8')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            items = []
            for row in reader:
                # Clean empty values
                clean_row = {k: v for k, v in row.items() if v.strip()}
                if clean_row:  # Only add non-empty rows
                    items.append(clean_row)

            # Process the CSV data using the same logic as bulk_update
            created_items = []
            updated_items = []
            errors = []

            with transaction.atomic():
                for i, item_data in enumerate(items):
                    try:
                        # Check if this is an update (has ID) or create (no ID)
                        item_id = item_data.get('id')

                        if item_id:
                            # Update existing item
                            try:
                                instance = self.get_queryset().get(id=item_id)
                                serializer = self.get_serializer(instance, data=item_data, partial=True)
                            except self.get_model().DoesNotExist:
                                # ID provided but item doesn't exist, create new
                                item_data.pop('id', None)  # Remove invalid ID
                                serializer = self.get_serializer(data=item_data)
                        else:
                            # Create new item
                            serializer = self.get_serializer(data=item_data)

                        if serializer.is_valid():
                            instance = serializer.save(owner=request.user)
                            if item_id:
                                updated_items.append(instance.id)
                            else:
                                created_items.append(instance.id)
                        else:
                            errors.append({
                                'row': i + 1,
                                'errors': serializer.errors
                            })

                    except Exception as e:
                        errors.append({
                            'row': i + 1,
                            'error': str(e)
                        })

            return Response({
                'created': len(created_items),
                'updated': len(updated_items),
                'errors': errors,
                'created_ids': created_items,
                'updated_ids': updated_items
            })

        except Exception as e:
            return Response(
                {'error': f'Failed to process CSV: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def export_excel(self, request):
        """
        Export data as Excel file
        """
        queryset = self.get_queryset()

        # Create workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = self.get_model()._meta.verbose_name_plural

        # Get field names from serializer
        serializer = self.get_serializer()
        fields = list(serializer.fields.keys())

        # Write header
        ws.append([field.replace('_', ' ').title() for field in fields])

        # Write data
        for item in queryset:
            row = []
            for field in fields:
                value = getattr(item, field, '')
                if value is None:
                    value = ''
                row.append(str(value))
            ws.append(row)

        # Create response
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{self.get_model()._meta.verbose_name_plural.lower()}_export.xlsx"'

        wb.save(response)
        return response

    @action(detail=False, methods=['delete'])
    def delete_all(self, request):
        """
        Delete all items for the current user
        """
        queryset = self.get_queryset()
        count = queryset.count()
        queryset.delete()

        return Response({
            'message': f'Successfully deleted {count} items',
            'deleted_count': count
        })


class TeachingViewSet(BaseBulkViewSet):
    """ViewSet for managing teaching activities"""
    serializer_class = TeachingSerializer

    def get_model(self):
        return Teaching

    @action(detail=False, methods=['post'])
    def import_csv(self, request):
        """
        Import teaching data from CSV file with custom field mapping
        Expected CSV format: level,name (where level is Undergraduate/Graduate)
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        csv_file = request.FILES['file']

        if not csv_file.name.endswith('.csv'):
            return Response(
                {'error': 'File must be a CSV'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            decoded_file = csv_file.read().decode('utf-8-sig')  # Handle BOM
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)

            created_items = []
            updated_items = []
            errors = []

            with transaction.atomic():
                for i, row in enumerate(reader):
                    try:
                        # Debug: log the row data
                        print(f"Debug - Row {i+1}: {dict(row)}")

                        # Map CSV fields to Teaching model fields
                        teaching_data = self._map_csv_row_to_teaching(row)
                        print(f"Debug - Mapped data: {teaching_data}")

                        # Skip empty rows
                        if not teaching_data.get('name'):
                            continue

                        # Create new teaching record
                        serializer = self.get_serializer(data=teaching_data)
                        if serializer.is_valid():
                            instance = serializer.save(owner=request.user)
                            created_items.append(instance.id)
                        else:
                            errors.append({
                                'row': i + 2,  # +2 because of header and 0-indexing
                                'errors': serializer.errors
                            })

                    except Exception as e:
                        errors.append({
                            'row': i + 2,
                            'error': str(e)
                        })

            return Response({
                'created': len(created_items),
                'updated': len(updated_items),
                'errors': errors,
                'created_ids': created_items,
                'updated_ids': updated_items
            })

        except Exception as e:
            return Response(
                {'error': f'Failed to process CSV: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _map_csv_row_to_teaching(self, row):
        """
        Map CSV row to Teaching model fields
        CSV format: level,name
        """
        # Debug: print available keys and values
        print(f"Debug - Available CSV columns: {list(row.keys())}")
        print(f"Debug - Raw level value: '{row.get('level', 'NOT_FOUND')}'")

        # Get level directly from CSV and normalize case
        course_level = row.get('level', '').strip()
        level = course_level.lower() if course_level else 'other'

        print(f"Debug - Processed level: '{level}'")

        # Validate against allowed values
        allowed_levels = ['undergraduate', 'graduate', 'postdoc', 'professional', 'other']
        if level not in allowed_levels:
            print(f"Debug - Level '{level}' not in allowed values, defaulting to 'other'")
            level = 'other'

        return {
            'name': row.get('name', '').strip(),
            'level': level,
        }


class TalkViewSet(BaseBulkViewSet):
    """ViewSet for managing talks"""
    serializer_class = TalkSerializer

    def get_model(self):
        return Talk


class ConferenceViewSet(BaseBulkViewSet):
    """ViewSet for managing conference presentations"""
    serializer_class = ConferenceSerializer

    def get_model(self):
        return Conference