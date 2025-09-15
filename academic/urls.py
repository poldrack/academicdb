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
    path('publications/<int:pk>/delete/', views.PublicationDeleteView.as_view(), name='publication_delete'),
    
    # Funding URLs
    path('funding/', views.FundingListView.as_view(), name='funding_list'),
    path('funding/new/', views.FundingCreateView.as_view(), name='funding_create'),
    path('funding/<int:pk>/', views.FundingDetailView.as_view(), name='funding_detail'),
    path('funding/<int:pk>/edit/', views.FundingUpdateView.as_view(), name='funding_update'),
    path('funding/clear/', views.ClearFundingView.as_view(), name='clear_funding'),
    
    # Teaching URLs
    path('teaching/', views.TeachingSpreadsheetView.as_view(), name='teaching_spreadsheet'),
    path('teaching/list/', views.TeachingSpreadsheetView.as_view(), name='teaching_list'),  # Redirect to spreadsheet view
    path('teaching/new/', views.TeachingCreateView.as_view(), name='teaching_create'),
    path('teaching/<int:pk>/', views.TeachingDetailView.as_view(), name='teaching_detail'),
    path('teaching/<int:pk>/edit/', views.TeachingUpdateView.as_view(), name='teaching_update'),
    path('teaching/spreadsheet/iframe/', views.TeachingSpreadsheetIframeView.as_view(), name='teaching_spreadsheet_iframe'),
    
    # Talk URLs
    path('talks/', views.TalksSpreadsheetView.as_view(), name='talks_spreadsheet'),
    path('talks/list/', views.TalksSpreadsheetView.as_view(), name='talk_list'),  # Redirect to spreadsheet view
    path('talks/new/', views.TalkCreateView.as_view(), name='talk_create'),
    path('talks/<int:pk>/', views.TalkDetailView.as_view(), name='talk_detail'),
    path('talks/<int:pk>/edit/', views.TalkUpdateView.as_view(), name='talk_update'),
    path('talks/spreadsheet/iframe/', views.TalksSpreadsheetIframeView.as_view(), name='talks_spreadsheet_iframe'),

    # Conference URLs
    path('conferences/', views.ConferencesSpreadsheetView.as_view(), name='conferences_spreadsheet'),
    path('conferences/list/', views.ConferencesSpreadsheetView.as_view(), name='conference_list'),  # Redirect to spreadsheet view
    path('conferences/new/', views.ConferenceCreateView.as_view(), name='conference_create'),
    path('conferences/<int:pk>/', views.ConferenceDetailView.as_view(), name='conference_detail'),
    path('conferences/<int:pk>/edit/', views.ConferenceUpdateView.as_view(), name='conference_update'),
    path('conferences/spreadsheet/iframe/', views.ConferencesSpreadsheetIframeView.as_view(), name='conferences_spreadsheet_iframe'),

    # Professional Activities URLs
    path('professional-activities/', views.ProfessionalActivityListView.as_view(), name='professional_activities'),
    
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

    # Tools & Administration URLs
    path('tools/', views.AdminPanelView.as_view(), name='admin_panel'),
    path('tools/backup/', views.AdminBackupView.as_view(), name='admin_backup'),
    path('tools/backup/create/', views.AdminBackupCreateView.as_view(), name='admin_backup_create'),
    path('tools/backup/restore/', views.AdminBackupRestoreView.as_view(), name='admin_backup_restore'),
    path('tools/backup/download/<str:backup_name>/', views.AdminBackupDownloadView.as_view(), name='admin_backup_download'),
    path('tools/backup/delete/<str:backup_name>/', views.AdminBackupDeleteView.as_view(), name='admin_backup_delete'),

    # CV Generation URLs
    path('cv/', views.CVPreviewView.as_view(), name='cv_preview'),
    path('cv/download/<str:format_type>/', views.CVView.as_view(), name='cv_download'),
]