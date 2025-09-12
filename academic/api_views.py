"""
API views for academic models
"""
from rest_framework import viewsets, permissions, authentication, status
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import exception_handler
from django.contrib.auth import get_user_model
from .models import Publication
from .serializers import PublicationSerializer

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
    max_page_size = 100


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