from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
import json
from .models import AcademicUser, Publication, AuthorCache, ProfessionalActivity


@admin.register(AcademicUser)
class AcademicUserAdmin(UserAdmin):
    """
    Admin interface for AcademicUser model
    """
    fieldsets = UserAdmin.fieldsets + (
        ('Academic Profile', {
            'fields': ('orcid_id', 'orcid_token', 'institution', 'department', 'research_areas')
        }),
        ('Personal Information', {
            'fields': ('middle_name',)
        }),
        ('Address', {
            'fields': ('address1', 'address2', 'city', 'state', 'zip_code', 'country')
        }),
        ('Contact Information', {
            'fields': ('phone', 'websites')
        }),
        ('Settings', {
            'fields': ('preferred_citation_style', 'email_notifications')
        }),
        ('Timestamps', {
            'fields': ('last_orcid_sync', 'profile_updated')
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Academic Profile', {
            'fields': ('orcid_id', 'institution', 'department')
        }),
        ('Personal Information', {
            'fields': ('middle_name',)
        }),
        ('Address', {
            'fields': ('address1', 'address2', 'city', 'state', 'zip_code', 'country')
        }),
        ('Contact Information', {
            'fields': ('phone', 'websites')
        }),
    )
    
    list_display = ['username', 'email', 'first_name', 'last_name', 'orcid_id', 'institution', 'is_active']
    list_filter = ['is_active', 'is_staff', 'institution', 'preferred_citation_style']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'orcid_id', 'institution']
    readonly_fields = ['profile_updated', 'last_orcid_sync']


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    """
    Admin interface for Publication model
    """
    list_display = [
        'title_truncated', 
        'year', 
        'first_author',
        'publication_type',
        'source',
        'has_doi',
        'has_manual_edits_display',
        'owner',
        'created_at'
    ]
    
    list_filter = [
        'year',
        'publication_type',
        'source',
        ('manually_edited_at', admin.EmptyFieldListFilter),
        'created_at',
        'updated_at'
    ]
    
    search_fields = [
        'title',
        'doi',
        'publication_name',
        'authors',
        'owner__username',
        'owner__email'
    ]
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'last_api_sync',
        'manually_edited_at',
        'formatted_authors',
        'formatted_identifiers',
        'formatted_links',
        'formatted_manual_edits',
        'formatted_edit_history'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'title', 'year', 'publication_date', 'publication_type')
        }),
        ('Publication Details', {
            'fields': ('publication_name', 'doi', 'source')
        }),
        ('Authors & Metadata', {
            'fields': ('formatted_authors', 'metadata'),
            'classes': ('collapse',)
        }),
        ('Identifiers & Links', {
            'fields': ('formatted_identifiers', 'formatted_links'),
            'classes': ('collapse',)
        }),
        ('Edit Tracking', {
            'fields': (
                'formatted_manual_edits',
                'formatted_edit_history',
                'manually_edited_at'
            ),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at', 'last_api_sync'),
            'classes': ('collapse',)
        })
    )
    
    def title_truncated(self, obj):
        """Display truncated title"""
        return obj.title[:75] + '...' if len(obj.title) > 75 else obj.title
    title_truncated.short_description = 'Title'
    
    def has_doi(self, obj):
        """Check if publication has DOI"""
        return bool(obj.doi)
    has_doi.boolean = True
    has_doi.short_description = 'DOI'
    
    def has_manual_edits_display(self, obj):
        """Display if publication has manual edits"""
        return obj.has_manual_edits
    has_manual_edits_display.boolean = True
    has_manual_edits_display.short_description = 'Edited'
    
    def formatted_authors(self, obj):
        """Display formatted authors list"""
        if not obj.authors:
            return "No authors"
        
        html = "<ol>"
        for author in obj.authors[:10]:  # Show first 10 authors
            if isinstance(author, dict):
                name = author.get('name', 'Unknown')
                affiliation = author.get('affiliation', '')
                if affiliation:
                    html += f"<li>{name} ({affiliation})</li>"
                else:
                    html += f"<li>{name}</li>"
            else:
                html += f"<li>{author}</li>"
        
        if len(obj.authors) > 10:
            html += f"<li><em>... and {len(obj.authors) - 10} more</em></li>"
        html += "</ol>"
        
        return mark_safe(html)
    formatted_authors.short_description = "Authors"
    
    def formatted_identifiers(self, obj):
        """Display formatted identifiers"""
        if not obj.identifiers:
            return "No identifiers"
        
        html = "<dl>"
        for key, value in obj.identifiers.items():
            html += f"<dt><strong>{key}:</strong></dt><dd>{value}</dd>"
        html += "</dl>"
        
        return mark_safe(html)
    formatted_identifiers.short_description = "External Identifiers"
    
    def formatted_links(self, obj):
        """Display formatted links"""
        if not obj.links:
            return "No links"
        
        html = "<ul>"
        for key, url in obj.links.items():
            html += f'<li><strong>{key}:</strong> <a href="{url}" target="_blank">{url}</a></li>'
        html += "</ul>"
        
        return mark_safe(html)
    formatted_links.short_description = "Links"
    
    def formatted_manual_edits(self, obj):
        """Display fields that have been manually edited"""
        if not obj.manual_edits:
            return "No manual edits"
        
        edited_fields = [field for field, is_edited in obj.manual_edits.items() if is_edited]
        if not edited_fields:
            return "No manual edits"
        
        return ", ".join(edited_fields)
    formatted_manual_edits.short_description = "Manually Edited Fields"
    
    def formatted_edit_history(self, obj):
        """Display edit history"""
        if not obj.edit_history:
            return "No edit history"
        
        html = "<ul>"
        for entry in obj.edit_history[-10:]:  # Show last 10 edits
            timestamp = entry.get('timestamp', 'Unknown time')
            action = entry.get('action', 'Unknown action')
            fields = entry.get('fields', [])
            
            html += f"<li><strong>{timestamp}</strong>: {action}"
            if fields:
                html += f" - Fields: {', '.join(fields)}"
            html += "</li>"
        
        if len(obj.edit_history) > 10:
            html += f"<li><em>... and {len(obj.edit_history) - 10} more edits</em></li>"
        html += "</ul>"
        
        return mark_safe(html)
    formatted_edit_history.short_description = "Edit History"
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('owner')
    
    def save_model(self, request, obj, form, change):
        """Track manual edits when saving through admin"""
        if change:  # If editing existing publication
            # Get changed fields
            changed_fields = []
            if form.changed_data:
                changed_fields = form.changed_data
                
            # Use the save_with_edit_protection method
            obj.save_with_edit_protection(
                user_edit=True,
                edited_fields=changed_fields
            )
        else:
            super().save_model(request, obj, form, change)


@admin.register(AuthorCache)
class AuthorCacheAdmin(admin.ModelAdmin):
    """
    Admin interface for AuthorCache model
    """
    list_display = [
        'normalized_name',
        'scopus_id',
        'orcid_id',
        'source',
        'confidence_score',
        'lookup_count',
        'last_verified',
        'created_at'
    ]
    
    list_filter = [
        'source',
        'confidence_score',
        ('scopus_id', admin.EmptyFieldListFilter),
        ('orcid_id', admin.EmptyFieldListFilter),
        'created_at',
        'last_verified'
    ]
    
    search_fields = [
        'normalized_name',
        'scopus_id',
        'orcid_id',
        'given_name',
        'surname',
        'name_variations'
    ]
    
    readonly_fields = [
        'lookup_count',
        'created_at',
        'updated_at'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('normalized_name', 'given_name', 'surname')
        }),
        ('External Identifiers', {
            'fields': ('scopus_id', 'orcid_id')
        }),
        ('Metadata', {
            'fields': ('source', 'confidence_score', 'verification_method')
        }),
        ('Name Variations & Affiliations', {
            'fields': ('name_variations', 'affiliations'),
            'classes': ('collapse',)
        }),
        ('Usage Statistics', {
            'fields': ('lookup_count', 'last_verified', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.order_by('-confidence_score', '-lookup_count', '-updated_at')
    
    actions = ['verify_authors', 'clear_verification']
    
    def verify_authors(self, request, queryset):
        """Mark selected authors as verified"""
        updated = queryset.update(
            last_verified=timezone.now(),
            verification_method='admin_verification'
        )
        self.message_user(request, f'{updated} authors marked as verified.')
    verify_authors.short_description = "Mark selected authors as verified"
    
    def clear_verification(self, request, queryset):
        """Clear verification status"""
        updated = queryset.update(
            last_verified=None,
            verification_method=''
        )
        self.message_user(request, f'{updated} authors verification status cleared.')
    clear_verification.short_description = "Clear verification status"


@admin.register(ProfessionalActivity)
class ProfessionalActivityAdmin(admin.ModelAdmin):
    """
    Admin interface for ProfessionalActivity model
    """
    list_display = [
        'title',
        'activity_type',
        'organization',
        'is_current',
        'start_date',
        'end_date',
        'owner',
        'source'
    ]

    list_filter = [
        'activity_type',
        'is_current',
        'source',
        'start_date',
        'created_at'
    ]

    search_fields = [
        'title',
        'organization',
        'department',
        'role',
        'city',
        'country',
        'owner__username',
        'owner__email'
    ]

    readonly_fields = [
        'orcid_put_code',
        'orcid_path',
        'orcid_visibility',
        'created_at',
        'updated_at',
        'last_synced'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'activity_type', 'title', 'organization', 'department', 'role')
        }),
        ('Dates', {
            'fields': ('start_date', 'end_date', 'is_current')
        }),
        ('Location', {
            'fields': ('city', 'region', 'country')
        }),
        ('Additional Information', {
            'fields': ('description', 'url'),
            'classes': ('collapse',)
        }),
        ('ORCID Metadata', {
            'fields': ('orcid_put_code', 'orcid_path', 'orcid_visibility', 'source'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at', 'last_synced'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('owner').order_by('-is_current', '-start_date')
