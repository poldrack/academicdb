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
    mkdir -p /app/data
    echo "Using SQLite database at: $SQLITE_PATH"
fi

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Create superuser if environment variables are provided
if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_EMAIL" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Creating superuser..."
    python /app/create_superuser.py
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