"""
Docker-specific Django settings.
This file contains settings optimized for Docker deployments.
"""

import os
from django.core.management.utils import get_random_secret_key
from .base import *

# Generate a secret key if not provided
SECRET_KEY = os.getenv('SECRET_KEY') or get_random_secret_key()

# Override settings for Docker environment
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

# Allow all hosts in Docker by default (can be restricted via environment)
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

# Force SQLite by default in Docker unless explicitly using PostgreSQL
if os.getenv('USE_POSTGRES', 'false').lower() != 'true':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.getenv('SQLITE_PATH', '/app/data/db.sqlite3'),
        }
    }

# Static files configuration for Docker
STATIC_URL = '/static/'
STATIC_ROOT = '/app/staticfiles'

# Media files configuration for Docker
MEDIA_URL = '/media/'
MEDIA_ROOT = '/app/media'

# Security settings for Docker
if not DEBUG:
    # Production security settings
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

    # Use secure cookies if HTTPS is available
    if os.getenv('USE_HTTPS', 'false').lower() == 'true':
        SECURE_SSL_REDIRECT = True
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True

# Logging configuration optimized for Docker
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': '/app/logs/django.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'] if not DEBUG else ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'academic': {
            'handlers': ['console', 'file'] if not DEBUG else ['console'],
            'level': os.getenv('APP_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

# Email configuration for Docker (using environment variables)
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
if EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
    EMAIL_HOST = os.getenv('EMAIL_HOST')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'true').lower() == 'true'
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
    DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@academicdb.local')

# Cache configuration (Redis optional for Docker)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'academicdb-cache',
    }
}

# Override with Redis if available
if os.getenv('REDIS_URL'):
    CACHES['default'] = {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.getenv('REDIS_URL'),
    }

# Session configuration for Docker
SESSION_COOKIE_AGE = int(os.getenv('SESSION_COOKIE_AGE', '86400'))  # 24 hours default
SESSION_EXPIRE_AT_BROWSER_CLOSE = os.getenv('SESSION_EXPIRE_AT_BROWSER_CLOSE', 'false').lower() == 'true'

# ORCID configuration for Docker
SOCIALACCOUNT_PROVIDERS = {
    'orcid': {
        'BASE_DOMAIN': os.getenv('ORCID_BASE_DOMAIN', 'orcid.org'),
        'MEMBER_API': os.getenv('ORCID_MEMBER_API', 'false').lower() == 'true',
        'VERIFIED_EMAIL': False,
    }
}

# Time zone configuration
TIME_ZONE = os.getenv('TIME_ZONE', 'UTC')
USE_TZ = True

# Internationalization
LANGUAGE_CODE = os.getenv('LANGUAGE_CODE', 'en-us')

# Database connection timeout for Docker
if 'postgresql' in DATABASES['default']['ENGINE']:
    DATABASES['default']['CONN_MAX_AGE'] = int(os.getenv('DB_CONN_MAX_AGE', '300'))
    DATABASES['default']['OPTIONS'] = {
        'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', '10')),
    }

# File upload settings for Docker
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('FILE_UPLOAD_MAX_MEMORY_SIZE', '2621440'))  # 2.5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('DATA_UPLOAD_MAX_MEMORY_SIZE', '2621440'))

# API throttling settings for Docker
REST_FRAMEWORK.update({
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.getenv('API_THROTTLE_ANON', '100/hour'),
        'user': os.getenv('API_THROTTLE_USER', '1000/hour'),
    }
})