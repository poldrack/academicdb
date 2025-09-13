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
    
    @property
    def has_scopus_id(self):
        """Check if user has Scopus ID"""
        return bool(self.scopus_id)
    
    @property
    def has_pubmed_query(self):
        """Check if user has PubMed query"""
        return bool(self.pubmed_query and self.pubmed_query.strip())


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
