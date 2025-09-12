# Claude Code Context: Academic Database Web Interface

## Project Overview
Django-based academic database management system with ORCID authentication, PostgreSQL backend, and comprehensive publication/collaboration tracking. Migrating from Flask+MongoDB to Django+PostgreSQL for better ecosystem integration.

## Current Architecture
**Framework**: Django 4.2+ with PostgreSQL and JSONB fields  
**Authentication**: django-allauth with ORCID OAuth provider  
**Database**: PostgreSQL with hybrid relational+document approach  
**Frontend**: Django templates + Bootstrap 5 (minimal JavaScript)  
**APIs**: Integration with Scopus, PubMed, CrossRef, ORCID, Google Scholar

## Key Models
```python
# Core entities with user-scoped data
class AcademicUser(AbstractUser):
    orcid_id = CharField(max_length=19, unique=True)
    institution = CharField(max_length=200)
    research_areas = JSONField(default=list)

class Publication(models.Model):
    owner = ForeignKey(AcademicUser, on_delete=CASCADE)
    doi = CharField(max_length=255, unique=True, db_index=True)
    title = TextField()
    year = IntegerField(db_index=True)
    
    # Flexible metadata in JSONB
    metadata = JSONField(default=dict)  # API-specific data
    authors = JSONField(default=list)   # Author details
    identifiers = JSONField(default=dict)  # PMID, PMCID, Scopus ID
    
    # Edit tracking for API sync preservation
    manual_edits = JSONField(default=dict)  # {"title": true}
    edit_history = JSONField(default=list)  # Audit trail
    
    class Meta:
        indexes = [GinIndex(fields=['metadata', 'authors'])]
```

## Critical Features
1. **Edit Preservation**: Manual edits protected during external API synchronization
2. **User Isolation**: All data scoped to authenticated ORCID users  
3. **Flexible Schema**: JSONB fields for varying API response structures
4. **Full-Text Search**: PostgreSQL text search for publications
5. **Collaboration Tracking**: NSF collaborator spreadsheet generation
6. **CV Export**: LaTeX/PDF generation from database

## Database Migration Strategy
**Phase 1**: Dual-write (MongoDB + PostgreSQL)  
**Phase 2**: Validation and testing  
**Phase 3**: Switch to PostgreSQL-only  
**Preservation**: Existing CLI tools maintain compatibility

## API Patterns
```python
# Django REST Framework with user-scoped querysets
class PublicationViewSet(ModelViewSet):
    def get_queryset(self):
        return Publication.objects.filter(owner=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
```

## Testing Requirements
- TDD with failing tests first (constitutional requirement)
- Real PostgreSQL database for integration tests
- ORCID sandbox API testing
- Performance testing for academic-scale datasets (1000+ publications)

## Development Workflow
1. Write failing tests for new functionality
2. Implement minimal code to pass tests  
3. Refactor while maintaining test coverage
4. Ensure user data isolation in all operations

## Recent Changes
- Migrating from Flask+MongoDB to Django+PostgreSQL
- Adding ORCID OAuth authentication
- Implementing field-level edit tracking
- Creating REST API contracts
- Designing data migration strategy

## Performance Targets
- Dashboard load: <2 seconds
- Publication search: <500ms  
- API responses: <200ms median
- Support 50+ concurrent researchers
- Handle 10,000+ publications per user

## Security Considerations
- ORCID OAuth for researcher authentication
- User data isolation at database level
- CSRF protection for all forms
- Input validation for all external API data
- Audit trails for sensitive operations

## Dependencies
```python
# Key packages
django>=4.2
psycopg2-binary>=2.9
django-allauth>=0.57
django-extensions>=3.2
djangorestframework>=3.14

# Academic API integrations (preserved from original)
scholarly>=1.7.11
pybliometrics>=4.1
crossrefapi>=1.6.0
orcid>=1.0.3
```

## Common Patterns
- All models inherit user ownership via ForeignKey to AcademicUser
- JSONB fields for flexible metadata with GIN indexes
- Manual edit tracking with boolean flags in metadata
- Bulk operations for external API synchronization
- Django management commands for data operations

## File Structure
```
academicdb_web/          # Django project
├── settings.py
├── urls.py
└── wsgi.py

academicdb/              # Main Django app  
├── models.py           # Database models
├── views.py            # API views and web views
├── serializers.py      # DRF serializers
├── forms.py            # Django forms
├── management/         # Management commands
│   └── commands/
│       ├── sync_external.py
│       └── migrate_from_mongo.py
└── templates/          # Django templates

src/academicdb/         # Existing CLI tools (preserved)
└── [existing Python package structure]
```

This system serves academic researchers who need to manage publication databases, track collaborations for grant reporting (NSF), and generate CVs programmatically while maintaining integration with academic APIs.