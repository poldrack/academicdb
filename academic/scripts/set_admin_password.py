#!/usr/bin/env python
"""
Quick script to set the admin password
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academicdb_web.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()
admin = User.objects.get(username='admin')
admin.set_password('admin123')  # Change this to your preferred password
admin.save()

print("Admin password has been set to: admin123")
print("Please change this password after logging in!")