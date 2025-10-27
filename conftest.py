"""
Pytest configuration file.

This file configures pytest to properly find and use test_settings.py
for Django configuration during test runs.
"""
import os
import sys

# Add the project root to the Python path FIRST (before site-packages)
# This ensures we use the local development version, not installed package
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root in sys.path:
    sys.path.remove(project_root)
sys.path.insert(0, project_root)

# Set the Django settings module before Django gets imported
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test_settings')

# Setup Django
import django
from django.conf import settings

if not settings.configured:
    django.setup()

