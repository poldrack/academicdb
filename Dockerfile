# Academic Database Docker Image (SQLite-optimized)
# This Dockerfile creates a lightweight, single-container deployment
# using SQLite for maximum simplicity and portability.

FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libpq-dev \
    netcat-openbsd \
    pkg-config \
    texlive-xetex \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    && rm -rf /var/lib/apt/lists/*

# Create app user for security
RUN useradd --create-home --shell /bin/bash appuser

# Create necessary directories
RUN mkdir -p /app/data /app/media /app/staticfiles /app/logs && \
    chown -R appuser:appuser /app

# Copy only dependency files first (for better caching)
COPY pyproject.toml .

# Install only dependencies first (cached layer)
RUN pip install --upgrade pip && \
    pip install pandas numpy biopython scholarly crossrefapi tomli pybliometrics pymongo orcid tomli-w pytest toml ipython matplotlib django psycopg2-binary django-allauth django-extensions djangorestframework python-dotenv openpyxl dj-database-url coverage factory-boy faker freezegun model-bakery pytest-cov pytest-django pytest-xdist responses && \
    pip install gunicorn whitenoise

# Copy application code after dependencies are installed
COPY . .

# Install current project as editable (fast since deps already installed)
RUN pip install -e .

# Set ownership of app directory
RUN chown -R appuser:appuser /app

# Switch to app user
USER appuser

# Set default environment variables for Docker
ENV DJANGO_SETTINGS_MODULE=academicdb_web.settings.docker \
    USE_POSTGRES=false \
    DEBUG=false \
    SQLITE_PATH=/app/data/db.sqlite3

# Collect static files
RUN python manage.py collectstatic --noinput --clear

# Copy migration setup script
COPY --chown=appuser:appuser docker/setup_migrations.py /app/
RUN chmod +x /app/setup_migrations.py

# Create superuser script
COPY --chown=appuser:appuser docker/create_superuser.py /app/
RUN chmod +x /app/create_superuser.py

# Expose port
EXPOSE 8000

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/admin/login/ || exit 1

# Create entrypoint script
COPY --chown=appuser:appuser docker/entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (can be overridden)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "1800", "--keep-alive", "60", "academicdb_web.wsgi:application"]