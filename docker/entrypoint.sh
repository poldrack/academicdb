#!/bin/bash
set -e

# Academic Database Docker Entrypoint
# This script initializes the database and starts the application

echo "Starting Academic Database..."

# Wait for database if using PostgreSQL
if [ "$USE_POSTGRES" = "true" ]; then
    echo "Waiting for PostgreSQL..."
    while ! nc -z ${DB_HOST:-db} ${DB_PORT:-5432}; do
        sleep 1
    done
    echo "PostgreSQL started"
fi

# Ensure data directory exists for SQLite
if [ "$USE_POSTGRES" != "true" ]; then
    # Default to /app/data if SQLITE_PATH not specified
    DB_PATH="${SQLITE_PATH:-/app/data/db.sqlite3}"
    DB_DIR=$(dirname "$DB_PATH")

    # Create the database directory (could be user's local directory)
    mkdir -p "$DB_DIR"
    echo "Using SQLite database at: $DB_PATH"
    echo "Database directory: $DB_DIR"

    # Check if this is a fresh deployment (no database file exists)
    if [ ! -f "$DB_PATH" ]; then
        echo "🔧 Fresh deployment detected - creating new SQLite database"
        FRESH_DEPLOYMENT=true
    else
        echo "📊 Existing database found - checking migrations"
        FRESH_DEPLOYMENT=false
    fi
else
    echo "Using PostgreSQL database"
    FRESH_DEPLOYMENT=false
fi

# Setup SQLite-compatible migrations for Docker
echo "🔧 Preparing SQLite-compatible migrations..."
python /app/setup_migrations.py

# Initialize database with proper error handling
echo "🗄️  Initializing database..."

if [ "$FRESH_DEPLOYMENT" = "true" ]; then
    echo "   Creating all tables for new database..."
    # For fresh deployment, run migrations with more verbosity to catch issues
    python manage.py migrate --verbosity=1

    # Verify all expected tables were created
    echo "🔍 Verifying database structure..."
    python manage.py shell -c "
from django.db import connection
cursor = connection.cursor()
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;\")
tables = [t[0] for t in cursor.fetchall()]
expected_tables = ['academic_academicuser', 'academic_publication', 'academic_professionalactivity']
missing_tables = [t for t in expected_tables if t not in tables]
if missing_tables:
    print(f'❌ Missing critical tables: {missing_tables}')
    exit(1)
else:
    print(f'✅ Database initialized successfully with {len(tables)} tables')
    for table in sorted([t for t in tables if t.startswith('academic_')]):
        print(f'   {table}')
    "

    # Force sync to disk to ensure database is fully written
    echo "💾 Syncing database to disk..."
    sync
    sleep 2
else
    echo "   Applying any pending migrations..."
    python manage.py migrate --verbosity=0
fi

# Create superuser if environment variables are provided
if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_EMAIL" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Creating superuser..."
    python /app/create_superuser.py
fi

# Setup ORCID authentication if credentials are provided
if [ "$ORCID_CLIENT_ID" ] && [ "$ORCID_CLIENT_SECRET" ]; then
    echo "Setting up ORCID authentication..."
    python manage.py setup_orcid

    # Ensure database changes are fully committed
    python manage.py shell -c "
from django.db import connection
connection.close()
print('📝 Database connections closed')
"
else
    echo "⚠️  ORCID credentials not provided - ORCID authentication will be unavailable"
    echo "   To enable ORCID login, set ORCID_CLIENT_ID and ORCID_CLIENT_SECRET environment variables"
fi

# Collect static files if not in debug mode
if [ "$DEBUG" != "true" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput --clear
fi

# Create media directory if it doesn't exist
mkdir -p /app/media

echo "Initialization complete. Starting server..."

# Execute the main command
exec "$@"