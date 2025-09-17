# Academic Database Docker Deployment Guide

This guide provides multiple Docker deployment options for the Academic Database, optimized for different use cases from simple testing to production deployments.

## Quick Start (Recommended)

The simplest way to run Academic Database is using the SQLite-based Docker image:

```bash
# Pull and run the latest image
docker run -d \
  --name academicdb \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  academicdb:latest

# Access the application
open http://localhost:8000
```

## Deployment Options

### 1. Simple Docker Run (SQLite) ⭐ **Recommended for trying the app**

**Best for**: Testing, development, single-user academic use

```bash
# Basic deployment
docker run -d \
  --name academicdb \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  -e SECRET_KEY=your-secret-key-here \
  academicdb:latest

# With superuser creation
docker run -d \
  --name academicdb \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  -e SECRET_KEY=your-secret-key-here \
  -e DJANGO_SUPERUSER_USERNAME=admin \
  -e DJANGO_SUPERUSER_EMAIL=admin@example.com \
  -e DJANGO_SUPERUSER_PASSWORD=secure_password \
  academicdb:latest
```

**Features:**
- ✅ Zero configuration
- ✅ Single container
- ✅ Persistent data via volume
- ✅ ~50MB memory usage
- ✅ SQLite search functionality
- ❌ No advanced full-text search

### 2. Docker Compose (SQLite)

**Best for**: Organized development, easy management

```bash
# Clone or download docker-compose.sqlite.yml
curl -o docker-compose.yml https://raw.githubusercontent.com/yourrepo/academicdb/main/docker-compose.sqlite.yml

# Edit environment variables in docker-compose.yml
# Then start
docker-compose up -d

# View logs
docker-compose logs -f web
```

### 3. Docker Compose (PostgreSQL) 🚀 **Recommended for production**

**Best for**: Production use, advanced search features, multi-user

```bash
# Clone or download docker-compose.yml
curl -o docker-compose.yml https://raw.githubusercontent.com/yourrepo/academicdb/main/docker-compose.yml

# Edit environment variables (especially passwords!)
# Then start
docker-compose up -d

# View logs
docker-compose logs -f web
```

**Features:**
- ✅ Full PostgreSQL features
- ✅ Advanced full-text search
- ✅ Better performance for large datasets
- ✅ Production-ready
- ❌ More complex setup
- ❌ Higher resource usage

## Environment Variables

### Essential Variables
```bash
SECRET_KEY=your-secret-key-here-change-in-production
DEBUG=false                    # Set to true for development only
USE_POSTGRES=false            # Set to true for PostgreSQL
```

### Optional Superuser Creation
```bash
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=secure_password
```

### Database Configuration (SQLite)
```bash
SQLITE_PATH=/app/data/db.sqlite3  # Default path
```

### Database Configuration (PostgreSQL)
```bash
USE_POSTGRES=true
DB_HOST=db                    # Database host
DB_NAME=academicdb           # Database name
DB_USER=postgres             # Database user
DB_PASSWORD=secure_password  # Database password
DB_PORT=5432                 # Database port
```

### Advanced Configuration
```bash
# Security
ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com
USE_HTTPS=true               # Enable if using HTTPS

# Logging
LOG_LEVEL=INFO               # DEBUG, INFO, WARNING, ERROR
DJANGO_LOG_LEVEL=INFO
APP_LOG_LEVEL=INFO

# Performance
API_THROTTLE_ANON=100/hour
API_THROTTLE_USER=1000/hour

# Session
SESSION_COOKIE_AGE=86400     # 24 hours in seconds

# Email (for notifications)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
```

## Volume Management

### SQLite Volumes
```bash
# List volumes
docker volume ls

# Backup SQLite database
docker run --rm -v academicdb_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/academicdb_backup_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Restore SQLite database
docker run --rm -v academicdb_data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/academicdb_backup.tar.gz -C /data
```

### PostgreSQL Volumes
```bash
# Backup PostgreSQL (if using docker-compose)
docker-compose exec db pg_dump -U postgres academicdb > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore PostgreSQL
docker-compose exec -T db psql -U postgres academicdb < backup.sql
```

## Building from Source

```bash
# Clone repository
git clone https://github.com/yourrepo/academicdb.git
cd academicdb

# Build image
docker build -t academicdb:local .

# Run locally built image
docker run -d \
  --name academicdb-local \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  academicdb:local
```

## Production Deployment

### Security Checklist
- [ ] Change default `SECRET_KEY`
- [ ] Set `DEBUG=false`
- [ ] Configure proper `ALLOWED_HOSTS`
- [ ] Use strong database passwords
- [ ] Enable HTTPS with `USE_HTTPS=true`
- [ ] Remove exposed database ports (5432) from docker-compose
- [ ] Configure proper logging
- [ ] Set up regular backups

### Recommended Production Setup
```bash
# 1. Create .env file
cat > .env << EOF
SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
DEBUG=false
USE_POSTGRES=true
DB_PASSWORD=$(openssl rand -base64 32)
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
USE_HTTPS=true
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@yourdomain.com
DJANGO_SUPERUSER_PASSWORD=$(openssl rand -base64 32)
EOF

# 2. Use production docker-compose
docker-compose -f docker-compose.yml --env-file .env up -d

# 3. Set up reverse proxy (nginx, traefik, etc.)
# 4. Configure SSL certificates
# 5. Set up monitoring and backups
```

## Troubleshooting

### Common Issues

**Container won't start:**
```bash
# Check logs
docker logs academicdb

# Common causes:
# - Invalid SECRET_KEY
# - Database connection issues (PostgreSQL)
# - Permission issues with volumes
```

**Database migration errors:**
```bash
# Reset database (SQLite)
docker volume rm academicdb_data
docker run ...  # Start fresh

# Reset database (PostgreSQL)
docker-compose down -v
docker-compose up -d
```

**Cannot access application:**
```bash
# Check if container is running
docker ps

# Check port mapping
docker port academicdb

# Check firewall/network settings
curl http://localhost:8000/admin/login/
```

**Performance issues:**
```bash
# Check resource usage
docker stats academicdb

# For SQLite: Consider PostgreSQL for large datasets
# For PostgreSQL: Tune database settings
```

### Health Checks

```bash
# Check application health
curl http://localhost:8000/admin/login/

# Check database connectivity (PostgreSQL)
docker-compose exec db pg_isready -U postgres

# Check logs for errors
docker-compose logs --tail=50 web
```

## Upgrading

### SQLite Deployment
```bash
# Backup data
docker run --rm -v academicdb_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/backup.tar.gz -C /data .

# Stop and remove old container
docker stop academicdb && docker rm academicdb

# Pull new image and start
docker pull academicdb:latest
docker run -d \
  --name academicdb \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  academicdb:latest
```

### PostgreSQL Deployment
```bash
# Backup database
docker-compose exec db pg_dump -U postgres academicdb > backup.sql

# Update and restart
docker-compose pull
docker-compose up -d
```

## Development Setup

```bash
# Development with auto-reload
docker run -d \
  --name academicdb-dev \
  -p 8000:8000 \
  -v academicdb_data:/app/data \
  -v $(pwd):/app \
  -e DEBUG=true \
  -e DJANGO_SETTINGS_MODULE=academicdb_web.settings.docker \
  academicdb:latest \
  python manage.py runserver 0.0.0.0:8000

# Run tests
docker run --rm \
  -v $(pwd):/app \
  academicdb:latest \
  python -m pytest tests/
```

## Support

- **Documentation**: See README.md for application-specific documentation
- **Issues**: Report bugs at https://github.com/yourrepo/academicdb/issues
- **Discussions**: Community support at https://github.com/yourrepo/academicdb/discussions

## Comparison: SQLite vs PostgreSQL

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| Setup Complexity | ⭐⭐⭐⭐⭐ Simple | ⭐⭐⭐ Moderate |
| Resource Usage | ⭐⭐⭐⭐⭐ Minimal | ⭐⭐⭐ Higher |
| Search Quality | ⭐⭐⭐ Good | ⭐⭐⭐⭐⭐ Excellent |
| Scalability | ⭐⭐⭐ Limited | ⭐⭐⭐⭐⭐ High |
| Backup/Restore | ⭐⭐⭐⭐ Easy | ⭐⭐⭐⭐ Standard |
| Multi-user | ⭐⭐ Limited | ⭐⭐⭐⭐⭐ Excellent |

**Recommendation**: Start with SQLite for simplicity, upgrade to PostgreSQL when you need advanced features or expect high usage.