# Docker Database Analysis: PostgreSQL vs SQLite

## Current State Analysis

### PostgreSQL Usage in Current Codebase
**Limited PostgreSQL-specific features currently used:**
1. **Full-text search** (migration 0014_add_fulltext_search.py)
   - `search_vector` column with tsvector type
   - GIN index on search_vector
   - Used in publication search functionality
2. **GIN indexes** (commented out in models.py for SQLite compatibility)
   - Would provide faster JSON field queries
   - Currently disabled for SQLite compatibility
3. **Advanced JSON queries** (minimal usage)
   - Some JSONField lookups in views.py

### Current Database Configuration
The app already supports **dual database configuration**:
- Environment variable `USE_POSTGRES=false` switches to SQLite
- Settings handle both PostgreSQL and SQLite gracefully
- Tests run on SQLite successfully with 95 passing tests

## PostgreSQL vs SQLite Comparison for Docker Distribution

### PostgreSQL Advantages ✅
1. **Production-ready** for multi-user environments
2. **Advanced search capabilities** (full-text search with tsvector)
3. **Better JSON field performance** with GIN indexes
4. **Concurrent access** handling
5. **Data integrity** with better transaction support
6. **Scalability** for larger datasets
7. **Backup/restore** tools (pg_dump, pg_restore)

### PostgreSQL Disadvantages ❌
1. **Complex Docker setup** requires multi-container architecture
2. **Resource overhead** (~100MB+ memory for PostgreSQL server)
3. **Persistent volumes** needed for data storage
4. **Network configuration** between containers
5. **Initial setup complexity** for users
6. **Database initialization** steps required
7. **Port conflicts** potential on user machines

### SQLite Advantages ✅
1. **Zero-configuration** - single file database
2. **Minimal resource usage** (~1MB memory overhead)
3. **Simple Docker setup** - single container
4. **No external dependencies**
5. **Easy backup** - just copy the .sqlite3 file
6. **No port conflicts**
7. **Immediate startup** - no database server initialization
8. **File-based** - easy to examine and debug
9. **Cross-platform** portability

### SQLite Disadvantages ❌
1. **Limited full-text search** (no tsvector support)
2. **No GIN indexes** for JSON performance
3. **Single writer** limitation (less relevant for single-user containers)
4. **Fewer advanced features**
5. **File locking** issues if shared across containers

## Recommendation: **SQLite for Docker Distribution** 🎯

### Rationale
1. **Simplicity wins for distribution** - Users want to run `docker run` and have it work
2. **Current PostgreSQL usage is minimal** - Only search functionality would be affected
3. **App already works well with SQLite** - 95 passing tests prove compatibility
4. **Target audience** - Academic researchers who want to try the tool, not run production deployments
5. **Fallback options available** - Advanced users can still use PostgreSQL with docker-compose

### Implementation Strategy

#### Phase 1: SQLite-First Docker Image (Recommended)
**Single container with SQLite for maximum simplicity:**

```dockerfile
FROM python:3.12-slim
# Simple, single-container setup with SQLite
# Sets USE_POSTGRES=false by default
# Includes volume mount for database persistence
```

**User experience:**
```bash
# Simple one-command setup
docker run -p 8000:8000 -v academicdb_data:/app/data academicdb:latest

# Optional environment file
docker run -p 8000:8000 --env-file .env academicdb:latest
```

#### Phase 2: PostgreSQL Option via Docker Compose
**For advanced users who want PostgreSQL:**

```yaml
# docker-compose.yml for PostgreSQL setup
version: '3.8'
services:
  web:
    image: academicdb:latest
    environment:
      - USE_POSTGRES=true
  db:
    image: postgres:15
```

## Detailed Implementation Plan

### 1. SQLite Optimizations Needed

**Search Functionality Fallback:**
```python
# In models.py - Add SQLite-compatible search
def search(cls, query, user=None):
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql':
        # Use PostgreSQL full-text search
        return cls._postgresql_search(query, user)
    else:
        # Use SQLite LIKE-based search
        return cls._sqlite_search(query, user)

def _sqlite_search(cls, query, user=None):
    # Simple but effective search using LIKE queries
    publications = cls.objects.filter(owner=user) if user else cls.objects.all()
    return publications.filter(
        Q(title__icontains=query) |
        Q(publication_name__icontains=query) |
        Q(metadata__abstract__icontains=query)
    ).distinct()
```

**Remove PostgreSQL dependencies from models:**
```python
# Conditional imports in models.py
try:
    from django.contrib.postgres.indexes import GinIndex
    from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
```

### 2. Docker Configuration

**Dockerfile (SQLite-first):**
```dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY pyproject.toml ./
RUN pip install -e .

# Copy application code
COPY . .

# Set default environment variables
ENV USE_POSTGRES=false
ENV DEBUG=false
ENV SECRET_KEY=docker-default-key-change-in-production

# Create database directory for SQLite
RUN mkdir -p /app/data

# Run migrations and collect static files
RUN python manage.py migrate
RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/ || exit 1

# Start command
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

**docker-compose.yml (PostgreSQL option):**
```yaml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - USE_POSTGRES=true
      - DB_HOST=db
      - DB_NAME=academicdb
      - DB_USER=postgres
      - DB_PASSWORD=academicdb_password
    depends_on:
      - db
    volumes:
      - ./media:/app/media

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=academicdb
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=academicdb_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

### 3. Configuration Changes Needed

**Update settings/base.py:**
```python
# Default to SQLite for Docker deployments
if os.getenv('USE_POSTGRES', 'false').lower() == 'true':
    # PostgreSQL configuration
else:
    # SQLite configuration with volume mount
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.getenv('SQLITE_PATH', BASE_DIR / 'data' / 'db.sqlite3'),
        }
    }
```

**Add Docker-specific settings:**
```python
# settings/docker.py
from .base import *

# Docker-specific overrides
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '*']

# Static files for production
STATIC_ROOT = '/app/staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = '/app/media'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
```

## Migration Strategy

### Step 1: Prepare SQLite Compatibility
1. ✅ **Already done** - App works with SQLite (tests passing)
2. Add conditional PostgreSQL imports
3. Implement SQLite-compatible search fallback
4. Test all functionality with `USE_POSTGRES=false`

### Step 2: Create Docker Images
1. Build SQLite-first Dockerfile
2. Test single-container deployment
3. Create PostgreSQL docker-compose option
4. Document both deployment methods

### Step 3: Distribution
1. **Primary**: Distribute SQLite Docker image for simplicity
2. **Advanced**: Provide PostgreSQL docker-compose for production use
3. **Documentation**: Clear setup instructions for both options

## User Experience Comparison

### SQLite Docker (Recommended for distribution)
```bash
# One command setup
docker run -p 8000:8000 -v academicdb_data:/app/data academicdb:latest

# Visit http://localhost:8000
# Database persists in named volume
```

### PostgreSQL Docker Compose
```bash
# Multi-step setup
curl -O https://raw.githubusercontent.com/org/repo/docker-compose.yml
docker-compose up -d

# Visit http://localhost:8000
# Full PostgreSQL features available
```

## Conclusion

**SQLite is the clear winner for Docker distribution** because:

1. **Simplicity**: Single command deployment vs multi-container setup
2. **Reliability**: No database connection issues or initialization problems
3. **Resource efficiency**: Runs on any machine without overhead
4. **Current compatibility**: App already works perfectly with SQLite
5. **User experience**: Academic researchers can try the tool instantly

The PostgreSQL-specific features (advanced search, GIN indexes) are **nice-to-have** but not **essential** for the core functionality. Users who need these features can use the PostgreSQL docker-compose option.

**Recommended approach**: Build SQLite-first Docker image as the primary distribution method, with PostgreSQL docker-compose as an advanced option for production deployments.