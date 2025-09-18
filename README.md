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

## Prerequisites

### ORCID Developer Setup (Required)

Before installing the application, you need to register for ORCID API credentials:

1. **Create an ORCID account** (if you don't have one):
   - Visit https://orcid.org/register
   - Complete the registration process

2. **Register for developer tools**:
   - Go to https://orcid.org/developer-tools
   - Sign in with your ORCID account
   - Click "Register for the free ORCID public API"

3. **Create a new application**:
   - Fill out the application form:
     - **Application name**: Your application name (e.g., "My Academic Database")
     - **Application website**: http://127.0.0.1:8000 (for local development)
     - **Application description**: Brief description of your use case
   - **Important**: Set the **Redirect URI** to: `http://127.0.0.1:8000/accounts/orcid/login/callback/`
   - Submit the application

4. **Get your credentials**:
   - After approval (usually immediate), you'll receive:
     - **Client ID**: Use this for `ORCID_CLIENT_ID` in the .env file below
     - **Client Secret**: Use this for `ORCID_CLIENT_SECRET` in the .env file below

**Note**: For production deployment, you would need to register a separate application with your production domain and HTTPS redirect URI.  However, this project isn't really meant for a production deployment, since the required Scopus keys are going to be user-specific and linked to your institution. 

## Installation

### Docker Installation (Recommended for New Users)

The easiest way to get started is using Docker, which handles all dependencies and setup automatically.

#### Prerequisites

- Docker and Docker Compose installed on your system
- ORCID API credentials (for authentication)
- Scopus API key - in principle this is optional, but you would lose much of the functionality of the project

#### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/academicdb2.git
cd academicdb2
```

2. Create environment configuration:
```bash
# Copy the example environment file
cp .env.example .env

# Edit the .env file with your configuration:
nano .env
```

3. Configure your `.env` file with the following variables:
```bash
# Django Configuration
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

# ORCID API Configuration (Required)
# See ORCID setup instructions below
ORCID_CLIENT_ID=your-orcid-client-id
ORCID_CLIENT_SECRET=your-orcid-client-secret

# Optional API Keys
SCOPUS_API_KEY=your-scopus-api-key  # Get from https://dev.elsevier.com/
SCOPUS_INST_TOKEN=your-scopus-inst-token  # Optional - only required for Scopus access outside institutional network
```

4. Build and start the application:
```bash
# Build the Docker image
make docker-build

# Start the application with ORCID authentication
make docker-run-orcid
```

The `make docker-run-orcid` command will:
- Validate your ORCID credentials from the `.env` file
- Set up proper data persistence with volume mounts
- Start the container with all necessary environment variables

5. Access the application:
   - Web interface: http://localhost:8000
   - Admin interface: http://localhost:8000/admin/

6. Initial setup (optional):
```bash
# Create a superuser account
docker exec academicdb python manage.py createsuperuser

# Load sample data
docker exec academicdb python manage.py loaddata fixtures/sample_data.json
```

#### Docker Commands

```bash
# Stop the container
make docker-stop

# Remove the container
make docker-remove

# View logs
docker logs academicdb

# Follow logs in real-time
docker logs -f academicdb

# Access Django shell
docker exec -it academicdb python manage.py shell

# Run tests
docker exec academicdb python manage.py test

# Backup database
docker exec academicdb python manage.py backup_db

# Complete restart (clean build)
make docker-full-restart
```

### Local Installation

For development or if you prefer not to use Docker:

#### Prerequisites

- Python 3.9+
- ORCID API credentials (for authentication)
- Scopus API key (optional, for Scopus integration)

#### Setup

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
ORCID_CLIENT_ID=your-orcid-client-id
ORCID_CLIENT_SECRET=your-orcid-client-secret
SCOPUS_API_KEY=your-scopus-api-key  # Optional
SCOPUS_INST_TOKEN=your-scopus-inst-token  # Required for Scopus access outside institutional network
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

## Docker Hub Deployment

### Building and Publishing to Docker Hub

If you want to publish your own version of the Docker image to Docker Hub:

#### 1. Prerequisites
- Docker Hub account (https://hub.docker.com/)
- Docker with buildx support for multi-platform builds

#### 2. Build and Push Multi-Platform Image
```bash
# Login to Docker Hub
docker login

# Create and use a new builder instance for multi-platform builds
docker buildx create --use

# Build and push for both AMD64 and ARM64 architectures
docker buildx build --platform linux/amd64,linux/arm64 \
  -t yourusername/academicdb2:latest \
  -t yourusername/academicdb2:v1.0.0 \
  --push .
```

#### 3. Alternative: Single Platform Build
```bash
# For local testing or single platform
docker build -t yourusername/academicdb2:latest .

# Test locally
docker run -p 8000:8000 yourusername/academicdb2:latest

# Push to Docker Hub
docker push yourusername/academicdb2:latest
```

#### 4. Verify Deployment
```bash
# Test pulling and running from Docker Hub
docker pull yourusername/academicdb2:latest
# this needs to be run within the academicdb2 directory since it needs several files from there
docker run -p 8000:8000 yourusername/academicdb2:latest
```

**Note**: The multi-platform build ensures compatibility with both Intel/AMD processors and Apple Silicon (M1/M2) Macs.

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
```

### Database Backup & Restore

#### PostgreSQL Direct Dumps (Recommended for full database backup)

```bash
# Create PostgreSQL backup (multiple formats available)
uv run python manage.py backup_db [options]
  --format {sql,custom,tar}  # Backup format (default: custom)
  --compress                 # Compress SQL output with gzip
  --output-dir DIR          # Output directory (default: backups/)

# Examples:
uv run python manage.py backup_db --format custom  # Compressed binary format (recommended)
uv run python manage.py backup_db --format sql --compress  # Compressed SQL
uv run python manage.py backup_db --format tar     # TAR archive format

# Restore PostgreSQL backup
uv run python manage.py restore_db <backup_file> [options]
  --clean          # Drop existing objects before restore
  --no-owner       # Don't restore ownership
  --data-only      # Restore only data, not schema
  --schema-only    # Restore only schema, not data
  --force          # Skip confirmation prompt
  --create-db      # Create database before restore

# Examples:
uv run python manage.py restore_db backups/academicdb_backup_20250916.dump
uv run python manage.py restore_db backup.sql.gz --clean --force
```

#### JSON-based Backup (User-specific data export/import)

```bash
# Create JSON backup
uv run python manage.py backup_data [--output-dir backups/] [--user-id ID]

# Restore from JSON backup
uv run python manage.py restore_data <backup_dir> [--user-id ID] [--merge]
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
