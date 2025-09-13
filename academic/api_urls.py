"""
API URL configuration for academic app
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import PublicationViewSet, TeachingViewSet, TalkViewSet, ConferenceViewSet

router = DefaultRouter()
router.register(r'publications', PublicationViewSet, basename='publication')
router.register(r'teaching', TeachingViewSet, basename='teaching')
router.register(r'talks', TalkViewSet, basename='talk')
router.register(r'conferences', ConferenceViewSet, basename='conference')

app_name = 'api'
urlpatterns = [
    path('v1/', include(router.urls)),
]