#!/usr/bin/env python
"""
Verification script for Docker setup.
Tests that all components work correctly in the Docker environment.
"""

import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
sys.path.insert(0, '/app')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academicdb_web.settings.docker')

try:
    django.setup()
    print("✅ Django setup successful")
except Exception as e:
    print(f"❌ Django setup failed: {e}")
    sys.exit(1)

def test_database_connection():
    """Test database connection"""
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        print("✅ Database connection successful")

        # Print database engine
        from django.conf import settings
        engine = settings.DATABASES['default']['ENGINE']
        print(f"   Database engine: {engine}")

        if 'sqlite' in engine:
            db_path = settings.DATABASES['default']['NAME']
            print(f"   SQLite database: {db_path}")
            print(f"   Database exists: {Path(db_path).exists()}")

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    return True

def test_models():
    """Test model functionality"""
    try:
        from django.contrib.auth import get_user_model
        from academic.models import Publication, Teaching, Talk, Conference

        User = get_user_model()
        print("✅ Models imported successfully")

        # Test basic model operations
        user_count = User.objects.count()
        pub_count = Publication.objects.count()
        print(f"   Users: {user_count}, Publications: {pub_count}")

    except Exception as e:
        print(f"❌ Model test failed: {e}")
        return False
    return True

def test_search_functionality():
    """Test search functionality"""
    try:
        from academic.models import Publication

        # Test search method exists
        if hasattr(Publication, 'search'):
            print("✅ Search method exists")

            # Test search works (may return empty results)
            results = Publication.search("test")
            print(f"   Search executed successfully, returned {len(results)} results")
        else:
            print("❌ Search method not found")
            return False

    except Exception as e:
        print(f"❌ Search functionality test failed: {e}")
        return False
    return True

def test_api_urls():
    """Test API URL configuration"""
    try:
        from django.urls import reverse

        # Test some key URLs
        urls_to_test = [
            'admin:index',
            'api:publication-list',
        ]

        for url_name in urls_to_test:
            try:
                url = reverse(url_name)
                print(f"✅ URL '{url_name}' -> {url}")
            except Exception as e:
                print(f"❌ URL '{url_name}' failed: {e}")

    except Exception as e:
        print(f"❌ URL configuration test failed: {e}")
        return False
    return True

def test_settings():
    """Test settings configuration"""
    try:
        from django.conf import settings

        print("✅ Settings loaded successfully")
        print(f"   DEBUG: {settings.DEBUG}")
        print(f"   SECRET_KEY set: {'*' * min(len(settings.SECRET_KEY), 10) if settings.SECRET_KEY else 'NOT SET'}")
        print(f"   ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}")
        print(f"   STATIC_ROOT: {settings.STATIC_ROOT}")
        print(f"   MEDIA_ROOT: {settings.MEDIA_ROOT}")

        if hasattr(settings, 'USE_POSTGRES'):
            print(f"   USE_POSTGRES: {getattr(settings, 'USE_POSTGRES', 'Not set')}")

    except Exception as e:
        print(f"❌ Settings test failed: {e}")
        return False
    return True

def main():
    """Run all verification tests"""
    print("🔍 Docker Setup Verification")
    print("=" * 40)

    tests = [
        test_database_connection,
        test_models,
        test_search_functionality,
        test_api_urls,
        test_settings,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            failed += 1
        print()

    print("=" * 40)
    print(f"Tests passed: {passed}")
    print(f"Tests failed: {failed}")

    if failed == 0:
        print("🎉 All tests passed! Docker setup is working correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check the logs above for details.")
        sys.exit(1)

if __name__ == '__main__':
    main()