from django.urls import path
from . import views

app_name = 'academic'

urlpatterns = [
    # Web interface URLs
    path('', views.HomeView.as_view(), name='home'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    
    # Publication URLs
    path('publications/', views.PublicationListView.as_view(), name='publication_list'),
    path('publications/new/', views.PublicationCreateView.as_view(), name='publication_create'),
    path('publications/<int:pk>/', views.PublicationDetailView.as_view(), name='publication_detail'),
    path('publications/<int:pk>/edit/', views.PublicationUpdateView.as_view(), name='publication_update'),
    
    # Authentication URLs (handled by allauth, but we can add custom logic)
    path('auth/orcid/connected/', views.OrcidConnectedView.as_view(), name='orcid_connected'),
    
    # Sync endpoints
    path('sync/orcid/', views.OrcidSyncView.as_view(), name='orcid_sync'),
    path('sync/scopus/', views.ScopusSyncView.as_view(), name='scopus_sync'),
    path('sync/pubmed/', views.PubMedSyncView.as_view(), name='pubmed_sync'),
    path('sync/comprehensive/', views.ComprehensiveSyncView.as_view(), name='comprehensive_sync'),
    path('sync/status/', views.SyncStatusView.as_view(), name='sync_status'),
    path('sync/progress/', views.SyncProgressStreamView.as_view(), name='sync_progress'),
    path('publications/clear/', views.ClearPublicationsView.as_view(), name='clear_publications'),
]