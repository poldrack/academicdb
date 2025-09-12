from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator, MinLengthValidator
from django.core.exceptions import ValidationError
import re
from datetime import datetime


class AcademicUser(AbstractUser):
    """
    Custom user model for academic researchers with ORCID integration
    """
    # ORCID Integration
    orcid_id = models.CharField(
        max_length=19, 
        unique=True, 
        null=True, 
        blank=True,
        help_text="ORCID ID format: 0000-0000-0000-000X"
    )
    orcid_token = models.TextField(
        null=True, 
        blank=True,
        help_text="OAuth token for ORCID API access"
    )
    
    # Academic Profile
    institution = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    research_areas = models.JSONField(
        default=list, 
        blank=True,
        help_text="List of research areas/keywords"
    )
    
    # System Settings
    preferred_citation_style = models.CharField(
        max_length=50, 
        default='apa',
        choices=[
            ('apa', 'APA'),
            ('mla', 'MLA'),
            ('chicago', 'Chicago'),
            ('ieee', 'IEEE'),
        ]
    )
    email_notifications = models.BooleanField(default=True)
    
    # Timestamps
    last_orcid_sync = models.DateTimeField(null=True, blank=True)
    profile_updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        if self.orcid_id:
            return f"{self.get_full_name()} ({self.orcid_id})"
        return self.get_full_name() or self.username
    
    @property
    def display_name(self):
        """Return the best available display name"""
        return self.get_full_name() or self.username
    
    @property
    def is_orcid_connected(self):
        """Check if user has valid ORCID connection"""
        return bool(self.orcid_id and self.orcid_token)


class Publication(models.Model):
    """
    Represents academic publications with flexible metadata and edit tracking
    """
    # Publication source choices
    SOURCE_CHOICES = [
        ('scopus', 'Scopus'),
        ('pubmed', 'PubMed'),
        ('crossref', 'CrossRef'),
        ('orcid', 'ORCID'),
        ('manual', 'Manual Entry'),
    ]
    
    # Publication type choices
    TYPE_CHOICES = [
        ('journal-article', 'Journal Article'),
        ('conference-paper', 'Conference Paper'),
        ('book', 'Book'),
        ('book-chapter', 'Book Chapter'),
        ('preprint', 'Preprint'),
        ('thesis', 'Thesis/Dissertation'),
        ('patent', 'Patent'),
        ('report', 'Report'),
        ('dataset', 'Dataset'),
        ('software', 'Software'),
        ('other', 'Other'),
    ]
    
    # Ownership & Identity
    owner = models.ForeignKey(
        AcademicUser, 
        on_delete=models.CASCADE,
        related_name='publications'
    )
    doi = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Digital Object Identifier (DOI)"
    )
    
    # Core Structured Fields
    title = models.TextField(
        validators=[MinLengthValidator(10)],
        help_text="Publication title (minimum 10 characters)"
    )
    year = models.IntegerField(
        db_index=True,
        validators=[
            MinValueValidator(1900),
            MaxValueValidator(datetime.now().year + 5)
        ],
        help_text="Publication year"
    )
    publication_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Specific publication date if known"
    )
    publication_name = models.CharField(
        max_length=500, 
        null=True, 
        blank=True,
        help_text="Journal, conference, or publisher name"
    )
    publication_type = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        default='journal-article',
        help_text="Type of publication"
    )
    
    # Flexible Metadata (JSON fields for SQLite, will be JSONB in PostgreSQL)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="API-specific metadata (Scopus, PubMed, etc.)"
    )
    authors = models.JSONField(
        default=list,
        help_text="List of authors with affiliations"
    )
    identifiers = models.JSONField(
        default=dict,
        blank=True,
        help_text="External identifiers (PMID, PMCID, Scopus ID, etc.)"
    )
    links = models.JSONField(
        default=dict,
        blank=True,
        help_text="URLs to PDF, dataset, code repository, etc."
    )
    
    # Source Tracking
    source = models.CharField(
        max_length=50,
        choices=SOURCE_CHOICES,
        default='manual',
        help_text="Original data source"
    )
    
    # Edit Tracking
    manual_edits = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tracks which fields have been manually edited"
    )
    edit_history = models.JSONField(
        default=list,
        blank=True,
        help_text="Audit trail of all edits"
    )
    manually_edited_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last manual edit timestamp"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_api_sync = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last synchronization with external API"
    )
    
    class Meta:
        # Note: GinIndex requires PostgreSQL, commented out for SQLite compatibility
        # When switching to PostgreSQL, uncomment these:
        # indexes = [
        #     models.Index(fields=['owner', 'year']),
        #     models.Index(fields=['doi']),
        #     models.Index(fields=['source', 'updated_at']),
        #     GinIndex(fields=['metadata']),
        #     GinIndex(fields=['authors']),
        #     GinIndex(fields=['identifiers']),
        # ]
        indexes = [
            models.Index(fields=['owner', 'year']),
            models.Index(fields=['doi']),
            models.Index(fields=['source', 'updated_at']),
        ]
        unique_together = ['owner', 'doi']
        ordering = ['-year', '-publication_date', 'title']
        verbose_name = 'Publication'
        verbose_name_plural = 'Publications'
    
    def __str__(self):
        return f"{self.title} ({self.year})"
    
    def clean(self):
        """Validate publication data"""
        super().clean()
        
        # Validate DOI format if provided
        if self.doi:
            doi_pattern = r'^10\.\d{4,}/[-._;()/:\w]+$'
            if not re.match(doi_pattern, self.doi):
                raise ValidationError({'doi': 'Invalid DOI format. Expected format: 10.XXXX/XXXX'})
        
        # Ensure at least one author
        if not self.authors or len(self.authors) == 0:
            raise ValidationError({'authors': 'At least one author is required'})
        
        # Validate year
        current_year = datetime.now().year
        if self.year < 1900 or self.year > current_year + 5:
            raise ValidationError({'year': f'Year must be between 1900 and {current_year + 5}'})
    
    def save_with_edit_protection(self, api_data=None, user_edit=False, edited_fields=None):
        """
        Save publication with protection for manually edited fields
        
        Args:
            api_data: Dictionary of data from external API
            user_edit: Boolean indicating if this is a manual user edit
            edited_fields: List of field names that were edited
        """
        if user_edit and edited_fields:
            # Mark fields as manually edited
            for field_name in edited_fields:
                self.manual_edits[field_name] = True
            
            # Add to edit history
            self.edit_history.append({
                'timestamp': timezone.now().isoformat(),
                'fields': edited_fields,
                'action': 'manual_edit',
            })
            self.manually_edited_at = timezone.now()
        
        if api_data:
            # Only update fields that haven't been manually edited
            for field, value in api_data.items():
                if not self.manual_edits.get(field, False):
                    setattr(self, field, value)
            self.last_api_sync = timezone.now()
        
        self.save()
    
    @property
    def first_author(self):
        """Get the first author's name"""
        if self.authors and len(self.authors) > 0:
            author = self.authors[0]
            if isinstance(author, dict):
                return author.get('name', 'Unknown')
            return str(author)
        return 'Unknown'
    
    @property
    def author_count(self):
        """Get the number of authors"""
        return len(self.authors) if self.authors else 0
    
    @property
    def has_manual_edits(self):
        """Check if publication has any manual edits"""
        return bool(self.manual_edits)
    
    def get_identifier(self, id_type):
        """Get a specific identifier (e.g., 'pmid', 'pmcid', 'scopus_id')"""
        return self.identifiers.get(id_type)
    
    def get_link(self, link_type):
        """Get a specific link (e.g., 'pdf', 'dataset', 'code')"""
        return self.links.get(link_type)
