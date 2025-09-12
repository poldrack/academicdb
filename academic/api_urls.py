"""
API URL configuration for academic app
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import PublicationViewSet

router = DefaultRouter()
router.register(r'publications', PublicationViewSet, basename='publication')

app_name = 'api'
urlpatterns = [
    path('v1/', include(router.urls)),
]