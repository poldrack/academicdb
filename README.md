# Academic Database Management System

A comprehensive Django-based academic database management system for researchers to track publications, funding, teaching, talks, and conferences with seamless integration to academic APIs.

## Features

### Core Functionality

- **ORCID Authentication**: Secure login via ORCID OAuth
- **Publication Management**: Track and manage academic publications with full metadata
- **Funding Tracking**: Manage grants and funding sources with role and status tracking
- **Teaching Records**: Document courses taught with enrollment and institution details
- **Talks & Conferences**: Track invited talks and conference presentations
- **Multi-Source Synchronization**: Automated data import from ORCID, PubMed, Scopus, and CrossRef
- **Spreadsheet Interface**: Excel-like bulk editing for efficient data management
- **CSV Import/Export**: Bulk data operations with custom field mapping
- **Edit Protection**: Manual edits preserved during API synchronization

### Key Integrations

- **ORCID**: Authentication and publication/funding synchronization
- **PubMed**: Query-based publication discovery and metadata enrichment
- **Scopus**: Author ID-based publication retrieval and citation data
- **CrossRef**: DOI metadata enrichment and publication type detection

## Installation

### Prerequisites

- Python 3.9+
- PostgreSQL 12+
- ORCID API credentials (for authentication)
- Scopus API key (optional, for Scopus integration)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/academicdb2.git
cd academicdb2
```

2. Install dependencies using uv:
```bash
uv sync
```

3. Set up environment variables:
```bash
# Create .env file with:
DATABASE_URL=postgresql://user:password@localhost/academicdb
SECRET_KEY=your-secret-key
ORCID_CLIENT_ID=your-orcid-client-id
ORCID_CLIENT_SECRET=your-orcid-client-secret
SCOPUS_API_KEY=your-scopus-api-key  # Optional
```

4. Run database migrations:
```bash
uv run python manage.py migrate
```

5. Create a superuser (optional):
```bash
uv run python manage.py createsuperuser
```

6. Run the development server:
```bash
uv run python manage.py runserver
```

Visit http://localhost:8000 to access the application.

## Usage

### Web Interface

1. **Login**: Authenticate using your ORCID account
2. **Dashboard**: View sync status and statistics
3. **Publications**: Manage your publication list with search and filtering
4. **Funding**: Track grants and funding sources
5. **Teaching/Talks/Conferences**: Use spreadsheet interfaces for bulk editing
6. **Sync**: Import data from external sources with real-time progress tracking

### API Endpoints

The application provides RESTful APIs for programmatic access:

- `/api/v1/publications/` - Publication CRUD operations
- `/api/v1/teaching/` - Teaching record management
- `/api/v1/talks/` - Talk record management
- `/api/v1/conferences/` - Conference presentation management

All endpoints require authentication and return user-scoped data.

## Management Commands

The system includes comprehensive Django management commands for data operations:

### Data Synchronization

```bash
# Comprehensive sync from all sources
uv run python manage.py comprehensive_sync [--user-id ID]

# Sync from specific sources
uv run python manage.py sync_orcid [--user-id ID]
uv run python manage.py sync_pubmed --user-id ID [--query "search query"]
uv run python manage.py sync_scopus --user-id ID [--scopus-id SCOPUS_ID]

# Enhanced Scopus sync with author ID capture
uv run python manage.py sync_scopus_enhanced --user-id ID
```

### Data Enrichment

```bash
# Enrich with CrossRef metadata
uv run python manage.py enrich_crossref [--user-id ID]

# Enrich with PubMed data
uv run python manage.py enrich_pubmed --email your@email.com [--user-id ID]

# Add Scopus author IDs
uv run python manage.py enrich_author_scopus_ids [--user-id ID]

# Lookup PMC IDs
uv run python manage.py lookup_pmc_ids [--user-id ID]
```

### Data Management

```bash
# Clear data (with confirmation)
uv run python manage.py clear_publications --user-id ID --confirm
uv run python manage.py clear_funding --user-id ID --confirm

# Import CSV data
uv run python manage.py import_csv --user-id ID --teaching-file teaching.csv

# Backup database
uv run python manage.py backup_db [--output-dir backups/]
```

### Data Quality

```bash
# Deduplicate DOIs
uv run python manage.py deduplicate_doi_case [--auto-merge]

# Detect preprints
uv run python manage.py detect_preprints

# Consolidate author cache
uv run python manage.py consolidate_author_cache

# Extract coauthors
uv run python manage.py extract_coauthors --user-id ID
```

### Diagnostics

```bash
# Test sync performance
uv run python manage.py test_sync_diagnostic --user-id ID

# Populate author cache
uv run python manage.py populate_author_cache --user-id ID
```

### Common Command Options

Most commands support these options:
- `--dry-run`: Preview changes without modifying data
- `--user-id ID`: Target specific user
- `--force`: Override safety checks
- `--rate-limit N`: API call throttling (seconds)

## Data Models

### Core Models

- **AcademicUser**: Extended user model with ORCID integration and academic profile
- **Publication**: Flexible publication tracking with JSONB metadata fields
- **Funding**: Grant and funding source management
- **Teaching**: Course and teaching activity records
- **Talk**: Invited talks and speaking engagements
- **Conference**: Conference presentations and papers
- **AuthorCache**: Intelligent author name normalization and matching

### Key Features

- **User Data Isolation**: All data scoped to authenticated users
- **Edit Protection**: Manual edits preserved during API synchronization
- **Flexible Metadata**: JSONB fields for varying API response structures
- **Full-Text Search**: PostgreSQL text search capabilities
- **Audit Trails**: Comprehensive edit history tracking

## Architecture

- **Framework**: Django 4.2+ with PostgreSQL
- **Authentication**: django-allauth with ORCID OAuth
- **Frontend**: Bootstrap 5 with minimal JavaScript
- **API**: Django REST Framework
- **Database**: PostgreSQL with JSONB for flexible schemas
- **Background Tasks**: Threading for long-running operations
- **Real-time Updates**: Server-Sent Events for progress tracking

## Development

### Project Structure

```
academicdb2/
├── academic/                 # Main Django app
│   ├── models.py            # Database models
│   ├── views.py             # Web and API views
│   ├── serializers.py       # DRF serializers
│   ├── management/          # Management commands
│   │   └── commands/        # Individual command files
│   └── templates/           # Django templates
├── academicdb_web/          # Django project settings
├── src/academicdb/          # Legacy CLI tools (preserved)
└── manage.py               # Django management script
```

### Testing

Run tests with:
```bash
uv run python manage.py test
```

### Contributing

1. Create a feature branch
2. Write failing tests first (TDD)
3. Implement minimal code to pass tests
4. Ensure user data isolation
5. Submit pull request

## Performance Targets

- Dashboard load: <2 seconds
- Publication search: <500ms
- API responses: <200ms median
- Support 50+ concurrent users
- Handle 10,000+ publications per user

## Security

- ORCID OAuth for authentication
- User data isolation at database level
- CSRF protection for all forms
- Input validation for external API data
- Comprehensive audit trails

## Legacy CLI Tool

The original academicdb command-line tool is preserved in `src/academicdb/` for compatibility. It provides:

- `dbbuilder`: Build academic database from APIs
- `render_cv`: Generate LaTeX/PDF CV from database
- `get_collaborators`: Create NSF collaborators spreadsheet

See [Legacy CLI Documentation](src/academicdb/README.md) for details on the original MongoDB-based tool.

## License

[Specify your license here]

## Support

For issues and feature requests, please use the GitHub issue tracker.
