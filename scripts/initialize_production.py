"""Run once from a trusted shell AFTER applying both reviewed SQL migrations.

python -m scripts.initialize_production
Uses environment variables; never prints secrets. Safe to repeat for the same
bootstrap email. Not called during Vercel build or cold starts.
"""
from app.production import is_production
from app.main import startup

if __name__ == "__main__":
    if not is_production():
        raise SystemExit("APP_ENV must be production")
    startup(initialize=True)
    print("Production seed/bootstrap completed")
