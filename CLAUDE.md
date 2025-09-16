# Claude Code Context: Academic Database Web Interface

## Project Overview
Django-based academic database management system with ORCID authentication, PostgreSQL backend, and comprehensive publication/collaboration tracking. Migrating from Flask+MongoDB to Django+PostgreSQL for better ecosystem integration.

**TESTING STATUS**: Comprehensive testing framework implemented with 80%+ coverage target. Current phase: regression and integration tests.

## Current Architecture
**Framework**: Django 4.2+ with PostgreSQL and JSONB fields
**Authentication**: django-allauth with ORCID OAuth provider
**Database**: PostgreSQL with hybrid relational+document approach
**Frontend**: Django templates + Bootstrap 5 (minimal JavaScript)
**APIs**: Integration with Scopus, PubMed, CrossRef, ORCID, Google Scholar
**Testing**: pytest + factory-boy + comprehensive test suite

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

## Testing Implementation (COMPLETED)
**Framework**: pytest + factory-boy + responses + freezegun
**Coverage Target**: 80%+ overall, 90%+ for critical paths
**Test Types**:
- Unit tests (35 tests): User isolation, edit preservation, authentication
- Characterization tests (11 tests): Document current model behavior
- Regression tests (API contracts, model behavior): Prevent breaking changes
- Integration tests: External API mocking with responses library
- Performance tests: Load testing and baseline metrics

**Test Infrastructure**:
- SQLite for fast unit tests, PostgreSQL option for integration tests
- Model factories for realistic test data generation
- External API mocking to prevent network dependencies
- Comprehensive fixtures for common test scenarios

## Development Workflow (Updated for Existing Codebase)
1. **Characterization tests first**: Document current behavior before changes
2. **Risk-based testing**: Prioritize critical paths (user isolation, edit preservation)
3. **Regression prevention**: Lock in API contracts and model behavior
4. **Integration verification**: Test external API interactions with mocks
5. **Performance baselines**: Establish benchmarks for optimization

## Testing Commands (Makefile)
```bash
make test                    # Run all tests
make test-unit              # Run unit tests only
make test-characterization  # Run characterization tests
make test-coverage          # Run tests with coverage report
make coverage-report        # Show coverage summary
```

## Recent Changes
- **COMPLETED**: Comprehensive testing framework implementation
- **COMPLETED**: User data isolation tests (critical security requirement)
- **COMPLETED**: Edit preservation tests (core business logic protection)
- **COMPLETED**: API contract regression tests
- **IN PROGRESS**: Performance baseline establishment
- Migrating from Flask+MongoDB to Django+PostgreSQL
- Adding ORCID OAuth authentication
- Implementing field-level edit tracking

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
├── settings/           # Settings package
│   ├── base.py        # Base settings
│   └── test.py        # Test-specific settings
├── urls.py
└── wsgi.py

academic/               # Main Django app
├── models.py          # Database models
├── views.py           # API views and web views
├── serializers.py     # DRF serializers
├── api_views.py       # API ViewSets
├── api_urls.py        # API URL routing
├── management/        # Management commands
└── templates/         # Django templates

tests/                 # Comprehensive test suite
├── conftest.py       # Test fixtures and configuration
├── factories.py      # Model factories for test data
├── unit/             # Unit tests (35 tests)
│   ├── test_user_data_isolation.py
│   ├── test_edit_preservation.py
│   └── test_authentication.py
├── characterization/ # Current behavior tests (11 tests)
├── regression/       # Regression prevention tests
├── integration/      # External API integration tests
└── performance/      # Load and performance tests

src/academicdb/       # Legacy CLI tools (preserved)
└── [existing Python package structure]
```

This system serves academic researchers who need to manage publication databases, track collaborations for grant reporting (NSF), and generate CVs programmatically while maintaining integration with academic APIs.