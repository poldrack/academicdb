# Data Model: Academic Database Web Interface

**Date**: 2025-09-12  
**Status**: Design Phase  
**Purpose**: Define Django models and database schema for academic data management

---

## Entity Relationship Overview

```
AcademicUser (1) ──── (*) Publication
                │
                ├──── (*) Coauthor  
                │
                ├──── (*) Funding
                │
                ├──── (*) Talk
                │
                ├──── (*) Education
                │
                ├──── (*) Employment
                │
                ├──── (*) Distinction
                │
                ├──── (*) Membership
                │
                ├──── (*) Service
                │
                └──── (1) ResearcherMetadata

Publication (*) ──── (*) Coauthor (through AuthorCollaboration)
```

---

## Core Entities

### 1. AcademicUser (Authentication & Authorization)

**Purpose**: Represents authenticated researchers with ORCID integration

```python
class AcademicUser(AbstractUser):
    # ORCID Integration
    orcid_id = models.CharField(max_length=19, unique=True, null=True, blank=True)
    orcid_token = models.TextField(null=True, blank=True)  # OAuth token
    
    # Academic Profile
    institution = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    research_areas = models.JSONField(default=list, blank=True)
    
    # System Settings
    preferred_citation_style = models.CharField(max_length=50, default='apa')
    email_notifications = models.BooleanField(default=True)
    
    # Timestamps
    last_orcid_sync = models.DateTimeField(null=True, blank=True)
    profile_updated = models.DateTimeField(auto_now=True)
```

**Validation Rules**:
- ORCID ID format: `0000-0000-0000-000X` (19 characters including hyphens)
- Email must be unique and valid
- Institution and department are optional but recommended

**State Transitions**:
- `inactive` → `active` (ORCID authentication)
- `active` → `syncing` (during ORCID data updates)
- `active` → `suspended` (admin action)

---

### 2. Publication (Core Academic Output)

**Purpose**: Represents academic publications with flexible metadata and edit tracking

```python
class Publication(models.Model):
    # Ownership & Identity
    owner = models.ForeignKey(AcademicUser, on_delete=models.CASCADE)
    doi = models.CharField(max_length=255, unique=True, db_index=True)
    
    # Core Structured Fields
    title = models.TextField()
    year = models.IntegerField(db_index=True)
    publication_date = models.DateField(null=True, blank=True)
    publication_name = models.CharField(max_length=500, null=True, blank=True)
    publication_type = models.CharField(max_length=50, default='journal-article')
    
    # Flexible Metadata (JSONB)
    metadata = models.JSONField(default=dict)  # API-specific data
    authors = models.JSONField(default=list)   # Author details with affiliations
    identifiers = models.JSONField(default=dict)  # PMID, PMCID, Scopus ID, etc.
    links = models.JSONField(default=dict)     # URLs to PDF, data, code
    
    # Source Tracking
    source = models.CharField(max_length=50, choices=[
        ('scopus', 'Scopus'),
        ('pubmed', 'PubMed'), 
        ('crossref', 'CrossRef'),
        ('orcid', 'ORCID'),
        ('manual', 'Manual Entry')
    ])
    
    # Edit Tracking
    manual_edits = models.JSONField(default=dict)  # {field_name: True/False}
    edit_history = models.JSONField(default=list)  # Audit trail
    manually_edited_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_api_sync = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['owner', 'year']),
            models.Index(fields=['doi']),
            models.Index(fields=['source', 'updated_at']),
            GinIndex(fields=['metadata']),
            GinIndex(fields=['authors']),
            GinIndex(fields=['identifiers']),
        ]
        unique_together = ['owner', 'doi']
```

**Validation Rules**:
- DOI format validation (10.XXXX/XXXX pattern)
- Year must be between 1900 and current year + 5
- Title minimum length: 10 characters
- At least one author required
- Publication type from controlled vocabulary

**JSONB Field Structures**:
```python
# metadata example
{
    "scopus_data": {
        "citedby_count": 45,
        "volume": "123",
        "pageRange": "45-67",
        "aggregationType": "Journal"
    },
    "pubmed_data": {
        "pmid": "12345678",
        "mesh_terms": ["Computer Science", "Artificial Intelligence"]
    }
}

# authors example  
[
    {
        "name": "Smith, John A.",
        "affiliation": "Stanford University",
        "scopus_id": "123456789",
        "order": 1
    },
    {
        "name": "Doe, Jane B.", 
        "affiliation": "Harvard University",
        "orcid": "0000-0000-0000-0000",
        "order": 2
    }
]
```

---

### 3. Coauthor (Collaboration Tracking)

**Purpose**: Tracks collaborators and their affiliations for NSF reporting

```python
class Coauthor(models.Model):
    # Ownership
    researcher = models.ForeignKey(AcademicUser, on_delete=models.CASCADE)
    
    # Identity
    scopus_id = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    orcid_id = models.CharField(max_length=19, null=True, blank=True)
    name = models.CharField(max_length=200)
    
    # Affiliation Details (JSONB for flexibility)
    affiliations = models.JSONField(default=list)  # Current and historical
    affiliation_ids = models.JSONField(default=list)  # Scopus affiliation IDs
    
    # Collaboration Statistics
    num_collaborations = models.IntegerField(default=0)
    first_collaboration = models.DateField(null=True, blank=True)
    last_collaboration = models.DateField(null=True, blank=True)
    
    # Contact Information
    email = models.EmailField(blank=True)
    institution_current = models.CharField(max_length=200, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['researcher', 'scopus_id']
        indexes = [
            models.Index(fields=['researcher', 'last_collaboration']),
            models.Index(fields=['scopus_id']),
            GinIndex(fields=['affiliations']),
        ]
```

**Validation Rules**:
- Name required, minimum 5 characters
- At least one identifier (scopus_id or orcid_id) required
- Email validation if provided
- Affiliation history maintained chronologically

---

### 4. Funding (Grant & Award Tracking)

**Purpose**: Tracks grants, awards, and funding history

```python
class Funding(models.Model):
    # Ownership
    researcher = models.ForeignKey(AcademicUser, on_delete=models.CASCADE)
    
    # Grant Details
    title = models.CharField(max_length=500)
    agency = models.CharField(max_length=200)
    grant_number = models.CharField(max_length=100, blank=True)
    
    # Financial Information
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    
    # Timeline
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    # Role & Collaboration
    role = models.CharField(max_length=50, choices=[
        ('pi', 'Principal Investigator'),
        ('co_pi', 'Co-Principal Investigator'),
        ('co_i', 'Co-Investigator'),
        ('consultant', 'Consultant'),
        ('other', 'Other')
    ])
    
    # Flexible Details
    additional_info = models.JSONField(default=dict)
    
    # Status
    status = models.CharField(max_length=20, choices=[
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('declined', 'Declined')
    ], default='active')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['researcher', 'start_date']),
            models.Index(fields=['agency', 'status']),
        ]
```

---

### 5. Talk (Presentation Tracking)

**Purpose**: Academic presentations, conferences, and invited talks

```python
class Talk(models.Model):
    # Ownership
    researcher = models.ForeignKey(AcademicUser, on_delete=models.CASCADE)
    
    # Talk Details
    title = models.CharField(max_length=500)
    venue = models.CharField(max_length=300)
    location = models.CharField(max_length=200, blank=True)
    
    # Date & Time
    date = models.DateField()
    
    # Talk Type
    talk_type = models.CharField(max_length=50, choices=[
        ('invited', 'Invited Talk'),
        ('conference', 'Conference Presentation'),
        ('poster', 'Poster Presentation'),
        ('keynote', 'Keynote'),
        ('workshop', 'Workshop'),
        ('webinar', 'Webinar'),
        ('other', 'Other')
    ])
    
    # Additional Information
    abstract = models.TextField(blank=True)
    slides_url = models.URLField(blank=True)
    recording_url = models.URLField(blank=True)
    additional_info = models.JSONField(default=dict)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['researcher', 'date']),
            models.Index(fields=['talk_type', 'date']),
        ]
        ordering = ['-date']
```

---

### 6. Education (Academic Background)

**Purpose**: Educational history and qualifications

```python
class Education(models.Model):
    # Ownership
    researcher = models.ForeignKey(AcademicUser, on_delete=models.CASCADE)
    
    # Institution
    institution = models.CharField(max_length=200)
    department = models.CharField(max_length=200, blank=True)
    
    # Degree Information
    degree_type = models.CharField(max_length=50, choices=[
        ('phd', 'Ph.D.'),
        ('masters', 'Master\'s'),
        ('bachelors', 'Bachelor\'s'),
        ('postdoc', 'Postdoctoral'),
        ('fellowship', 'Fellowship'),
        ('certificate', 'Certificate'),
        ('other', 'Other')
    ])
    degree_field = models.CharField(max_length=200)
    
    # Timeline
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    # Additional Details
    advisor = models.CharField(max_length=200, blank=True)
    thesis_title = models.CharField(max_length=500, blank=True)
    gpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    additional_info = models.JSONField(default=dict)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['researcher', 'end_date']),
            models.Index(fields=['degree_type', 'end_date']),
        ]
        ordering = ['-end_date']
```

---

### 7. Employment (Professional History)

**Purpose**: Career positions and professional experience

```python
class Employment(models.Model):
    # Ownership
    researcher = models.ForeignKey(AcademicUser, on_delete=models.CASCADE)
    
    # Position Details
    institution = models.CharField(max_length=200)
    department = models.CharField(max_length=200, blank=True)
    position_title = models.CharField(max_length=200)
    
    # Timeline
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Null for current position
    
    # Position Type
    position_type = models.CharField(max_length=50, choices=[
        ('faculty', 'Faculty'),
        ('postdoc', 'Postdoctoral Researcher'),
        ('staff', 'Staff'),
        ('visiting', 'Visiting Scholar'),
        ('consultant', 'Consultant'),
        ('industry', 'Industry Position'),
        ('other', 'Other')
    ])
    
    # Additional Information
    responsibilities = models.TextField(blank=True)
    is_current = models.BooleanField(default=False)
    additional_info = models.JSONField(default=dict)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['researcher', 'start_date']),
            models.Index(fields=['position_type', 'is_current']),
        ]
        ordering = ['-start_date']
```

---

### 8. Supporting Entities

**Distinction, Membership, Service** follow similar patterns with flexible JSONB fields for various award types, professional memberships, and service activities.

---

## Data Integrity & Constraints

### Foreign Key Relationships
- All entities cascade delete from `AcademicUser` (researcher data ownership)
- No orphaned records possible
- Publication-Coauthor relationships through explicit collaboration tracking

### Database Indexes
- **Performance**: GIN indexes on all JSONB fields for fast queries
- **Uniqueness**: Composite indexes on user+identifier fields
- **Temporal**: Indexes on date fields for chronological queries
- **Full-text**: PostgreSQL text search vectors on title/abstract fields

### Data Validation
- **Format validation**: DOI, ORCID ID, email formats
- **Business rules**: Date ranges, required fields per entity type
- **Referential integrity**: User ownership, collaboration consistency
- **JSON schema validation**: Structured validation for JSONB fields

---

## Migration Mapping

### MongoDB → PostgreSQL Translation
```python
# MongoDB collections mapping
COLLECTION_MAPPINGS = {
    'publications': 'Publication',
    'coauthors': 'Coauthor', 
    'funding': 'Funding',
    'talks': 'Talk',
    'education': 'Education',
    'employment': 'Employment',
    'distinctions': 'Distinction',
    'memberships': 'Membership',
    'service': 'Service',
    'metadata': 'ResearcherMetadata'
}

# Document → Model field mapping
FIELD_MAPPINGS = {
    'publications': {
        'DOI': 'doi',
        'title': 'title',
        'year': 'year',
        'authors': 'authors',  # JSON preserved
        'publicationName': 'publication_name',
        # All other fields → metadata JSONB
    }
}
```

---

## Query Optimization

### Common Query Patterns
```sql
-- Publication search by year and author
SELECT * FROM publications 
WHERE owner_id = %s 
  AND year BETWEEN %s AND %s
  AND authors @> '[{"name": "%smith%"}]';

-- Collaboration network analysis
SELECT DISTINCT c.name, c.institution_current
FROM coauthors c
JOIN publications p ON p.authors @> CONCAT('[{"scopus_id": "', c.scopus_id, '"}]')::jsonb
WHERE p.owner_id = %s AND c.last_collaboration >= %s;

-- Full-text search across publications
SELECT * FROM publications
WHERE to_tsvector('english', title || ' ' || coalesce(metadata->>'abstract', ''))
      @@ plainto_tsquery('english', %s);
```

### Performance Targets
- User dashboard load: <2 seconds
- Publication search: <500ms
- Bulk operations: 1000+ records/second
- Concurrent users: 50+ researchers

---

*Data model design complete - ready for API contract generation.*