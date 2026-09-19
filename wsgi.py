"""Optional WSGI entry point — same app instance as app.py / gunicorn app:app."""

from app import app  # noqa: F401
