"""Vercel ASGI entrypoint. Migrations/bootstrap run separately, never on build."""
from app.main import app
