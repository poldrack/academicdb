from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
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
    
    # Scopus Integration
    scopus_id = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Scopus Author ID"
    )
    
    # PubMed Integration
    pubmed_query = models.TextField(
        null=True,
        blank=True,
        help_text="PubMed search query to find your publications (e.g., 'Smith J[Author] AND Stanford[Affiliation]')"
    )
    
    # Academic Profile
    institution = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    research_areas = models.JSONField(
        default=list,
        blank=True,
        help_text="List of research areas/keywords"
    )

    # Personal Information for CV Header
    middle_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Middle name or initial for CV formatting"
    )

    # Address Information
    address1 = models.CharField(
        max_length=200,
        blank=True,
        help_text="Street address line 1"
    )
    address2 = models.CharField(
        max_length=200,
        blank=True,
        help_text="Street address line 2 (apartment, suite, etc.)"
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        help_text="City"
    )
    state = models.CharField(
        max_length=100,
        blank=True,
        help_text="State or province"
    )
    zip_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="ZIP or postal code"
    )
    country = models.CharField(
        max_length=100,
        blank=True,
        help_text="Country"
    )

    # Contact Information
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Phone number"
    )

    # Web Presence (JSONField for multiple URLs)
    websites = models.JSONField(
        default=list,
        blank=True,
        help_text="List of websites/URLs with labels (e.g., [{'label': 'Personal Website', 'url': 'https://...'}])"
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

    # DOI Skip List
    skip_dois = models.TextField(
        blank=True,
        null=True,
        help_text="List of DOIs to skip during publication ingestion (one per line)"
    )
    
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
    
    @property
    def has_scopus_id(self):
        """Check if user has Scopus ID"""
        return bool(self.scopus_id)

    @property
    def has_pubmed_query(self):
        """Check if user has PubMed query"""
        return bool(self.pubmed_query and self.pubmed_query.strip())

    def get_skip_dois_list(self):
        """Get normalized list of DOIs to skip during ingestion"""
        if not self.skip_dois:
            return []

        # Split by lines and normalize DOIs
        dois = []
        for line in self.skip_dois.strip().split('\n'):
            doi = line.strip().lower()
            if doi:
                # Remove any URL prefix if present
                if doi.startswith('https://doi.org/'):
                    doi = doi.replace('https://doi.org/', '')
                elif doi.startswith('http://doi.org/'):
                    doi = doi.replace('http://doi.org/', '')
                elif doi.startswith('doi:'):
                    doi = doi.replace('doi:', '')

                # Replace repeated slashes with single slash
                doi = re.sub(r'/+', '/', doi)

                if doi:
                    dois.append(doi)

        return dois


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
    is_preprint = models.BooleanField(
        default=False,
        help_text="True if this publication is a preprint (detected from DOI or manually set)"
    )
    is_ignored = models.BooleanField(
        default=False,
        help_text="True if this publication should be ignored (e.g., corrigendum, misattributed)"
    )
    ignore_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text="Reason for ignoring this publication (optional)"
    )

    # Publication Details (extracted from metadata for easy access)
    volume = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Journal volume number"
    )
    page_range = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Page range (e.g., '123-135', '1-15', 'e12345')"
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
                    # Special handling for volume and page_range: don't overwrite
                    # existing non-null values with null/empty values
                    if field in ['volume', 'page_range']:
                        current_value = getattr(self, field, None)
                        if current_value and not value:
                            # Skip updating if current value exists and new value is null/empty
                            continue
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
    def scopus_author_count(self):
        """Get the number of authors with Scopus IDs"""
        if not self.authors:
            return 0
        return sum(1 for author in self.authors 
                  if isinstance(author, dict) and author.get('scopus_id'))
    
    @property
    def has_scopus_authors(self):
        """Check if publication has any authors with Scopus IDs"""
        return self.scopus_author_count > 0
    
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

    @staticmethod
    def is_preprint_doi(doi):
        """
        Detect if a DOI belongs to a preprint server

        Args:
            doi (str): DOI to check

        Returns:
            bool: True if DOI is from a known preprint server
        """
        if not doi:
            return False

        # Convert to lowercase for consistent matching
        doi_lower = doi.lower()

        # Known preprint DOI prefixes
        preprint_prefixes = [
            '10.1101',    # bioRxiv
            '10.48550',   # arXiv (new format)
            '10.31234',   # PsyArXiv
            '10.21203',   # Research Square preprints
        ]

        # Check standard preprint prefixes
        if any(doi_lower.startswith(prefix) for prefix in preprint_prefixes):
            return True

        # Check for arXiv patterns (both old and new formats)
        # Old arXiv format: bare IDs like "2306.12345" or with arXiv: prefix
        # New arXiv format: 10.48550/arXiv.2306.12345
        import re

        # Pattern for arXiv IDs: YYMM.NNNNN format (optionally with arXiv: prefix)
        arxiv_patterns = [
            r'^arxiv:', # arXiv: prefix
            r'^\d{4}\.\d{4,5}',  # Bare arXiv ID format like 2306.12345
            r'10\.48550/arxiv\.',  # New DOI format
        ]

        for pattern in arxiv_patterns:
            if re.match(pattern, doi_lower):
                return True

        return False

    @staticmethod
    def normalize_doi_for_deduplication(doi):
        """
        Normalize DOI for deduplication by removing version suffixes

        Examples:
        - 10.21203/rs.3.rs-264855/v2 -> 10.21203/rs.3.rs-264855
        - 10.21203/rs.3.rs-264855/v3 -> 10.21203/rs.3.rs-264855
        - 10.1101/2021.11.26.470115 -> 10.1101/2021.11.26.470115 (unchanged)

        Args:
            doi (str): DOI to normalize

        Returns:
            tuple: (base_doi, version_number) or (doi, None) if no version
        """
        if not doi:
            return None, None

        import re

        # Convert to lowercase for consistent matching
        doi_lower = doi.lower().strip()

        # Pattern to match version suffixes like /v1, /v2, etc.
        version_pattern = r'^(.*)/v(\d+)$'
        match = re.match(version_pattern, doi_lower)

        if match:
            base_doi = match.group(1)
            version_number = int(match.group(2))
            return base_doi, version_number

        return doi_lower, None

    @classmethod
    def find_potential_duplicates_by_doi(cls, doi, user):
        """
        Find potential duplicate publications by DOI, including versioned variants

        Args:
            doi (str): DOI to search for
            user: User object to filter by

        Returns:
            QuerySet: Publications that might be duplicates
        """
        if not doi:
            return cls.objects.none()

        base_doi, version = cls.normalize_doi_for_deduplication(doi)
        if not base_doi:
            return cls.objects.none()

        # Search for exact DOI and any versioned variants
        import re

        # Use regex to find DOIs that match the base pattern with any version
        pattern = f"^{re.escape(base_doi)}(/v\\d+)?$"

        return cls.objects.filter(
            owner=user,
            doi__iregex=pattern
        ).order_by('doi')

    @classmethod
    def find_published_version_of_preprint(cls, preprint, user):
        """
        Find if a preprint has a corresponding published journal article

        Uses multiple strategies:
        1. Check for explicit relationship metadata
        2. Match by title similarity and author overlap

        Args:
            preprint: Publication object that is a preprint
            user: User object to filter by

        Returns:
            Publication object if published version found, None otherwise
        """
        if not preprint.is_preprint:
            return None

        # Strategy 1: Check for explicit relationships in metadata
        if preprint.metadata and isinstance(preprint.metadata, dict):
            relations = preprint.metadata.get('relation', {})
            if relations:
                for relation_type in ['is-preprint-of', 'has-version', 'is-version-of']:
                    if relation_type in relations:
                        relation_list = relations[relation_type]
                        if isinstance(relation_list, list):
                            for rel in relation_list:
                                if isinstance(rel, dict) and 'id' in rel:
                                    # Extract DOI from the relation
                                    published_doi = rel['id']
                                    # Clean the DOI
                                    if published_doi.startswith('https://doi.org/'):
                                        published_doi = published_doi.replace('https://doi.org/', '')
                                    elif published_doi.startswith('http://doi.org/'):
                                        published_doi = published_doi.replace('http://doi.org/', '')

                                    # Find this publication
                                    published_pub = cls.objects.filter(
                                        owner=user,
                                        doi=published_doi,
                                        is_preprint=False
                                    ).first()
                                    if published_pub:
                                        return published_pub

        # Strategy 2: Look for published articles with matching title and similar authors
        # Get all non-preprint publications by the same user
        published_pubs = cls.objects.filter(
            owner=user,
            is_preprint=False,
            is_ignored=False
        ).exclude(id=preprint.id)

        for pub in published_pubs:
            if cls._is_likely_published_version(preprint, pub):
                return pub

        return None

    @classmethod
    def _is_likely_published_version(cls, preprint, published_pub):
        """
        Determine if a published publication is likely the published version of a preprint

        Uses title similarity and author matching
        """
        # Check title similarity - use more relaxed threshold
        title_similarity = cls._calculate_title_similarity(preprint.title, published_pub.title)
        if title_similarity < 0.6:  # Lowered from 0.8 to 0.6 for more flexibility
            return False

        # Check author overlap - use more relaxed threshold
        author_overlap = cls._calculate_author_overlap(preprint.authors, published_pub.authors)
        if author_overlap < 0.3:  # Lowered from 0.5 to 0.3 for more flexibility
            return False

        # Check if published version came after preprint (allow same year)
        if published_pub.year < preprint.year:
            return False

        # Additional check: if we have very high title similarity (>= 0.9),
        # we can be more lenient with author overlap
        if title_similarity >= 0.9 and author_overlap >= 0.2:
            return True

        # For moderate title similarity, require higher author overlap
        if title_similarity >= 0.7 and author_overlap >= 0.4:
            return True

        # For lower title similarity, require high author overlap
        if title_similarity >= 0.6 and author_overlap >= 0.6:
            return True

        return False

    @classmethod
    def _calculate_title_similarity(cls, title1, title2):
        """Calculate title similarity using simple word overlap"""
        if not title1 or not title2:
            return 0.0

        import re

        # Normalize titles: lowercase, remove punctuation, split into words
        def normalize_title(title):
            words = re.findall(r'\b\w+\b', title.lower())
            # Remove common stop words
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'shall'}
            return [word for word in words if word not in stop_words and len(word) > 2]

        words1 = set(normalize_title(title1))
        words2 = set(normalize_title(title2))

        if not words1 or not words2:
            return 0.0

        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        return intersection / union if union > 0 else 0.0

    @classmethod
    def _calculate_author_overlap(cls, authors1, authors2):
        """Calculate author overlap between two publications"""
        if not authors1 or not authors2:
            return 0.0

        # Extract author names
        names1 = set()
        names2 = set()

        for author in authors1:
            if isinstance(author, dict):
                name = author.get('name', '')
            else:
                name = str(author)
            if name:
                names1.add(cls._normalize_author_name(name))

        for author in authors2:
            if isinstance(author, dict):
                name = author.get('name', '')
            else:
                name = str(author)
            if name:
                names2.add(cls._normalize_author_name(name))

        if not names1 or not names2:
            return 0.0

        # Calculate Jaccard similarity
        intersection = len(names1.intersection(names2))
        union = len(names1.union(names2))

        return intersection / union if union > 0 else 0.0

    @classmethod
    def _normalize_author_name(cls, name):
        """Normalize author name for comparison"""
        if not name:
            return ""

        import re

        # Convert to lowercase
        name = name.lower().strip()

        # Remove common suffixes and prefixes
        name = re.sub(r'\b(jr|sr|ph\.?d|m\.?d|dr)\b\.?', '', name)

        # Remove punctuation
        name = re.sub(r'[.,\-_\'\"()]', ' ', name)

        # Normalize whitespace
        name = re.sub(r'\s+', ' ', name).strip()

        # For comparison, use last name + first initial
        words = name.split()
        if len(words) >= 2:
            last_name = words[-1]
            first_initial = words[0][0] if words[0] else ''
            return f"{last_name} {first_initial}"
        elif len(words) == 1:
            return words[0]

        return name

    def detect_preprint_status(self):
        """
        Detect and update preprint status based on DOI

        Returns:
            bool: True if preprint status was updated
        """
        old_status = self.is_preprint
        old_type = self.publication_type

        # Detect if this is a preprint
        is_preprint = self.is_preprint_doi(self.doi)

        # Update preprint status and type
        self.is_preprint = is_preprint
        if is_preprint:
            self.publication_type = 'preprint'
        elif old_type == 'preprint' and not is_preprint:
            # If it was a preprint but no longer is (DOI changed), revert to journal-article
            self.publication_type = 'journal-article'

        return old_status != self.is_preprint or old_type != self.publication_type

    @property
    def preprint_server(self):
        """
        Get the preprint server name based on DOI

        Returns:
            str: Name of preprint server or None
        """
        if not self.is_preprint or not self.doi:
            return None

        if self.doi.startswith('10.1101'):
            return 'bioRxiv'
        elif self.doi.startswith('10.48550'):
            return 'arXiv'
        elif self.doi.startswith('10.31234'):
            return 'PsyArXiv'

        return 'Unknown Preprint Server'

    @classmethod
    def search(cls, query, user=None):
        """
        Full-text search across publications

        Args:
            query: Search query string
            user: AcademicUser instance to filter by (optional)

        Returns:
            QuerySet of Publication objects ranked by relevance
        """
        search_query = SearchQuery(query, config='english')

        # Start with base queryset
        qs = cls.objects.all()

        # Filter by user if provided
        if user:
            qs = qs.filter(owner=user)

        # Use raw SQL for search vector that was created in migration
        qs = qs.extra(
            select={'rank': "ts_rank(search_vector, plainto_tsquery('english', %s))"},
            select_params=(query,),
            where=["search_vector @@ plainto_tsquery('english', %s)"],
            params=(query,),
            order_by=('-rank',)
        )

        return qs

    def save(self, *args, **kwargs):
        """Override save to auto-detect preprint status and normalize DOI"""
        # Normalize DOI to lowercase and replace repeated slashes
        if self.doi:
            import re
            self.doi = self.doi.lower().strip()
            # Replace repeated slashes with single slash
            self.doi = re.sub(r'/+', '/', self.doi)

        # Auto-detect preprint status before saving
        self.detect_preprint_status()
        super().save(*args, **kwargs)


class AuthorCache(models.Model):
    """
    Cache for author lookups to avoid repeated API calls
    Stores mappings between names and external IDs (Scopus, ORCID, etc.)
    """
    # Normalized name for matching (lowercase, no punctuation)
    normalized_name = models.CharField(
        max_length=500,
        db_index=True,
        help_text="Normalized author name for matching"
    )
    
    # Original name variations seen
    name_variations = models.JSONField(
        default=list,
        help_text="List of name variations encountered"
    )
    
    # External identifiers
    scopus_id = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        db_index=True,
        help_text="Scopus Author ID"
    )
    orcid_id = models.CharField(
        max_length=19,
        null=True,
        blank=True,
        db_index=True,
        help_text="ORCID ID"
    )
    
    # Additional author details
    given_name = models.CharField(max_length=200, blank=True)
    surname = models.CharField(max_length=200, blank=True)
    affiliations = models.JSONField(
        default=list,
        blank=True,
        help_text="Known institutional affiliations"
    )
    
    # Metadata
    source = models.CharField(
        max_length=50,
        choices=[
            ('scopus', 'Scopus'),
            ('orcid', 'ORCID'),
            ('manual', 'Manual'),
            ('crossref', 'CrossRef'),
        ],
        help_text="Source of the ID information"
    )
    confidence_score = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Confidence in the mapping (0.0-1.0)"
    )
    
    # Quality tracking
    lookup_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of times this mapping has been used"
    )
    last_verified = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this mapping was verified"
    )
    verification_method = models.CharField(
        max_length=100,
        blank=True,
        help_text="Method used for last verification"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['normalized_name']),
            models.Index(fields=['scopus_id']),
            models.Index(fields=['orcid_id']),
            models.Index(fields=['source', 'confidence_score']),
        ]
        unique_together = ['normalized_name', 'scopus_id', 'orcid_id']
        ordering = ['-confidence_score', '-lookup_count', '-updated_at']
        verbose_name = 'Author Cache Entry'
        verbose_name_plural = 'Author Cache Entries'
    
    def __str__(self):
        ids = []
        if self.scopus_id:
            ids.append(f"Scopus:{self.scopus_id}")
        if self.orcid_id:
            ids.append(f"ORCID:{self.orcid_id}")
        
        id_str = " | ".join(ids) if ids else "No IDs"
        return f"{self.normalized_name} ({id_str})"
    
    @classmethod
    def normalize_name(cls, name):
        """Normalize author name for consistent matching"""
        if not name:
            return ""
        
        # Convert to lowercase and clean
        name = name.lower().strip()
        
        # Remove punctuation and standardize spaces
        import re
        name = re.sub(r'[.,\-_\'\"()]', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Handle common suffixes
        name = re.sub(r'\bjr\.?\b', '', name)  # Remove "Jr"
        name = re.sub(r'\bsr\.?\b', '', name)  # Remove "Sr"
        
        return name.strip()
    
    @classmethod
    def extract_name_components(cls, name):
        """Extract surname, given names, and initials from a name"""
        if not name:
            return {"surname": "", "given_names": [], "initials": [], "variants": []}
        
        import re
        
        # Normalize basic punctuation
        clean_name = name.lower().strip()
        clean_name = re.sub(r'[.,\-_\'\"()]', ' ', clean_name)
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        
        # Remove suffixes
        clean_name = re.sub(r'\bjr\.?\b', '', clean_name)
        clean_name = re.sub(r'\bsr\.?\b', '', clean_name)
        
        words = clean_name.split()
        if not words:
            return {"surname": "", "given_names": [], "initials": [], "variants": []}
        
        # Detect if this looks like "Last, First" format
        if ',' in name:
            parts = [p.strip() for p in name.split(',')]
            if len(parts) >= 2:
                surname = parts[0].lower().strip()
                given_part = ' '.join(parts[1:]).lower().strip()
                given_words = given_part.split()
            else:
                surname = words[-1]
                given_words = words[:-1]
        else:
            # Assume "First Last" format
            surname = words[-1]
            given_words = words[:-1]
        
        # Extract initials and full given names
        given_names = []
        initials = []
        
        for word in given_words:
            if len(word) == 1 or (len(word) == 2 and word.endswith('.')):
                # This is an initial
                initial = word.replace('.', '')
                initials.append(initial)
            elif len(word) > 1:
                # This is a full name
                given_names.append(word)
                initials.append(word[0])  # Add first letter as initial
        
        # Generate variants for matching
        variants = [surname]  # Surname only
        
        if initials:
            # Add initials variants
            initials_str = ' '.join(initials)
            variants.extend([
                f"{initials_str} {surname}",
                f"{surname} {initials_str}",
                ''.join(initials) + ' ' + surname,
                surname + ' ' + ''.join(initials)
            ])
        
        if given_names:
            # Add full name variants
            given_str = ' '.join(given_names)
            variants.extend([
                f"{given_str} {surname}",
                f"{surname} {given_str}"
            ])
            
            # Mixed variants (first name + other initials)
            if len(given_names) > 0 and len(initials) > 1:
                first_name = given_names[0]
                other_initials = ''.join(initials[1:])
                if other_initials:
                    variants.extend([
                        f"{first_name} {other_initials} {surname}",
                        f"{surname} {first_name} {other_initials}"
                    ])
        
        # Remove duplicates and empty variants
        variants = list(set(v.strip() for v in variants if v.strip()))
        
        return {
            "surname": surname,
            "given_names": given_names,
            "initials": initials,
            "variants": variants
        }
    
    @classmethod
    def find_cached_author(cls, name, fuzzy=True):
        """Find cached author by name using multi-variant matching"""
        if not name:
            return None
        
        # Extract all possible name variants
        components = cls.extract_name_components(name)
        search_variants = components['variants']
        
        # Phase 1: Exact matches on all variants
        for variant in search_variants:
            exact_match = cls.objects.filter(normalized_name=variant).first()
            if exact_match:
                exact_match.lookup_count += 1
                exact_match.save(update_fields=['lookup_count'])
                return exact_match
        
        if not fuzzy or not components['surname']:
            return None
        
        # Phase 2: Surname-based fuzzy matching
        surname = components['surname']
        initials = components['initials']
        given_names = components['given_names']
        
        # Find candidates with same surname
        candidates = cls.objects.filter(
            normalized_name__icontains=surname
        ).order_by('-confidence_score', '-lookup_count')[:20]
        
        best_match = None
        best_score = 0
        
        for candidate in candidates:
            # Extract candidate components
            candidate_components = cls.extract_name_components(candidate.normalized_name)
            candidate_surname = candidate_components['surname']
            candidate_initials = candidate_components['initials'] 
            candidate_given_names = candidate_components['given_names']
            
            # Surname must match exactly
            if candidate_surname != surname:
                continue
            
            # Calculate match score based on initials and given names
            score = cls._calculate_name_similarity(
                initials, given_names, candidate_initials, candidate_given_names
            )
            
            if score > best_score and score >= 0.7:  # Minimum 70% similarity
                best_score = score
                best_match = candidate
        
        if best_match:
            best_match.lookup_count += 1
            best_match.save(update_fields=['lookup_count'])
            return best_match
        
        # Phase 3: Edit distance matching for very similar names
        if len(search_variants) > 0:
            primary_variant = search_variants[0]  # Use most complete variant
            if len(primary_variant) >= 5:  # Only for names with decent length
                candidates = cls.objects.filter(
                    normalized_name__icontains=surname
                ).order_by('-confidence_score', '-lookup_count')[:10]
                
                for candidate in candidates:
                    distance = cls._edit_distance(primary_variant, candidate.normalized_name)
                    if distance <= 2 and len(candidate.normalized_name) >= 5:  # Allow max 2 character difference
                        candidate.lookup_count += 1
                        candidate.save(update_fields=['lookup_count'])
                        return candidate
        
        return None
    
    @classmethod
    def _calculate_name_similarity(cls, initials1, given_names1, initials2, given_names2):
        """Calculate similarity score between two name representations"""
        score = 0
        total_weight = 0
        
        # Compare initials (high weight)
        if initials1 and initials2:
            weight = 0.6
            total_weight += weight
            
            # Check if initials match (any order)
            matching_initials = len(set(initials1) & set(initials2))
            total_initials = max(len(initials1), len(initials2))
            if total_initials > 0:
                score += weight * (matching_initials / total_initials)
        
        # Compare given names (medium weight)
        if given_names1 and given_names2:
            weight = 0.4
            total_weight += weight
            
            # Check for exact matches or substring matches
            matches = 0
            for name1 in given_names1:
                for name2 in given_names2:
                    if name1 == name2:
                        matches += 1
                        break
                    elif len(name1) > 2 and len(name2) > 2:
                        # Check if one is substring of other (for Russell vs Russ)
                        if name1.startswith(name2) or name2.startswith(name1):
                            matches += 0.8
                            break
            
            if len(given_names1) > 0:
                score += weight * (matches / len(given_names1))
        
        # Handle cases where one has initials and other has given names
        elif (initials1 and given_names2) or (given_names1 and initials2):
            weight = 0.5
            total_weight += weight
            
            # Check if initials match first letters of given names
            check_initials = initials1 if initials1 else [name[0] for name in given_names1]
            check_given = given_names2 if given_names2 else []
            
            if not check_given:
                check_given = []
                check_initials = initials2 if initials2 else [name[0] for name in given_names2]
                check_given = given_names1 if given_names1 else []
            
            matches = 0
            for i, initial in enumerate(check_initials):
                if i < len(check_given) and check_given[i].startswith(initial.lower()):
                    matches += 1
            
            if len(check_initials) > 0:
                score += weight * (matches / len(check_initials))
        
        # Normalize score by total weight
        return score / total_weight if total_weight > 0 else 0
    
    @classmethod 
    def _edit_distance(cls, s1, s2):
        """Calculate edit distance between two strings"""
        if len(s1) > len(s2):
            s1, s2 = s2, s1
        
        distances = range(len(s1) + 1)
        for i2, c2 in enumerate(s2):
            distances_ = [i2 + 1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_
        return distances[-1]
    
    @classmethod
    def cache_author(cls, name, scopus_id=None, orcid_id=None, 
                    given_name=None, surname=None, affiliations=None, 
                    source='scopus', confidence_score=1.0):
        """Cache an author lookup result with intelligent deduplication"""
        if not name and not scopus_id and not orcid_id:
            return None
        
        # Extract name components for better matching
        components = cls.extract_name_components(name) if name else {}
        
        # Use surname as primary key for deduplication
        canonical_surname = components.get('surname', '') or surname or ''
        if not canonical_surname and name:
            canonical_surname = cls.normalize_name(name).split()[-1] if cls.normalize_name(name) else ''
        
        # Look for existing entries with the same surname and IDs
        existing = None
        
        # First, try to find by exact IDs
        if scopus_id:
            existing = cls.objects.filter(scopus_id=scopus_id).first()
        elif orcid_id:
            existing = cls.objects.filter(orcid_id=orcid_id).first()
        
        # If not found by ID, try intelligent name matching
        if not existing and canonical_surname:
            # Use the improved find_cached_author method
            existing = cls.find_cached_author(name, fuzzy=True) if name else None
        
        if existing:
            # Update existing entry
            updated = False
            
            # Update IDs if missing
            if scopus_id and not existing.scopus_id:
                existing.scopus_id = scopus_id
                updated = True
            
            if orcid_id and not existing.orcid_id:
                existing.orcid_id = orcid_id
                updated = True
                
            # Update name components if missing or better
            if given_name and not existing.given_name:
                existing.given_name = given_name
                updated = True
                
            if surname and not existing.surname:
                existing.surname = surname
                updated = True
            
            # Always add name variation
            if name and name not in existing.name_variations:
                existing.name_variations.append(name)
                updated = True
            
            # Add affiliations
            if affiliations:
                for affiliation in affiliations:
                    if affiliation not in existing.affiliations:
                        existing.affiliations.append(affiliation)
                        updated = True
            
            # Update confidence if higher or if we now have an ID
            new_confidence = confidence_score
            if scopus_id or orcid_id:
                new_confidence = max(confidence_score, 0.9)  # IDs give high confidence
            
            if new_confidence > existing.confidence_score:
                existing.confidence_score = new_confidence
                updated = True
                
            if updated:
                existing.save()
            
            return existing
        else:
            # Create new cache entry using canonical normalized name
            # Use the most complete variant as normalized name
            if name:
                variants = components.get('variants', [])
                # Choose the variant with most information
                best_variant = name  # Default to original
                max_parts = len(name.split())
                for variant in variants:
                    parts = len(variant.split())
                    if parts > max_parts:
                        max_parts = parts
                        best_variant = variant
                canonical_name = cls.normalize_name(best_variant)
            else:
                canonical_name = canonical_surname
            
            return cls.objects.create(
                normalized_name=canonical_name,
                name_variations=[name] if name else [],
                scopus_id=scopus_id,
                orcid_id=orcid_id,
                given_name=given_name or components.get('given_names', [''])[0] if components.get('given_names') else '',
                surname=surname or canonical_surname,
                affiliations=affiliations or [],
                source=source,
                confidence_score=max(confidence_score, 0.9) if (scopus_id or orcid_id) else confidence_score,
            )
    
    def add_verification(self, method, verified_ids=None):
        """Add verification information"""
        self.last_verified = timezone.now()
        self.verification_method = method
        
        if verified_ids:
            updated = False
            if verified_ids.get('scopus_id') and verified_ids['scopus_id'] != self.scopus_id:
                self.scopus_id = verified_ids['scopus_id']
                updated = True
            if verified_ids.get('orcid_id') and verified_ids['orcid_id'] != self.orcid_id:
                self.orcid_id = verified_ids['orcid_id']
                updated = True
            
            if updated:
                self.confidence_score = min(1.0, self.confidence_score + 0.1)
        
        self.save()


class PMCCache(models.Model):
    """
    Cache for PMID to PMCID mappings to speed up rebuilding the database
    Stores mappings that survive deletion of the publication database
    """
    # Primary identifier
    pmid = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text="PubMed ID"
    )

    # Cached PMC ID
    pmcid = models.CharField(
        max_length=20,
        help_text="PubMed Central ID (with PMC prefix)"
    )

    # DOI (optional, for additional verification)
    doi = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="DOI associated with this publication"
    )

    # Metadata for cache management
    lookup_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of times this mapping has been used"
    )

    last_verified = models.DateTimeField(
        auto_now=True,
        help_text="Last time this mapping was verified/updated"
    )

    source = models.CharField(
        max_length=50,
        choices=[
            ('pubmed_api', 'PubMed API'),
            ('manual', 'Manual Entry'),
        ],
        default='pubmed_api',
        help_text="Source of the mapping"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['pmid']),
            models.Index(fields=['pmcid']),
            models.Index(fields=['doi']),
            models.Index(fields=['lookup_count', '-last_verified']),
        ]
        ordering = ['-lookup_count', '-last_verified']
        verbose_name = 'PMC Cache Entry'
        verbose_name_plural = 'PMC Cache Entries'

    def __str__(self):
        return f"PMID:{self.pmid} -> {self.pmcid}"

    @classmethod
    def get_cached_pmcid(cls, pmid, doi=None):
        """
        Retrieve cached PMCID for a given PMID
        Returns None if not found in cache
        """
        try:
            cache_entry = cls.objects.filter(pmid=str(pmid)).first()
            if cache_entry:
                # Update lookup count and last verified
                cache_entry.lookup_count += 1
                cache_entry.save(update_fields=['lookup_count', 'last_verified'])
                return cache_entry.pmcid
        except Exception:
            pass
        return None

    @classmethod
    def cache_pmcid_mapping(cls, pmid, pmcid, doi=None, source='pubmed_api'):
        """
        Cache a PMID to PMCID mapping
        Updates existing entry or creates new one
        """
        if not pmid or not pmcid:
            return None

        # Ensure PMCID has PMC prefix
        if not pmcid.startswith('PMC'):
            pmcid = 'PMC' + pmcid

        # Update or create cache entry
        cache_entry, created = cls.objects.get_or_create(
            pmid=str(pmid),
            defaults={
                'pmcid': pmcid,
                'doi': doi,
                'source': source,
                'lookup_count': 1,
            }
        )

        if not created:
            # Update existing entry
            cache_entry.pmcid = pmcid
            if doi:
                cache_entry.doi = doi
            cache_entry.lookup_count += 1
            cache_entry.save()

        return cache_entry

    @classmethod
    def bulk_cache_mappings(cls, mappings):
        """
        Efficiently cache multiple PMID->PMCID mappings
        mappings: list of dicts with 'pmid', 'pmcid', and optionally 'doi'
        """
        cache_entries = []
        for mapping in mappings:
            pmid = mapping.get('pmid')
            pmcid = mapping.get('pmcid')
            doi = mapping.get('doi')

            if pmid and pmcid:
                # Ensure PMCID has PMC prefix
                if not pmcid.startswith('PMC'):
                    pmcid = 'PMC' + pmcid

                cache_entries.append(cls(
                    pmid=str(pmid),
                    pmcid=pmcid,
                    doi=doi,
                    source='pubmed_api',
                    lookup_count=1,
                ))

        if cache_entries:
            cls.objects.bulk_create(
                cache_entries,
                ignore_conflicts=True,
                batch_size=100
            )

        return len(cache_entries)


class Funding(models.Model):
    """
    Represents grants, awards, and funding history for academic researchers
    """
    # Status choices
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('declined', 'Declined'),
    ]
    
    # Role choices
    ROLE_CHOICES = [
        ('pi', 'Principal Investigator'),
        ('pi_subcontract', 'PI (Subcontract)'),
        ('co_pi', 'Co-Principal Investigator'),
        ('co_i', 'Co-Investigator'),
        ('consultant', 'Consultant'),
        ('other', 'Other'),
    ]
    
    # Ownership
    owner = models.ForeignKey(
        AcademicUser, 
        on_delete=models.CASCADE,
        related_name='funding'
    )
    
    # Grant Details
    title = models.CharField(max_length=500)
    agency = models.CharField(max_length=200)
    grant_number = models.CharField(max_length=100, blank=True)
    
    # Financial Information
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Funding amount in the specified currency"
    )
    currency = models.CharField(max_length=3, default='USD')
    
    # Timeline
    start_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Project start date"
    )
    end_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Project end date"
    )
    
    # Role & Collaboration
    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES,
        default='pi',
        help_text="Your role in this funding"
    )
    
    # Flexible Details
    additional_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata (ORCID-specific fields, etc.)"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        help_text="Current status of the funding"
    )
    
    # Source Tracking
    source = models.CharField(
        max_length=50,
        choices=[
            ('orcid', 'ORCID'),
            ('manual', 'Manual Entry'),
            ('institutional', 'Institutional System'),
        ],
        default='manual',
        help_text="Original data source"
    )
    
    # Edit Tracking (consistent with Publication model)
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
        indexes = [
            models.Index(fields=['owner', 'start_date']),
            models.Index(fields=['agency', 'status']),
            models.Index(fields=['source', 'updated_at']),
        ]
        ordering = ['-start_date', '-created_at']
        verbose_name = 'Funding'
        verbose_name_plural = 'Funding'
    
    def __str__(self):
        return f"{self.title} ({self.agency})"
    
    def clean(self):
        """Validate funding data"""
        super().clean()
        
        # Validate date range
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError({
                    'end_date': 'End date must be after start date'
                })
    
    def save_with_edit_protection(self, api_data=None, user_edit=False, edited_fields=None):
        """
        Save funding with protection for manually edited fields
        Similar pattern to Publication model
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
    def duration_years(self):
        """Calculate project duration in years"""
        if self.start_date and self.end_date:
            delta = self.end_date - self.start_date
            return round(delta.days / 365.25, 1)
        return None
    
    @property
    def is_active(self):
        """Check if funding is currently active"""
        return self.status == 'active'
    
    @property
    def formatted_amount(self):
        """Return formatted amount with currency"""
        if self.amount:
            return f"{self.currency} {self.amount:,.2f}"
        return None


class Teaching(models.Model):
    """
    Represents teaching activities including courses taught
    """
    # Course level choices
    LEVEL_CHOICES = [
        ('undergraduate', 'Undergraduate'),
        ('graduate', 'Graduate'),
        ('postdoc', 'Postdoctoral'),
        ('professional', 'Professional Development'),
        ('other', 'Other'),
    ]
    
    # Ownership
    owner = models.ForeignKey(
        AcademicUser, 
        on_delete=models.CASCADE,
        related_name='teaching'
    )
    
    # Course Details
    name = models.CharField(
        max_length=300,
        help_text="Course name or title"
    )
    level = models.CharField(
        max_length=50,
        choices=LEVEL_CHOICES,
        default='undergraduate',
        help_text="Academic level of the course"
    )
    
    # Optional Details
    course_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="Course number/code (e.g., PSYC 101)"
    )
    semester = models.CharField(
        max_length=50,
        blank=True,
        help_text="Semester taught (e.g., Fall 2023)"
    )
    year = models.IntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(1950),
            MaxValueValidator(datetime.now().year + 10)
        ],
        help_text="Year taught"
    )
    institution = models.CharField(
        max_length=200,
        blank=True,
        help_text="Institution where course was taught"
    )
    enrollment = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of students enrolled"
    )
    
    # Additional metadata
    additional_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional course details"
    )
    
    # Source tracking
    source = models.CharField(
        max_length=50,
        choices=[
            ('manual', 'Manual Entry'),
            ('import', 'File Import'),
            ('institutional', 'Institutional System'),
        ],
        default='manual',
        help_text="Original data source"
    )
    
    # Edit tracking
    manual_edits = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tracks which fields have been manually edited"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['owner', 'year']),
            models.Index(fields=['level', 'year']),
        ]
        ordering = ['-year', 'level', 'name']
        verbose_name = 'Teaching Activity'
        verbose_name_plural = 'Teaching Activities'
    
    def __str__(self):
        if self.year:
            return f"{self.name} ({self.get_level_display()}, {self.year})"
        return f"{self.name} ({self.get_level_display()})"


class Talk(models.Model):
    """
    Represents invited talks, seminars, and speaking engagements
    """
    # Ownership
    owner = models.ForeignKey(
        AcademicUser, 
        on_delete=models.CASCADE,
        related_name='talks'
    )
    
    # Talk Details
    year = models.IntegerField(
        validators=[
            MinValueValidator(1950),
            MaxValueValidator(datetime.now().year + 10)
        ],
        help_text="Year of the talk"
    )
    place = models.CharField(
        max_length=500,
        help_text="Institution, university, or venue where talk was given"
    )
    
    # Optional Details
    title = models.CharField(
        max_length=500,
        blank=True,
        help_text="Title of the talk"
    )
    date = models.DateField(
        null=True,
        blank=True,
        help_text="Specific date of the talk"
    )
    invited = models.BooleanField(
        default=True,
        help_text="Was this an invited talk?"
    )
    virtual = models.BooleanField(
        default=False,
        help_text="Was this talk given virtually?"
    )
    
    # Additional metadata
    additional_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional talk details (audience size, event name, etc.)"
    )
    
    # Source tracking
    source = models.CharField(
        max_length=50,
        choices=[
            ('manual', 'Manual Entry'),
            ('import', 'File Import'),
        ],
        default='manual',
        help_text="Original data source"
    )
    
    # Edit tracking
    manual_edits = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tracks which fields have been manually edited"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['owner', 'year']),
            models.Index(fields=['year', 'invited']),
        ]
        ordering = ['-year', '-date', 'place']
        verbose_name = 'Talk'
        verbose_name_plural = 'Talks'
    
    def __str__(self):
        if self.title:
            return f"{self.title} - {self.place} ({self.year})"
        return f"{self.place} ({self.year})"


class Conference(models.Model):
    """
    Represents conference presentations, posters, and proceedings
    """
    # Presentation type choices
    TYPE_CHOICES = [
        ('talk', 'Talk/Presentation'),
        ('poster', 'Poster'),
        ('keynote', 'Keynote'),
        ('workshop', 'Workshop'),
        ('panel', 'Panel Discussion'),
        ('other', 'Other'),
    ]
    
    # Ownership
    owner = models.ForeignKey(
        AcademicUser, 
        on_delete=models.CASCADE,
        related_name='conferences'
    )
    
    # Conference Details
    title = models.CharField(
        max_length=500,
        help_text="Title of the presentation/poster"
    )
    authors = models.TextField(
        help_text="Authors of the presentation (as they appear in program)"
    )
    year = models.IntegerField(
        validators=[
            MinValueValidator(1950),
            MaxValueValidator(datetime.now().year + 10)
        ],
        help_text="Year of the conference"
    )
    location = models.CharField(
        max_length=500,
        help_text="Conference location (city, venue, or 'virtual')"
    )
    
    # Optional Details
    month = models.CharField(
        max_length=20,
        blank=True,
        help_text="Month of the conference"
    )
    conference_name = models.CharField(
        max_length=300,
        blank=True,
        help_text="Name of the conference or meeting"
    )
    presentation_type = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        default='talk',
        help_text="Type of presentation"
    )
    link = models.URLField(
        blank=True,
        help_text="Link to presentation, abstract, or conference page"
    )
    abstract = models.TextField(
        blank=True,
        help_text="Abstract of the presentation"
    )
    
    # Parsed author information (JSON field for structured data)
    parsed_authors = models.JSONField(
        default=list,
        blank=True,
        help_text="Structured author information"
    )
    
    # Additional metadata
    additional_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional conference details"
    )
    
    # Source tracking
    source = models.CharField(
        max_length=50,
        choices=[
            ('manual', 'Manual Entry'),
            ('import', 'File Import'),
        ],
        default='manual',
        help_text="Original data source"
    )
    
    # Edit tracking
    manual_edits = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tracks which fields have been manually edited"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['owner', 'year']),
            models.Index(fields=['year', 'presentation_type']),
        ]
        ordering = ['-year', 'month', 'title']
        verbose_name = 'Conference Presentation'
        verbose_name_plural = 'Conference Presentations'


class APIRecordCache(models.Model):
    """
    Cache for full records from external APIs (Scopus, PubMed, CrossRef)
    These records are preserved even when publications are deleted to speed up re-syncing
    """
    # API source choices
    API_SOURCES = [
        ('scopus', 'Scopus'),
        ('pubmed', 'PubMed'),
        ('crossref', 'CrossRef'),
    ]

    # Primary identifiers
    api_source = models.CharField(
        max_length=20,
        choices=API_SOURCES,
        db_index=True,
        help_text="Source API for this record"
    )

    # API-specific identifier
    api_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="API-specific identifier (DOI, PMID, Scopus ID, etc.)"
    )

    # Secondary identifiers for cross-referencing
    doi = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="DOI if available"
    )

    pmid = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        db_index=True,
        help_text="PubMed ID if available"
    )

    scopus_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        db_index=True,
        help_text="Scopus ID if available"
    )

    # Full API response
    raw_data = models.JSONField(
        help_text="Complete API response data"
    )

    # Processed metadata for quick access
    title = models.TextField(
        blank=True,
        help_text="Publication title extracted from API data"
    )

    year = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Publication year extracted from API data"
    )

    authors = models.JSONField(
        default=list,
        blank=True,
        help_text="Author list extracted from API data"
    )

    # Cache management
    lookup_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of times this record has been accessed"
    )

    last_accessed = models.DateTimeField(
        auto_now=True,
        help_text="Last time this record was accessed"
    )

    # Quality and reliability tracking
    is_complete = models.BooleanField(
        default=True,
        help_text="Whether this record contains complete data"
    )

    api_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="API version when record was fetched"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['api_source', 'api_id']),
            models.Index(fields=['doi']),
            models.Index(fields=['pmid']),
            models.Index(fields=['scopus_id']),
            models.Index(fields=['api_source', 'year']),
            models.Index(fields=['lookup_count', '-last_accessed']),
        ]
        unique_together = ['api_source', 'api_id']
        ordering = ['-last_accessed', '-lookup_count']
        verbose_name = 'API Record Cache'
        verbose_name_plural = 'API Record Cache'

    def __str__(self):
        title_preview = self.title[:50] + "..." if len(self.title) > 50 else self.title
        return f"{self.api_source.upper()}: {title_preview} ({self.year or 'No year'})"

    @classmethod
    def get_cached_record(cls, api_source, api_id=None, doi=None, pmid=None, scopus_id=None):
        """
        Retrieve cached record by various identifiers

        Args:
            api_source: 'scopus', 'pubmed', or 'crossref'
            api_id: Primary API identifier
            doi: DOI for cross-API lookup
            pmid: PubMed ID for cross-API lookup
            scopus_id: Scopus ID for cross-API lookup

        Returns:
            APIRecordCache instance or None
        """
        # Try primary identifier first
        if api_id:
            record = cls.objects.filter(api_source=api_source, api_id=api_id).first()
            if record:
                record.lookup_count += 1
                record.save(update_fields=['lookup_count', 'last_accessed'])
                return record

        # Try secondary identifiers
        filters = {}
        if doi:
            filters['doi'] = doi.lower()
        if pmid:
            filters['pmid'] = str(pmid)
        if scopus_id:
            filters['scopus_id'] = str(scopus_id)

        if filters:
            # Look for any matching record from the same API source first
            record = cls.objects.filter(api_source=api_source, **filters).first()
            if record:
                record.lookup_count += 1
                record.save(update_fields=['lookup_count', 'last_accessed'])
                return record

            # Look for records from other APIs if needed for cross-referencing
            record = cls.objects.filter(**filters).first()
            if record:
                record.lookup_count += 1
                record.save(update_fields=['lookup_count', 'last_accessed'])
                return record

        return None

    @classmethod
    def cache_record(cls, api_source, api_id, raw_data, doi=None, pmid=None, scopus_id=None,
                     title=None, year=None, authors=None, api_version=None, is_complete=True):
        """
        Cache an API record with automatic metadata extraction

        Args:
            api_source: 'scopus', 'pubmed', or 'crossref'
            api_id: Primary API identifier
            raw_data: Complete API response
            doi, pmid, scopus_id: Cross-reference identifiers
            title, year, authors: Extracted metadata (will be auto-extracted if not provided)
            api_version: API version string
            is_complete: Whether record is complete

        Returns:
            APIRecordCache instance
        """
        # Normalize identifiers
        if doi:
            doi = doi.lower().strip()
        if pmid:
            pmid = str(pmid).strip()
        if scopus_id:
            scopus_id = str(scopus_id).strip()

        # Extract metadata if not provided
        if not title or not year or not authors:
            extracted = cls._extract_metadata(api_source, raw_data)
            title = title or extracted.get('title', '')
            year = year or extracted.get('year')
            authors = authors or extracted.get('authors', [])

        # Update or create cache entry
        record, created = cls.objects.update_or_create(
            api_source=api_source,
            api_id=api_id,
            defaults={
                'raw_data': raw_data,
                'doi': doi,
                'pmid': pmid,
                'scopus_id': scopus_id,
                'title': title or '',
                'year': year,
                'authors': authors or [],
                'is_complete': is_complete,
                'api_version': api_version or '',
            }
        )

        # Update lookup count separately for existing records
        if not created:
            record.lookup_count += 1
            record.save(update_fields=['lookup_count', 'last_accessed'])

        return record

    @classmethod
    def _extract_metadata(cls, api_source, raw_data):
        """
        Extract title, year, and authors from raw API data

        Args:
            api_source: 'scopus', 'pubmed', or 'crossref'
            raw_data: Raw API response data

        Returns:
            dict with 'title', 'year', 'authors' keys
        """
        metadata = {'title': '', 'year': None, 'authors': []}

        if not raw_data:
            return metadata

        try:
            if api_source == 'scopus':
                # Scopus API structure
                if 'dc:title' in raw_data:
                    metadata['title'] = raw_data['dc:title']
                elif 'title' in raw_data:
                    metadata['title'] = raw_data['title']

                if 'prism:coverDate' in raw_data:
                    date_str = raw_data['prism:coverDate']
                    if date_str:
                        try:
                            metadata['year'] = int(date_str.split('-')[0])
                        except (ValueError, IndexError):
                            pass

                # Extract authors from Scopus format
                if 'author' in raw_data:
                    authors = raw_data['author']
                    if isinstance(authors, list):
                        for author in authors:
                            if isinstance(author, dict):
                                name = author.get('authname', '')
                                if name:
                                    metadata['authors'].append({'name': name})

            elif api_source == 'pubmed':
                # PubMed API structure
                if 'title' in raw_data:
                    metadata['title'] = raw_data['title']
                elif 'ArticleTitle' in raw_data:
                    metadata['title'] = raw_data['ArticleTitle']

                if 'pubdate' in raw_data:
                    date_str = raw_data['pubdate']
                    if date_str:
                        try:
                            metadata['year'] = int(date_str.split()[0])
                        except (ValueError, IndexError):
                            pass

                # Extract authors from PubMed format
                if 'authors' in raw_data:
                    authors = raw_data['authors']
                    if isinstance(authors, list):
                        for author in authors:
                            if isinstance(author, dict):
                                name = author.get('name', '')
                                if name:
                                    metadata['authors'].append({'name': name})

            elif api_source == 'crossref':
                # CrossRef API structure
                if 'title' in raw_data and raw_data['title']:
                    metadata['title'] = raw_data['title'][0] if isinstance(raw_data['title'], list) else raw_data['title']

                if 'published-print' in raw_data:
                    date_parts = raw_data['published-print'].get('date-parts', [])
                    if date_parts and date_parts[0]:
                        metadata['year'] = date_parts[0][0]
                elif 'published-online' in raw_data:
                    date_parts = raw_data['published-online'].get('date-parts', [])
                    if date_parts and date_parts[0]:
                        metadata['year'] = date_parts[0][0]

                # Extract authors from CrossRef format
                if 'author' in raw_data:
                    authors = raw_data['author']
                    if isinstance(authors, list):
                        for author in authors:
                            if isinstance(author, dict):
                                given = author.get('given', '')
                                family = author.get('family', '')
                                name = f"{given} {family}".strip()
                                if name:
                                    metadata['authors'].append({'name': name})

        except Exception:
            # If extraction fails, return empty metadata
            pass

        return metadata

    @classmethod
    def bulk_cache_records(cls, records):
        """
        Efficiently cache multiple API records

        Args:
            records: List of dicts with cache_record parameters

        Returns:
            Number of records cached
        """
        cached_count = 0

        for record_data in records:
            try:
                cls.cache_record(**record_data)
                cached_count += 1
            except Exception:
                # Skip problematic records
                continue

        return cached_count

    @classmethod
    def cleanup_old_records(cls, days_old=365, min_lookup_count=1):
        """
        Clean up old, rarely used cache records

        Args:
            days_old: Remove records older than this many days
            min_lookup_count: Only remove records with lookup_count <= this value

        Returns:
            Number of records deleted
        """
        from django.utils import timezone
        from datetime import timedelta

        cutoff_date = timezone.now() - timedelta(days=days_old)

        old_records = cls.objects.filter(
            last_accessed__lt=cutoff_date,
            lookup_count__lte=min_lookup_count
        )

        count = old_records.count()
        old_records.delete()

        return count


class ProfessionalActivity(models.Model):
    """
    Represents professional activities from ORCID including:
    - Employments
    - Education and qualifications
    - Invited positions and distinctions
    - Memberships and service
    """
    # Owner
    owner = models.ForeignKey(
        AcademicUser,
        on_delete=models.CASCADE,
        related_name='professional_activities'
    )

    # Activity Type
    ACTIVITY_TYPES = [
        ('employment', 'Employment'),
        ('education', 'Education'),
        ('qualification', 'Qualification'),
        ('invited_position', 'Invited Position'),
        ('distinction', 'Distinction'),
        ('membership', 'Membership'),
        ('service', 'Service'),
    ]

    activity_type = models.CharField(
        max_length=50,
        choices=ACTIVITY_TYPES,
        help_text="Type of professional activity"
    )

    # Core Fields
    title = models.CharField(
        max_length=500,
        help_text="Position title or activity name"
    )

    organization = models.CharField(
        max_length=500,
        help_text="Organization or institution name"
    )

    department = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Department within organization"
    )

    role = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Role or position type"
    )

    # Date Fields
    start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Start date of activity"
    )

    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="End date of activity (null for current positions)"
    )

    is_current = models.BooleanField(
        default=False,
        help_text="Is this a current/ongoing activity?"
    )

    # Location
    city = models.CharField(max_length=200, blank=True, null=True)
    region = models.CharField(max_length=200, blank=True, null=True)
    country = models.CharField(max_length=200, blank=True, null=True)

    # Additional Details
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Description of the activity or role"
    )

    url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL for more information"
    )

    # ORCID Metadata
    orcid_put_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        help_text="ORCID put-code for this activity"
    )

    orcid_path = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="ORCID API path for this activity"
    )

    orcid_visibility = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="ORCID visibility setting"
    )

    # Raw ORCID data
    orcid_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw data from ORCID API"
    )

    # Source tracking
    source = models.CharField(
        max_length=50,
        choices=[
            ('orcid', 'ORCID'),
            ('manual', 'Manual Entry'),
        ],
        default='orcid',
        help_text="Original data source"
    )

    # Edit tracking
    manual_edits = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tracks which fields have been manually edited"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time synced from ORCID"
    )

    class Meta:
        indexes = [
            models.Index(fields=['owner', 'activity_type']),
            models.Index(fields=['owner', 'is_current']),
            models.Index(fields=['activity_type', 'start_date']),
            models.Index(fields=['orcid_put_code']),
        ]
        ordering = ['-is_current', '-start_date', 'title']
        verbose_name = 'Professional Activity'
        verbose_name_plural = 'Professional Activities'
        unique_together = [['owner', 'orcid_put_code']]

    def __str__(self):
        date_str = f"{self.start_date.year if self.start_date else 'Unknown'}"
        if self.is_current:
            date_str += "-Present"
        elif self.end_date:
            date_str += f"-{self.end_date.year}"
        return f"{self.title} at {self.organization} ({date_str})"

    def save(self, *args, **kwargs):
        # Auto-detect if current based on end_date
        if not self.end_date:
            self.is_current = True
        else:
            self.is_current = False
        super().save(*args, **kwargs)
    
    @property
    def first_author(self):
        """Extract first author from authors string"""
        if self.authors:
            # Handle both comma-separated and formatted author strings
            authors_clean = self.authors.strip()
            if ',' in authors_clean:
                return authors_clean.split(',')[0].strip()
            else:
                # Assume space-separated format
                words = authors_clean.split()
                if words:
                    # Look for pattern "LastName FirstInitial"
                    return f"{words[0]} {words[1] if len(words) > 1 else ''}"
        return "Unknown"
    
    @property
    def author_count(self):
        """Estimate number of authors"""
        if not self.authors:
            return 0
        # Simple heuristic: count commas + 1, or count "and" occurrences
        comma_count = self.authors.count(',')
        if comma_count > 0:
            return comma_count + 1
        
        and_count = self.authors.lower().count(' and ')
        if and_count > 0:
            return and_count + 1
        
        # Fallback: assume single author if no clear separators
        return 1 if self.authors.strip() else 0
