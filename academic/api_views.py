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
from .models import Publication, Teaching, Talk, Conference, Editorial
from .serializers import PublicationSerializer, TeachingSerializer, TalkSerializer, ConferenceSerializer, EditorialSerializer
from .csv_importers import (
    PublicationCSVImporter,
    TeachingCSVImporter,
    TalkCSVImporter,
    ConferenceCSVImporter,
    EditorialCSVImporter
)

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
        Import publications from CSV file using unified CSV importer
        Expected CSV format: type,year,authors,title,journal,volume,page,DOI,publisher,ISBN,editors
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        csv_file = request.FILES['file']
        importer = PublicationCSVImporter()
        result = importer.import_csv(request.user, csv_file)

        if 'error' in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)


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

    def get_csv_importer(self):
        """Override in subclasses to return appropriate CSV importer"""
        from .csv_importers import get_csv_importer
        model_name = self.get_model()._meta.model_name
        return get_csv_importer(model_name)

    @action(detail=False, methods=['post'])
    def import_csv(self, request):
        """
        Import data from CSV file using unified CSV importer
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        csv_file = request.FILES['file']
        importer = self.get_csv_importer()
        result = importer.import_csv(request.user, csv_file)

        if 'error' in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)

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


class EditorialViewSet(BaseBulkViewSet):
    """ViewSet for managing editorial activities"""
    serializer_class = EditorialSerializer

    def get_model(self):
        return Editorial

