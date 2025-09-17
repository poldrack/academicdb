# Data Ingestion Directory

This directory is used for CSV data file ingestion during the "Sync All Databases" operation.

## Supported CSV Files

Place the following CSV files in this directory to have them automatically ingested during sync:

### 1. `additional_pubs.csv`
Additional publications not available through API sources.

**Required columns:**
- `title` - Publication title
- `authors` - Authors (semicolon-separated)
- `year` - Publication year
- `doi` - Digital Object Identifier (optional)
- `journal` - Journal name (optional)

### 2. `conferences.csv`
Conference presentations and proceedings.

**Required columns:**
- `title` - Presentation title
- `authors` - Authors
- `year` - Conference year
- `venue` - Conference name
- `location` - Conference location

### 3. `editorial.csv`
Editorial activities and board memberships.

**Required columns:**
- `role` - Editorial role (e.g., Editor, Editorial Board)
- `journal` - Journal name
- `dates` - Date range (e.g., "2020-2024")

### 4. `links.csv`
Links to additional resources for publications.

**Required columns:**
- `publication_title` - Title of the publication to link to
- `link_type` - Type of link (Code, Data, OSF, Other)
- `url` - URL of the resource
- `description` - Description of the linked resource

### 5. `talks.csv`
Invited talks and seminars.

**Required columns:**
- `title` - Talk title
- `venue` - Institution or venue
- `date` - Date (YYYY-MM-DD format)
- `type` - Talk type (invited, keynote, etc.)

### 6. `teaching.csv`
Teaching activities and courses.

**Required columns:**
- `course_name` - Course name
- `institution` - Institution name
- `year` - Year taught
- `role` - Teaching role (instructor, TA, etc.)

## Usage

### Local Development
Place your CSV files in this directory and run the sync:
```bash
# The data directory is automatically mounted when using Docker
make docker-run-orcid
# Then trigger sync from the web interface
```

### Docker Container
When running in Docker, this directory is mounted to `/app/datafiles` inside the container.
The application will automatically look for CSV files in this location during sync.

### Manual Path Specification
You can also specify a custom data directory path in the sync request if your files are located elsewhere.

## Important Notes

1. **File Encoding**: All CSV files should be UTF-8 encoded
2. **Headers**: The first row of each CSV must contain the column headers
3. **Deduplication**: The system will check for existing records to avoid duplicates
4. **Error Handling**: Invalid rows will be skipped and reported in the sync summary
5. **Directory Separation**: This directory is separate from the database directory (`/app/data`) to avoid conflicts

## Example CSV Format

### additional_pubs.csv
```csv
title,authors,year,doi,journal
"Example Paper Title","Smith, J.; Doe, A.",2023,10.1000/example,"Journal of Examples"
```

### conferences.csv
```csv
title,authors,year,venue,location
"Conference Presentation","Author, A.",2023,"International Conference","City, Country"
```