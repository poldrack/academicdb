# Research Findings: Academic Database Web Interface & Modernization

**Date**: 2025-09-12  
**Status**: Complete  
**Purpose**: Resolve technical unknowns for Django migration with optimal database backend

---

## Database Backend Research

### Decision: PostgreSQL with Django ORM
**Rationale**: PostgreSQL with JSONB fields provides the optimal balance of structured data benefits and flexible document storage, far superior to MongoDB integration with Django.

**Alternatives Considered**:
1. **MongoDB with djongo** - Rejected due to poor Django integration, buggy ORM translation
2. **MongoDB with MongoEngine** - Rejected due to non-standard Django patterns, ecosystem gaps
3. **SQLite** - Considered for development/single-user only
4. **PostgreSQL hybrid** - Selected as optimal solution

**Key Benefits**:
- Native Django ORM support with migrations, admin interface, ecosystem compatibility  
- JSONB fields preserve flexible academic metadata while enabling structured queries
- Superior full-text search for publications (PostgreSQL vs MongoDB text search)
- ACID transactions critical for multi-source API data synchronization
- GIN indexes for high-performance JSONB queries
- Mature migration tooling and proven academic database implementations

**Implementation Approach**:
```python
class Publication(models.Model):
    # Structured core fields
    doi = models.CharField(max_length=255, unique=True, db_index=True)
    title = models.TextField()
    year = models.IntegerField(db_index=True)
    
    # Flexible metadata in JSONB
    metadata = models.JSONField(default=dict)  # Scopus, PubMed, CrossRef data
    authors = models.JSONField(default=list)   # Variable author formats
    identifiers = models.JSONField(default=dict)  # PMID, PMCID, etc.
    
    class Meta:
        indexes = [GinIndex(fields=['metadata', 'authors'])]
```

---

## Authentication Strategy Research

### Decision: Django-allauth with ORCID Provider
**Rationale**: Academic researchers already possess ORCID identifiers (required for modern publishing), providing optimal user experience and security.

**Alternatives Considered**:
1. **Django built-in auth** - Rejected as insufficient for academic identity integration
2. **Custom OAuth2** - Rejected due to high maintenance overhead
3. **Institutional SSO** - Considered as future enhancement
4. **django-allauth + ORCID** - Selected for optimal academic workflow

**Key Benefits**:
- Researchers use familiar ORCID credentials (e.g., 0000-0001-6755-0259 format)
- Battle-tested django-allauth package with native ORCID provider
- Long-lived tokens (20-year expiry) suitable for academic workflows
- Compliance with ORCID authentication guidelines
- Extensible to institutional SSO integration

**Implementation Approach**:
```python
# settings.py
SOCIALACCOUNT_PROVIDERS = {
    'orcid': {
        'SCOPE': ['openid'],
        'APPS': [{
            'client_id': 'your-orcid-client-id',
            'secret': 'your-orcid-secret',
            'settings': {'member': True}
        }]
    }
}

# Custom user model
class AcademicUser(AbstractUser):
    orcid_id = models.CharField(max_length=19, unique=True, null=True)
    institution = models.CharField(max_length=200, blank=True)
    research_areas = models.JSONField(default=list, blank=True)
```

**User Experience Flow**:
1. Researcher visits Django web interface
2. "Login with ORCID" button redirects to ORCID OAuth
3. ORCID authentication and consent
4. Return to Django app with user profile creation
5. Access to personal academic database collections

---

## Data Migration Strategy Research

### Decision: Phased Dual-Write Migration
**Rationale**: Zero-downtime migration preserving existing CLI tools while enabling comprehensive data validation.

**Migration Phases**:
1. **Initial Bulk Migration** - Offline PostgreSQL population with optimized bulk inserts
2. **Dual-Write Mode** - New data written to both MongoDB and PostgreSQL
3. **Validation Phase** - Comprehensive data consistency checking
4. **Dual-Read Validation** - Application reads from both databases for comparison
5. **PostgreSQL-Only** - Complete migration with MongoDB retirement

**Key Technical Decisions**:

**Schema Mapping**:
- MongoDB collections → Django models with JSONB fields
- Preserve flexible metadata in `metadata` JSONB column
- Extract frequently queried fields (DOI, year, title) to structured columns
- GIN indexes on JSONB fields for query performance

**Data Preservation**:
- Field-level edit tracking to preserve manual changes during API sync
- Audit trail for all manual modifications
- Conflict resolution favoring user edits over API updates

**Performance Optimization**:
- Bulk operations with 1000-record batches
- Temporary PostgreSQL optimization settings during migration
- GIN indexes for JSONB query performance
- Connection pooling for concurrent access

---

## Edit Tracking & Conflict Resolution Research

### Decision: Field-Level Edit Metadata with Preservation Logic
**Rationale**: Academic databases require preserving manual edits when synchronizing with external APIs (Scopus, PubMed, etc.).

**Implementation Strategy**:
```python
class Publication(models.Model):
    # Core data fields
    title = models.TextField()
    
    # Edit tracking
    manual_edits = models.JSONField(default=dict)  # {'title': True, 'authors': True}
    last_api_sync = models.DateTimeField(auto_now=True)
    edit_history = models.JSONField(default=list)  # Audit trail
    
    def save_with_edit_protection(self, api_data=None, user_edit=False):
        """Save with protection for manually edited fields"""
        if user_edit:
            # Mark field as manually edited
            self.manual_edits[field_name] = True
            self.edit_history.append({
                'timestamp': timezone.now().isoformat(),
                'field': field_name,
                'action': 'manual_edit',
                'user': request.user.username
            })
        
        if api_data:
            # Only update fields not manually edited
            for field, value in api_data.items():
                if not self.manual_edits.get(field, False):
                    setattr(self, field, value)
        
        super().save()
```

**Conflict Resolution Rules**:
1. User edits always take precedence over API updates
2. New fields from APIs are added unless conflicting with manual edits
3. Timestamp-based audit trail for all changes
4. Admin interface for resolving complex conflicts

---

## Performance & Scalability Research

### Decision: Multi-User Architecture with User-Scoped Data
**Rationale**: Academic departments need collaborative features while maintaining data privacy.

**Scalability Targets**:
- 10-50 researchers per installation
- 1,000-10,000 publications per researcher
- Sub-2-second page load times
- Concurrent access support

**Performance Optimizations**:
- Database indexes on frequently queried fields (year, DOI, user_id)
- GIN indexes for JSONB full-text search
- Django query optimization with select_related/prefetch_related
- Pagination for large publication lists
- Connection pooling for database efficiency

**User Isolation**:
```python
class UserScopedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)

class Publication(models.Model):
    owner = models.ForeignKey(AcademicUser, on_delete=models.CASCADE)
    objects = UserScopedManager()
```

---

## Technology Stack Finalization

**Core Stack**:
- **Backend**: Django 4.2+ (LTS)
- **Database**: PostgreSQL 14+
- **Authentication**: django-allauth with ORCID provider
- **Frontend**: Django templates with Bootstrap 5 (minimal JavaScript)
- **Testing**: pytest + Django TestCase
- **Deployment**: Docker containers

**Key Dependencies**:
```python
# pyproject.toml additions
dependencies = [
    "django>=4.2,<5.0",
    "psycopg2-binary>=2.9.0",
    "django-allauth>=0.57.0",
    "django-extensions>=3.2.0",
    # Existing academic API dependencies preserved
    "scholarly>=1.7.11",
    "crossrefapi>=1.6.0",
    "pybliometrics>=4.1",
    "orcid>=1.0.3",
]
```

**Development Environment**:
- PostgreSQL via Docker for local development
- Django development server
- pytest for testing with real PostgreSQL instance
- django-admin for data management interface

---

## Risk Assessment & Mitigation

**Migration Risks**:
1. **Data Loss** - Mitigated by comprehensive validation framework
2. **Downtime** - Mitigated by dual-write migration strategy  
3. **Performance Regression** - Mitigated by PostgreSQL query optimization
4. **User Adoption** - Mitigated by familiar ORCID authentication

**Technical Debt Reduction**:
- Replace Flask with mature Django framework
- Eliminate MongoDB-Django integration complexity
- Standardize on PostgreSQL for simpler operations
- Leverage Django ecosystem for admin, forms, testing

---

## Next Steps (Phase 1)

1. **Data Model Design** - Define Django models with JSONB fields
2. **API Contracts** - Design REST endpoints for CRUD operations
3. **Migration Scripts** - Implement MongoDB → PostgreSQL migration tools
4. **Authentication Setup** - Configure django-allauth with ORCID
5. **Test Framework** - Create comprehensive test suites

**Success Criteria**:
- All existing MongoDB collections mapped to Django models
- Zero data loss during migration validation
- Authentication working with test ORCID accounts
- Basic CRUD operations functional through web interface
- Existing CLI tools remain functional during transition

---

*Research phase complete - ready for Phase 1 design and contracts.*