"""
Vercel serverless entry point for the Healthcare Management System.

Vercel runs this file (the "index" entry) as a serverless function and serves
the WSGI application it exposes. The existing Django entry points
(backend/manage.py for dev, backend/project/wsgi.py for Gunicorn) are untouched.
"""
import os
import sys

# Repo root must be on sys.path so the 'backend' package is importable.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.project.settings')

from django.core.wsgi import get_wsgi_application

# 'app' is the WSGI callable that @vercel/python serves.
app = get_wsgi_application()
